"""
定时任务调度器

负责定期执行知识整理任务：
- 扫描未分类内容
- 自动聚类
- 生成摘要
- 去重清理
"""

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError

from app.core.config import settings

logger = logging.getLogger(__name__)


class KnowledgeScheduler:
    """知识整理调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._jobs = {}

    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Knowledge scheduler started")

    def shutdown(self):
        """关闭调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Knowledge scheduler shutdown")

    def add_scan_job(
        self,
        scan_func,
        interval_minutes: int = 30,
        interval_seconds: int = 0,
    ):
        """添加定时扫描任务"""
        job_id = "scan_unorganized"

        try:
            if job_id in self._jobs:
                self.scheduler.remove_job(job_id)

            self.scheduler.add_job(
                scan_func,
                trigger=IntervalTrigger(
                    minutes=interval_minutes, seconds=interval_seconds
                ),
                id=job_id,
                replace_existing=True,
                name="扫描未分类内容",
            )
            self._jobs[job_id] = True
            logger.info(
                f"Scan job added: every {interval_minutes}m {interval_seconds}s"
            )
        except Exception as e:
            logger.error(f"Failed to add scan job: {e}")

    def add_cluster_job(self, cluster_func, hour: int = 2, minute: int = 0):
        """添加每日聚类任务（凌晨执行）"""
        job_id = "daily_cluster"

        try:
            if job_id in self._jobs:
                self.scheduler.remove_job(job_id)

            self.scheduler.add_job(
                cluster_func,
                trigger=CronTrigger(hour=hour, minute=minute),
                id=job_id,
                replace_existing=True,
                name="每日知识聚类",
            )
            self._jobs[job_id] = True
            logger.info(f"Cluster job added: daily at {hour:02d}:{minute:02d}")
        except Exception as e:
            logger.error(f"Failed to add cluster job: {e}")

    def add_cleanup_job(self, cleanup_func, days: int = 7, hour: int = 3):
        """添加定期清理任务"""
        job_id = "cleanup_duplicates"

        try:
            if job_id in self._jobs:
                self.scheduler.remove_job(job_id)

            self.scheduler.add_job(
                cleanup_func,
                trigger=CronTrigger(hour=hour, minute=0),
                id=job_id,
                replace_existing=True,
                name="定期去重清理",
            )
            self._jobs[job_id] = True
            logger.info(
                f"Cleanup job added: daily at {hour:02d}:00, keeping {days} days history"
            )
        except Exception as e:
            logger.error(f"Failed to add cleanup job: {e}")


# 全局调度器实例
_scheduler: Optional[KnowledgeScheduler] = None


def get_scheduler() -> KnowledgeScheduler:
    """获取调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = KnowledgeScheduler()
    return _scheduler
