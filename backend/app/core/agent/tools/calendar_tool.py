"""
日历工具

支持 Google Calendar API 的操作：
- 创建事件
- 查询事件
- 删除事件
- 获取空闲时间
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from .base import BaseTool, ToolResult, ToolStatus, ToolParameter

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """日历事件"""

    id: str
    summary: str
    start: datetime
    end: datetime
    description: Optional[str] = None
    location: Optional[str] = None


class CalendarTool(BaseTool):
    """Google Calendar 工具"""

    def __init__(self, credentials_path: Optional[str] = None):
        """
        初始化日历工具

        Args:
            credentials_path: Google API 凭证路径
        """
        self.credentials_path = credentials_path
        self.service: Any | None = None
        self._init_service()

    def _get_service(self) -> Any:
        if self.service is None:
            raise RuntimeError("Calendar service not initialized")
        return self.service

    def _init_service(self):
        """初始化 Google Calendar 服务"""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            SCOPES = ["https://www.googleapis.com/auth/calendar"]

            creds = None
            # 尝试加载已有凭证
            import os

            token_path = "token.json"
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)

            # 如果没有有效凭证，进行 OAuth 流程
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path or "credentials.json", SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                # 保存凭证
                with open(token_path, "w") as token:
                    token.write(creds.to_json())

            self.service = build("calendar", "v3", credentials=creds)
            logger.info("Google Calendar service initialized")

        except Exception as e:
            logger.error(f"Failed to initialize Calendar service: {e}")

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return "管理 Google Calendar 日历，支持创建、查询、删除事件"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型: create, query, delete, freebusy",
                required=True,
                enum=["create", "query", "delete", "freebusy"],
            ),
            ToolParameter(
                name="summary",
                type="string",
                description="事件标题（create 时必需）",
                required=False,
            ),
            ToolParameter(
                name="start_time",
                type="string",
                description="开始时间 (ISO 格式，如 2024-01-15T10:00:00)",
                required=False,
            ),
            ToolParameter(
                name="end_time",
                type="string",
                description="结束时间 (ISO 格式)",
                required=False,
            ),
            ToolParameter(
                name="event_id",
                type="string",
                description="事件 ID（delete 时必需）",
                required=False,
            ),
            ToolParameter(
                name="days",
                type="number",
                description="查询天数（query 时使用）",
                required=False,
                default=7,
            ),
            ToolParameter(
                name="description",
                type="string",
                description="事件描述",
                required=False,
            ),
            ToolParameter(
                name="location", type="string", description="事件地点", required=False
            ),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """执行日历操作"""
        action = kwargs.get("action")

        if not self.service:
            return ToolResult(
                status=ToolStatus.FAILED, error="Calendar service not initialized"
            )

        try:
            if action == "create":
                return await self._create_event(kwargs)
            elif action == "query":
                return await self._query_events(kwargs)
            elif action == "delete":
                return await self._delete_event(kwargs)
            elif action == "freebusy":
                return await self._get_freebusy(kwargs)
            else:
                return ToolResult(
                    status=ToolStatus.FAILED, error=f"Unknown action: {action}"
                )
        except Exception as e:
            logger.error(f"Calendar operation failed: {e}")
            return ToolResult(status=ToolStatus.FAILED, error=str(e))

    async def _create_event(self, params: Dict) -> ToolResult:
        """创建日历事件"""
        start_time = params.get("start_time")
        end_time = params.get("end_time")
        summary = params.get("summary")

        if not all([start_time, end_time, summary]):
            return ToolResult(
                status=ToolStatus.FAILED,
                error="Missing required parameters: start_time, end_time, summary",
            )

        event = {
            "summary": summary,
            "start": {
                "dateTime": start_time,
                "timeZone": "Asia/Shanghai",
            },
            "end": {
                "dateTime": end_time,
                "timeZone": "Asia/Shanghai",
            },
        }

        if params.get("description"):
            event["description"] = params["description"]
        if params.get("location"):
            event["location"] = params["location"]

        # 执行创建（同步转异步）
        import asyncio

        created_event = await asyncio.to_thread(
            self._get_service()
            .events()
            .insert(calendarId="primary", body=event)
            .execute
        )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "event_id": created_event.get("id"),
                "summary": created_event.get("summary"),
                "start": created_event.get("start", {}).get("dateTime"),
                "end": created_event.get("end", {}).get("dateTime"),
                "html_link": created_event.get("htmlLink"),
            },
            metadata={"action": "create_event"},
        )

    async def _query_events(self, params: Dict) -> ToolResult:
        """查询日历事件"""
        days = params.get("days", 7)

        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat().replace("+00:00", "Z")
        later = (now_dt + timedelta(days=days)).isoformat().replace("+00:00", "Z")

        import asyncio

        events_result = await asyncio.to_thread(
            self._get_service()
            .events()
            .list(
                calendarId="primary",
                timeMin=now,
                timeMax=later,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute
        )

        events = events_result.get("items", [])

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "total": len(events),
                "events": [
                    {
                        "id": e.get("id"),
                        "summary": e.get("summary"),
                        "start": e.get("start", {}).get(
                            "dateTime", e.get("start", {}).get("date")
                        ),
                        "end": e.get("end", {}).get(
                            "dateTime", e.get("end", {}).get("date")
                        ),
                    }
                    for e in events
                ],
            },
            metadata={"action": "query_events", "days": days},
        )

    async def _delete_event(self, params: Dict) -> ToolResult:
        """删除日历事件"""
        event_id = params.get("event_id")

        if not event_id:
            return ToolResult(
                status=ToolStatus.FAILED, error="Missing event_id parameter"
            )

        import asyncio

        await asyncio.to_thread(
            self._get_service()
            .events()
            .delete(calendarId="primary", eventId=event_id)
            .execute
        )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"event_id": event_id, "deleted": True},
            metadata={"action": "delete_event"},
        )

    async def _get_freebusy(self, params: Dict) -> ToolResult:
        """获取空闲时间"""
        days = params.get("days", 3)

        now_dt = datetime.now(timezone.utc)
        time_min = now_dt.isoformat().replace("+00:00", "Z")
        time_max = (now_dt + timedelta(days=days)).isoformat().replace("+00:00", "Z")

        body = {"timeMin": time_min, "timeMax": time_max, "items": [{"id": "primary"}]}

        import asyncio

        freebusy = await asyncio.to_thread(
            self._get_service().freebusy().query(body=body).execute
        )

        calendars = freebusy.get("calendars", {})
        busy_slots = calendars.get("primary", {}).get("busy", [])

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "busy_slots": busy_slots,
                "free_slots": self._calculate_free_slots(
                    busy_slots, time_min, time_max
                ),
            },
            metadata={"action": "freebusy", "days": days},
        )

    def _calculate_free_slots(
        self, busy_slots: List[Dict], time_min: str, time_max: str
    ) -> List[Dict]:
        """计算空闲时间段"""
        # 简化实现，实际需要更复杂的计算
        return [{"start": time_min, "end": time_max}]
