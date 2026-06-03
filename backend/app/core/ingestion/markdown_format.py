"""将 HTML / 杂乱纯文本整理为可读的 Markdown。"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag
import trafilatura

_HEADING_MAX_LEN = 80
_BULLET_RE = re.compile(r"^[-*•●]\s+")
_ORDERED_RE = re.compile(r"^(\d+)[.)]\s+")

# 常见页脚/侧栏/互动噪音（中英）
_NOISE_LINE_RE = re.compile(
    r"^("
    r"分享到|扫一扫|关注公众号|打开微信|登录|注册|首页|下一篇|上一篇|"
    r"相关阅读|推荐阅读|热门推荐|猜你喜欢|延伸阅读|更多内容|"
    r"责任编辑|来源[:：]|点击[:：]|展开全文|阅读全文|查看原文|"
    r"版权所有|Copyright|All Rights Reserved|"
    r"点赞|收藏|转发|评论|留言|订阅|广告|"
    r"Share|Tweet|Follow|Sign in|Log in|Read more|Related"
    r")",
    re.IGNORECASE,
)
_SHORT_JUNK_RE = re.compile(
    r"^[\s\d\W]{0,8}$|^(首页|目录|返回|顶部|更多|详情|链接)$"
)
_LINK_ONLY_RE = re.compile(r"^\[.+\]\(https?://[^\)]+\)\s*$")


def _make_soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


# 站点已用 Markdown 渲染正文的容器（掘金、GitHub、部分博客）
_MARKDOWN_BODY_SELECTORS = (
    ".markdown-body",
    "#article-root .markdown-body",
    "article .markdown-body",
    ".md-content",
    ".post-content.markdown",
)

_ARTICLE_SELECTORS = (
    "article",
    "main",
    "[role='main']",
    ".article-content",
    ".post-content",
    ".entry-content",
    ".content-body",
    ".rich-text",
    "#article",
    "#content",
)


def _clean_markdown(md: str) -> str:
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r"[ \t]{2,}", " ", md)
    return md.strip()


def is_likely_markdown(text: str) -> bool:
    if re.search(r"^#{1,6}\s+\S", text, re.MULTILINE):
        return True
    if "```" in text:
        return True
    if re.search(r"\[[^\]]+\]\(https?://", text):
        return True
    if re.search(r"^\s*[-*+]\s+\S", text, re.MULTILINE) and text.count("\n- ") >= 2:
        return True
    if re.search(r"^\|.+\|", text, re.MULTILINE) and "|---" in text:
        return True
    # trafilatura markdown：多段空行分隔的长段落
    paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 40]
    if len(paras) >= 2 and not re.search(r"^#{1,6}\s", text, re.M):
        return True
    return False


def _is_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # Markdown 语法行不可当噪音删除
    if s.startswith("```") or re.match(r"^#{1,6}\s", s):
        return False
    if s in ("---", "***", "___"):
        return False
    if s.startswith("|") and "|" in s[1:]:
        return False
    if len(s) <= 2:
        return True
    if _SHORT_JUNK_RE.match(s):
        return True
    if _NOISE_LINE_RE.search(s):
        return True
    # 纯符号/分隔线
    if re.fullmatch(r"[-=_*#|·\s]{3,}", s):
        return True
    # 过短且几乎无中文/字母
    if len(s) < 12 and not re.search(r"[\u4e00-\u9fffA-Za-z]{4}", s):
        return True
    return False


def _markdown_structure_score(md: str) -> float:
    """衡量 Markdown 结构完整度（标题、代码块、列表）。"""
    headings = len(re.findall(r"^#{1,6}\s+\S", md, re.MULTILINE))
    fences = len(re.findall(r"^```", md, re.MULTILINE))
    lists = len(re.findall(r"^[-*+]\s+\S", md, re.MULTILINE))
    bold_blocks = len(re.findall(r"\*\*[^*]+\*\*", md))

    score = headings * 30.0 + min(fences, 24) * 15.0 + min(lists, 40) * 2.0
    score += min(bold_blocks, 30) * 1.5

    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    # 行内代码被拆成独立行的碎片（掘金错误提取的典型特征）
    fragments = sum(
        1
        for ln in lines
        if re.fullmatch(r"`[^`\n]{1,60}`", ln)
        or re.fullmatch(r">\s*`[^`]+`", ln)
        or (
            len(ln) < 18
            and "`" in ln
            and not ln.startswith("#")
            and ln.count("`") >= 2
        )
    )
    score -= fragments * 10.0

    # 无标题的长文若碎片极多，强烈降权
    if headings == 0 and fragments > 8 and len(md) > 2000:
        score -= 80.0

    return score


def _score_extracted(md: str) -> float:
    """为候选正文打分，优先保留 Markdown 结构。"""
    if not md:
        return 0.0
    text = md.strip()
    n = len(text)
    if n < 120:
        return 0.0

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return 0.0

    noise = sum(1 for ln in lines if _is_noise_line(ln))
    noise_ratio = noise / max(len(lines), 1)
    if noise_ratio > 0.45:
        return 0.0

    substantive = [ln for ln in lines if len(ln) >= 20]
    if len(substantive) < 2:
        return 0.0

    structure = _markdown_structure_score(text)

    score = min(n, 80_000) / 800.0
    score += len(substantive) * 1.5
    score += text.count("\n\n") * 3.0
    score += structure
    score -= noise * 12.0

    short_lines = sum(1 for ln in lines if len(ln) < 8)
    if short_lines > len(lines) * 0.25 and structure < 50:
        score -= 40.0

    return score


def polish_extracted_markdown(md: str, page_title: str | None = None) -> str:
    """清理提取结果，不破坏已有 Markdown 结构。"""
    if not md or not md.strip():
        return ""

    lines: list[str] = []
    prev: str | None = None
    for raw in md.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            prev = None
            continue

        if _is_noise_line(stripped):
            continue

        # 去掉空链接、重复行
        if stripped in ("[]()", "[ ]()") or stripped == prev:
            continue
        if _LINK_ONLY_RE.match(stripped) and len(stripped) < 80:
            continue

        lines.append(line)
        prev = stripped

    out = _dedupe_paragraphs(_clean_markdown("\n".join(lines)))
    if page_title:
        out = ensure_document_title(out, page_title)
    return out


def _dedupe_paragraphs(md: str) -> str:
    """去掉重复段落（多策略提取叠加时常见）。"""
    parts = re.split(r"\n{2,}", md.strip())
    seen: set[str] = set()
    kept: list[str] = []
    for part in parts:
        key = re.sub(r"\s+", " ", part.strip())[:400]
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(part.strip())
    return "\n\n".join(kept)


def ensure_document_title(content: str, title: str | None) -> str:
    if not title or not content:
        return content
    t = title.strip()
    if not t or len(t) < 2:
        return content
    # 去掉末尾站点名「 - 掘金」等
    t = re.sub(r"\s*[-–—|]\s*[^-\n]{1,24}\s*$", "", t).strip() or t
    head = content[: min(len(content), 400)]
    if t in head or t[:20] in head:
        return content
    return f"# {t}\n\n{content}"


def _resolve_links(md: str, base_url: str | None) -> str:
    if not base_url:
        return md

    def repl(m: re.Match[str]) -> str:
        label, href = m.group(1), m.group(2).strip()
        if href.startswith(("http://", "https://", "mailto:", "#")):
            return m.group(0)
        full = urljoin(base_url, href)
        return f"[{label}]({full})"

    return re.sub(r"\[([^\]]*)\]\(([^\)]+)\)", repl, md)


def _trafilatura_to_markdown(
    html: str,
    url: str | None = None,
    *,
    favor_precision: bool = False,
    favor_recall: bool = False,
) -> str | None:
    try:
        md = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_links=True,
            include_tables=True,
            include_images=False,
            deduplicate=True,
            favor_precision=favor_precision,
            favor_recall=favor_recall,
        )
        if md and len(md.strip()) > 80:
            return _resolve_links(_clean_markdown(md), url)
    except Exception:
        pass
    return None


def _readability_article_html(html: str) -> str | None:
    try:
        from readability import Document as ReadabilityDocument

        doc = ReadabilityDocument(html)
        fragment = doc.summary()
        if fragment and len(fragment) > 200:
            return fragment
    except Exception:
        pass
    return None


def _extract_markdown_body_container(html: str, url: str | None) -> str | None:
    """优先从 .markdown-body 等容器提取（掘金、GitHub 等）。"""
    soup = _make_soup(html)
    for sel in _MARKDOWN_BODY_SELECTORS:
        el = soup.select_one(sel)
        if not el:
            continue
        if len(el.get_text(strip=True)) < 200:
            continue
        fragment = str(el)
        for md in (
            _trafilatura_to_markdown(fragment, url, favor_precision=True),
            _trafilatura_to_markdown(fragment, url, favor_recall=True),
            _html_element_to_markdown(el),
        ):
            if not md or len(md.strip()) < 200:
                continue
            polished = polish_extracted_markdown(md)
            # 必须结构分达标，避免掘金等页 trafilatura 碎片版误判为 Markdown
            if _markdown_structure_score(polished) >= 60:
                return polished
    return None


def _html_element_to_markdown(root: Tag) -> str:
    """将单个正文 DOM 转为 Markdown（保留 pre/code/标题）。"""
    out: list[str] = []

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name
            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(name[1])
                text = _inline_md(child).strip()
                if text:
                    out.append(f"{'#' * min(level, 6)} {text}")
                    out.append("")
            elif name == "pre":
                code_el = child.find("code")
                code = (code_el or child).get_text("\n", strip=False).strip("\n")
                lang = ""
                if code_el and code_el.get("class"):
                    for cls in code_el["class"]:
                        cs = str(cls)
                        if cs.startswith("language-"):
                            lang = cs.replace("language-", "")
                            break
                out.append(f"```{lang}")
                out.append(code)
                out.append("```")
                out.append("")
            elif name == "p":
                text = _inline_md(child).strip()
                if text:
                    out.append(text)
                    out.append("")
            elif name in ("ul", "ol"):
                for idx, li in enumerate(child.find_all("li", recursive=False), start=1):
                    item = _inline_md(li).strip()
                    if not item:
                        continue
                    out.append(
                        f"{idx}. {item}" if name == "ol" else f"- {item}"
                    )
                out.append("")
            elif name == "blockquote":
                text = _inline_md(child).strip()
                if text:
                    for ln in text.split("\n"):
                        out.append(f"> {ln}")
                    out.append("")
            elif name in ("div", "section", "article", "span"):
                walk(child)
            elif name == "table":
                # 简单表格：只取文本行
                for tr in child.find_all("tr"):
                    cells = [
                        _inline_md(td).strip()
                        for td in tr.find_all(["th", "td"])
                    ]
                    if cells:
                        out.append("| " + " | ".join(cells) + " |")
                out.append("")

    walk(root)
    return _clean_markdown("\n".join(out))


def _select_article_fragment(html: str) -> str | None:
    soup = _make_soup(html)
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
        tag.decompose()

    best_el = None
    best_len = 0
    for selector in _ARTICLE_SELECTORS:
        for el in soup.select(selector):
            text = el.get_text("\n", strip=True)
            if len(text) > best_len:
                best_len = len(text)
                best_el = el

    if best_el and best_len > 300:
        return str(best_el)

    article = soup.find("article")
    if article:
        return str(article)
    return None


def _collect_extraction_candidates(html: str, url: str | None) -> list[str]:
    candidates: list[str] = []

    def add(text: str | None) -> None:
        if text and len(text.strip()) > 80:
            candidates.append(text.strip())

    # 整页 trafilatura markdown（掘金等效果通常最好）
    add(_trafilatura_to_markdown(html, url, favor_precision=True))

    article_html = _readability_article_html(html)
    if article_html:
        add(_trafilatura_to_markdown(article_html, url, favor_precision=True))

    fragment = _select_article_fragment(html)
    if fragment and fragment != article_html:
        add(_trafilatura_to_markdown(fragment, url, favor_precision=True))

    add(_trafilatura_to_markdown(html, url, favor_recall=True))

    # 纯文本兜底（仅当无任何 Markdown 候选时）
    if not any(re.search(r"^#{1,6}\s", c, re.M) for c in candidates):
        try:
            plain = trafilatura.extract(
                html,
                url=url,
                output_format="txt",
                include_comments=False,
                deduplicate=True,
                favor_precision=True,
            )
            if plain:
                add(plain_text_to_markdown(plain))
        except Exception:
            pass

    # 去重候选
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        key = c[:500]
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def extract_markdown_from_html(html: str, url: str | None = None) -> str:
    """从整页 HTML 提取质量最佳的 Markdown。"""
    from_container = _extract_markdown_body_container(html, url)
    if from_container and _markdown_structure_score(from_container) >= 120:
        return from_container

    candidates = _collect_extraction_candidates(html, url)
    if not candidates:
        soup = _make_soup(html)
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return plain_text_to_markdown(soup.get_text("\n", strip=True))

    def rank_key(text: str) -> tuple[float, float]:
        return (_score_extracted(text), _markdown_structure_score(text))

    best = max(candidates, key=rank_key)

    return polish_extracted_markdown(best, page_title=None)


def _mostly_cjk(text: str) -> bool:
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    alpha = sum(1 for c in text if c.isalpha())
    return cjk > alpha


def _looks_like_heading(line: str) -> bool:
    if len(line) > _HEADING_MAX_LEN:
        return False
    if line.endswith((".", "。", "!", "?", "！", "？", "；", ";", "…", "：", ":")):
        return False
    if line.count("，") > 2 or line.count(",") > 3:
        return False
    if len(line) > 48 and ("，" in line or "," in line):
        return False
    return True


def _merge_cjk_lines(lines: list[str]) -> list[str]:
    """中文站常见「一行一句」合并为段落。"""
    if not lines:
        return []
    sample = "".join(lines[: min(20, len(lines))])
    if not _mostly_cjk(sample):
        return lines

    avg_len = sum(len(x) for x in lines) / len(lines)
    if avg_len > 55:
        return lines

    merged: list[str] = []
    buf: list[str] = []
    for line in lines:
        if _looks_like_heading(line) or _BULLET_RE.match(line) or _ORDERED_RE.match(line):
            if buf:
                merged.append("".join(buf))
                buf = []
            merged.append(line)
            continue
        buf.append(line)
        # 句号结尾视为段落结束
        if line.endswith(("。", "！", "？", ".", "!", "?")) and len("".join(buf)) >= 80:
            merged.append("".join(buf))
            buf = []
    if buf:
        merged.append("".join(buf))
    return merged


def plain_text_to_markdown(text: str) -> str:
    """把抓取得到的纯文本整理为 Markdown 段落/标题/列表。"""
    if not text or not text.strip():
        return ""

    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text("\n", strip=True)

    text = _clean_markdown(text)
    if is_likely_markdown(text):
        return polish_extracted_markdown(text)

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    lines = [ln for ln in lines if not _is_noise_line(ln)]
    lines = _merge_cjk_lines(lines)

    blocks: list[str] = []
    buf: list[str] = []

    def flush_buf() -> None:
        if not buf:
            return
        if len(buf) == 1 and _looks_like_heading(buf[0]):
            blocks.append(f"## {buf[0]}")
        else:
            joined = (
                "".join(buf)
                if _mostly_cjk("".join(buf))
                else " ".join(buf)
            )
            blocks.append(joined)
        blocks.append("")
        buf.clear()

    for line in lines:
        if _BULLET_RE.match(line):
            flush_buf()
            blocks.append(_BULLET_RE.sub("- ", line))
            continue

        m = _ORDERED_RE.match(line)
        if m:
            flush_buf()
            blocks.append(f"{m.group(1)}. {line[m.end() :].strip()}")
            continue

        if not buf and _looks_like_heading(line):
            flush_buf()
            blocks.append(f"## {line}")
            blocks.append("")
            continue

        buf.append(line)

    flush_buf()
    return polish_extracted_markdown(_clean_markdown("\n".join(blocks)))


def html_to_markdown(html: str, url: str | None = None) -> str:
    """HTML 片段转为 Markdown。"""
    md = _trafilatura_to_markdown(html, url, favor_precision=True)
    if md:
        return md
    return _soup_to_markdown(html)


def _inline_md(node: Tag) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            name = child.name
            inner = _inline_md(child).strip()
            if not inner:
                continue
            if name in ("strong", "b"):
                parts.append(f"**{inner}**")
            elif name in ("em", "i"):
                parts.append(f"*{inner}*")
            elif name == "code":
                parts.append(f"`{inner}`")
            elif name == "a" and child.get("href"):
                href = str(child["href"])
                parts.append(f"[{inner}]({href})")
            else:
                parts.append(inner)
    return "".join(parts)


def _soup_to_markdown(html: str) -> str:
    soup = _make_soup(html)
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
        tag.decompose()

    out: list[str] = []

    def walk(el: Tag) -> None:
        for child in el.children:
            if isinstance(child, NavigableString):
                t = str(child).strip()
                if t and not _is_noise_line(t):
                    out.append(t)
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name
            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(name[1])
                prefix = "#" * min(level, 6)
                text = _inline_md(child).strip()
                if text:
                    out.append(f"{prefix} {text}")
                    out.append("")
            elif name == "p":
                text = _inline_md(child).strip()
                if text and not _is_noise_line(text):
                    out.append(text)
                    out.append("")
            elif name in ("ul", "ol"):
                for idx, li in enumerate(child.find_all("li", recursive=False), start=1):
                    item = _inline_md(li).strip()
                    if not item:
                        continue
                    if name == "ol":
                        out.append(f"{idx}. {item}")
                    else:
                        out.append(f"- {item}")
                out.append("")
            elif name == "blockquote":
                text = _inline_md(child).strip()
                if text:
                    for ln in text.split("\n"):
                        out.append(f"> {ln}")
                    out.append("")
            elif name == "pre":
                code = child.get_text("\n", strip=False).strip("\n")
                out.append("```")
                out.append(code)
                out.append("```")
                out.append("")
            elif name in ("div", "section", "article", "main", "body"):
                walk(child)
            elif name == "br":
                out.append("")
            else:
                text = _inline_md(child).strip()
                if text and not _is_noise_line(text):
                    out.append(text)

    root = soup.body or soup
    if isinstance(root, Tag):
        walk(root)
    else:
        return plain_text_to_markdown(soup.get_text("\n", strip=True))

    md = _clean_markdown("\n".join(out))
    return polish_extracted_markdown(md) if len(md) > 80 else plain_text_to_markdown(
        soup.get_text("\n", strip=True)
    )


def format_stored_content(
    content: str,
    source_type: str | None = None,
    page_title: str | None = None,
) -> str:
    """入库前统一整理正文为 Markdown。"""
    if not content:
        return ""
    if "<" in content and ">" in content:
        md = extract_markdown_from_html(content)
    elif is_likely_markdown(content) or (
        source_type == "url" and _markdown_structure_score(content) >= 20
    ):
        # 已是 Markdown（如掘金 trafilatura 结果），仅清理噪音，勿 plain_text 重排
        md = polish_extracted_markdown(content, page_title=page_title)
    else:
        md = plain_text_to_markdown(content)
    if page_title and not ("<" in content and ">" in content):
        md = ensure_document_title(md, page_title)
    return md
