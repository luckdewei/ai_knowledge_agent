from app.core.ingestion.markdown_format import (
    extract_markdown_from_html,
    plain_text_to_markdown,
    polish_extracted_markdown,
    _score_extracted,
)

SAMPLE_HTML = """
<!DOCTYPE html>
<html><head><title>示例站 - 文章标题</title>
<meta property="og:title" content="文章标题"/>
<meta name="description" content="摘要"/>
</head><body>
<nav>首页 登录 注册</nav>
<article>
  <h1>文章标题</h1>
  <p>这是第一段正文，介绍文章主题。包含足够的中文内容用于测试提取质量。</p>
  <p>这是第二段正文，继续说明细节。每段应被保留为独立段落而不是一行一句的乱码。</p>
  <h2>小节一</h2>
  <p>小节下的说明文字，同样应当完整保留在正文中。</p>
  <ul><li>要点一</li><li>要点二</li></ul>
</article>
<footer>版权所有 分享到 登录</footer>
</body></html>
"""


def test_extract_article_markdown():
    md = extract_markdown_from_html(SAMPLE_HTML, url="https://example.com/post/1")
    assert _score_extracted(md) > 0
    assert "文章标题" in md or "第一段" in md
    assert "版权所有" not in md
    assert "登录" not in md or md.count("登录") <= 1


def test_plain_text_merge_cjk():
    raw = """文章标题

这是第一句话。
这是第二句话。

分享到
推荐阅读

另一标题
- 列表一
- 列表二"""
    md = plain_text_to_markdown(raw)
    assert "分享到" not in md
    assert "列表一" in md


def test_polish_dedupes_lines():
    md = polish_extracted_markdown("段落A\n\n段落A\n\n分享到\n\n段落B")
    assert md.count("段落A") == 1
    assert "分享到" not in md
