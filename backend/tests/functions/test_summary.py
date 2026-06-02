# backend/test_summary.py
import asyncio
from app.services.summary_service import SummaryService


async def test_summary():
    service = SummaryService()

    # 测试短文本摘要
    print("=== 测试短文本摘要 ===")
    short_text = """
    智能个人知识库助手是一个能够主动管理、整理、联想和生成内容的多工具Agent。
    它可以从本地文件、网页链接、剪贴板、语音笔记等多渠道获取信息，
    并自动聚类、打标签、去重、生成摘要。
    """
    summary = await service.summarize(short_text, max_length=50)
    print(f"原文长度: {len(short_text)}")
    print(f"摘要: {summary}")
    print(f"摘要长度: {len(summary)}")

    # 测试长文本摘要（MapReduce）
    print("\n=== 测试长文本摘要（MapReduce）===")
    long_text = (
        """
    第一章介绍了项目初始化与环境搭建，包括UV包管理工具的使用和FastAPI脚手架搭建。
    第二章讲解了知识存储层设计，包括PostgreSQL + pgvector的配置和向量化流程。
    第三章实现了多源知识摄取模块，支持文件、URL、剪贴板、语音等多种来源。
    第四章构建了Agent核心架构，使用LangGraph实现了规划、检索、推理、执行、反思的完整循环。
    第五章实现了自主整理与归纳能力，包括聚类、标签生成、摘要和去重。
    """
        * 10
    )  # 重复10次制造长文本

    long_summary = await service.summarize(long_text, max_length=100)
    print(f"原文长度: {len(long_text)}")
    print(f"摘要: {long_summary}")
    print(f"摘要长度: {len(long_summary)}")

    # 测试批量摘要
    print("\n=== 测试批量摘要 ===")
    items = [
        {"id": "1", "title": "笔记1", "content": "Python 3.12 引入了新的类型语法特性"},
        {"id": "2", "title": "笔记2", "content": "FastAPI 0.100 版本支持生命周期管理"},
    ]
    results = await service.summarize_batch(items, max_length=30)
    for r in results:
        print(f"  {r['title']}: {r['summary']}")


asyncio.run(test_summary())
