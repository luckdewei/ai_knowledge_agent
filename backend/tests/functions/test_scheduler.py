# backend/test_scheduler.py
import asyncio
from app.core.scheduler import get_scheduler
from datetime import datetime


async def test_scheduler():
    scheduler = get_scheduler()

    # 定义一个测试任务
    async def test_task():
        print(f"[{datetime.now()}] Test task executed")
        return {"status": "ok"}

    # 添加每10秒执行一次的任务
    scheduler.add_scan_job(test_task, interval_minutes=0, interval_seconds=10)
    scheduler.start()

    # 运行30秒观察
    await asyncio.sleep(30)
    scheduler.shutdown()


asyncio.run(test_scheduler())
