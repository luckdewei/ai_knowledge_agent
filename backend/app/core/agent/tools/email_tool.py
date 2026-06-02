"""
邮件工具

支持发送邮件、查询邮件
"""

import logging
from typing import List, Dict, Any, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

from .base import BaseTool, ToolResult, ToolStatus, ToolParameter
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailTool(BaseTool):
    """邮件工具"""

    def __init__(self):
        self.smtp_config = {
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "username": settings.smtp_username,
            "password": settings.smtp_password,
        }

    @property
    def name(self) -> str:
        return "email"

    @property
    def description(self) -> str:
        return "发送邮件和查询邮件"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型: send, query",
                required=True,
                enum=["send", "query"],
            ),
            ToolParameter(
                name="to", type="string", description="收件人邮箱", required=False
            ),
            ToolParameter(
                name="subject", type="string", description="邮件主题", required=False
            ),
            ToolParameter(
                name="body", type="string", description="邮件正文", required=False
            ),
            ToolParameter(
                name="is_html",
                type="boolean",
                description="是否为 HTML 格式",
                required=False,
                default=False,
            ),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """执行邮件操作"""
        action = kwargs.get("action")

        try:
            if action == "send":
                return await self._send_email(kwargs)
            elif action == "query":
                return await self._query_emails(kwargs)
            else:
                return ToolResult(
                    status=ToolStatus.FAILED, error=f"Unknown action: {action}"
                )
        except Exception as e:
            logger.error(f"Email operation failed: {e}")
            return ToolResult(status=ToolStatus.FAILED, error=str(e))

    async def _send_email(self, params: Dict) -> ToolResult:
        """发送邮件"""
        to = params.get("to")
        subject = params.get("subject")
        body = params.get("body")

        if (
            not isinstance(to, str)
            or not isinstance(subject, str)
            or not isinstance(body, str)
        ):
            return ToolResult(
                status=ToolStatus.FAILED,
                error="Missing required parameters: to, subject, body",
            )

        # 构建邮件
        msg = MIMEMultipart()
        msg["From"] = self.smtp_config["username"]
        msg["To"] = to
        msg["Subject"] = subject

        if params.get("is_html"):
            msg.attach(MIMEText(body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))

        # 发送
        async with aiosmtplib.SMTP(
            hostname=self.smtp_config["host"],
            port=self.smtp_config["port"],
            use_tls=True,
        ) as smtp:
            await smtp.login(self.smtp_config["username"], self.smtp_config["password"])
            await smtp.send_message(msg)

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"to": to, "subject": subject, "sent": True},
            metadata={"action": "send_email"},
        )

    async def _query_emails(self, params: Dict) -> ToolResult:
        """查询邮件（需要 IMAP 配置，简化实现）"""
        # 实际实现需要配置 IMAP
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"message": "Email query not implemented yet"},
            metadata={"action": "query_emails"},
        )
