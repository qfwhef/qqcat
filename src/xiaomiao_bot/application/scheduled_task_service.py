"""Scheduled task management and execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from nonebot import get_bot

from ..adapters.onebot import build_at_message
from ..application.ai_service import AIService
from ..core.logging import get_logger
from ..infrastructure.database import database, dumps_json, loads_json

logger = get_logger("定时任务")


@dataclass(slots=True)
class _ScheduledSender:
    nickname: str
    card: str | None = None


class _ScheduledTaskEvent:
    def __init__(
        self,
        *,
        session_type: str,
        session_id: int,
        task_name: str,
        display_name: str | None = None,
    ) -> None:
        self.message_id = int(datetime.now().timestamp() * 1000)
        self.message = []
        self.reply = None
        self.sender = _ScheduledSender(nickname=task_name, card=task_name)
        if session_type == "group":
            self.group_id = int(session_id)
            self.user_id = 0
            self.group_name = display_name
        else:
            self.user_id = int(session_id)
            self.group_name = None


class ScheduledTaskService:
    """Runtime scheduler backed by MySQL."""

    def __init__(self, ai_service: AIService) -> None:
        self.ai_service = ai_service
        self.timezone = ZoneInfo("Asia/Shanghai")
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self._started = False
        self._ensure_table()

    def _ensure_table(self) -> None:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_scheduled_task (
                id BIGINT NOT NULL AUTO_INCREMENT,
                name VARCHAR(128) NOT NULL,
                description TEXT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'active',
                schedule_type VARCHAR(16) NOT NULL,
                cron_expression VARCHAR(64) NULL,
                run_at DATETIME NULL,
                interval_seconds INT UNSIGNED NULL,
                target_type VARCHAR(16) NOT NULL,
                target_ids_json JSON NOT NULL,
                message_content TEXT NOT NULL,
                last_run_at DATETIME NULL,
                next_run_at DATETIME NULL,
                last_run_status VARCHAR(16) NULL,
                last_error TEXT NULL,
                run_count INT UNSIGNED NOT NULL DEFAULT 0,
                created_by VARCHAR(64) NULL,
                updated_by VARCHAR(64) NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY idx_task_status_next (status, next_run_at),
                KEY idx_task_target_type (target_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务表'
            """,
            (),
        )

    async def start(self) -> None:
        if self._started:
            return
        self._ensure_table()
        await self.reload_active_tasks()
        self.scheduler.start()
        self._started = True
        logger.info("定时任务调度器已启动")

    async def shutdown(self) -> None:
        if not self._started:
            return
        self.scheduler.shutdown(wait=False)
        self._started = False
        logger.info("定时任务调度器已停止")

    async def reload_active_tasks(self) -> None:
        for job in list(self.scheduler.get_jobs()):
            self.scheduler.remove_job(job.id)
        rows = database.fetch_all(
            """
            SELECT *
            FROM bot_scheduled_task
            WHERE status=%s
            ORDER BY id ASC
            """,
            ("active",),
        )
        for row in rows:
            self._schedule_row(row)

    def list_tasks(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str = "",
        status: str = "",
        target_type: str = "",
    ) -> dict[str, Any]:
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        filters: list[str] = []
        params: list[Any] = []
        if keyword.strip():
            filters.append("(name LIKE %s OR description LIKE %s OR message_content LIKE %s)")
            like = f"%{keyword.strip()}%"
            params.extend([like, like, like])
        if status:
            filters.append("status=%s")
            params.append(status)
        if target_type:
            filters.append("target_type=%s")
            params.append(target_type)
        where_sql = f" WHERE {' AND '.join(filters)}" if filters else ""
        count_row = database.fetch_one(
            f"SELECT COUNT(*) AS total FROM bot_scheduled_task{where_sql}",
            tuple(params),
        )
        rows = database.fetch_all(
            f"""
            SELECT *
            FROM bot_scheduled_task
            {where_sql}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*params, safe_page_size, (safe_page - 1) * safe_page_size]),
        )
        items = [self._normalize_task_row(row) for row in rows]
        return {
            "items": items,
            "page": safe_page,
            "page_size": safe_page_size,
            "total": int(count_row["total"] or 0) if count_row else 0,
        }

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        row = database.fetch_one(
            "SELECT * FROM bot_scheduled_task WHERE id=%s",
            (int(task_id),),
        )
        return self._normalize_task_row(row) if row else None

    def create_task(self, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        validated = self._validate_payload(payload)
        row_id = database.insert(
            """
            INSERT INTO bot_scheduled_task(
                name, description, status, schedule_type, cron_expression, run_at, interval_seconds,
                target_type, target_ids_json, message_content, created_by, updated_by
            ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                validated["name"],
                validated.get("description"),
                validated["status"],
                validated["schedule_type"],
                validated.get("cron_expression"),
                validated.get("run_at"),
                validated.get("interval_seconds"),
                validated["target_type"],
                dumps_json(validated["target_ids"]),
                validated["message_content"],
                changed_by,
                changed_by,
            ),
        )
        row = database.fetch_one("SELECT * FROM bot_scheduled_task WHERE id=%s", (row_id,))
        if row and row.get("status") == "active":
            self._schedule_row(row)
        return self._normalize_task_row(row) if row else {}

    def update_task(self, task_id: int, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        current = database.fetch_one("SELECT * FROM bot_scheduled_task WHERE id=%s", (int(task_id),))
        if not current:
            raise ValueError("定时任务不存在")
        merged_payload = {
            "name": current["name"],
            "description": current.get("description"),
            "status": current.get("status"),
            "schedule_type": current["schedule_type"],
            "cron_expression": current.get("cron_expression"),
            "run_at": current.get("run_at"),
            "interval_seconds": current.get("interval_seconds"),
            "target_type": current["target_type"],
            "target_ids": loads_json(str(current.get("target_ids_json")), []),
            "message_content": current["message_content"],
            **payload,
        }
        validated = self._validate_payload(merged_payload)
        database.execute(
            """
            UPDATE bot_scheduled_task
            SET name=%s,
                description=%s,
                status=%s,
                schedule_type=%s,
                cron_expression=%s,
                run_at=%s,
                interval_seconds=%s,
                target_type=%s,
                target_ids_json=%s,
                message_content=%s,
                updated_by=%s
            WHERE id=%s
            """,
            (
                validated["name"],
                validated.get("description"),
                validated["status"],
                validated["schedule_type"],
                validated.get("cron_expression"),
                validated.get("run_at"),
                validated.get("interval_seconds"),
                validated["target_type"],
                dumps_json(validated["target_ids"]),
                validated["message_content"],
                changed_by,
                int(task_id),
            ),
        )
        self._remove_job(task_id)
        updated = database.fetch_one("SELECT * FROM bot_scheduled_task WHERE id=%s", (int(task_id),))
        if updated and updated.get("status") == "active":
            self._schedule_row(updated)
        return self._normalize_task_row(updated) if updated else {}

    def delete_task(self, task_id: int) -> dict[str, Any]:
        existing = self.get_task(task_id)
        if not existing:
            raise ValueError("定时任务不存在")
        self._remove_job(task_id)
        database.execute("DELETE FROM bot_scheduled_task WHERE id=%s", (int(task_id),))
        return {"deleted": True, "task_id": int(task_id)}

    async def run_task_now(self, task_id: int) -> dict[str, Any]:
        row = database.fetch_one("SELECT * FROM bot_scheduled_task WHERE id=%s", (int(task_id),))
        if not row:
            raise ValueError("定时任务不存在")
        await self._dispatch_task(int(task_id), ignore_status=True)
        refreshed = self.get_task(task_id)
        return refreshed or {}

    def _remove_job(self, task_id: int) -> None:
        job_id = self._job_id(task_id)
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    def _schedule_row(self, row: dict[str, Any]) -> None:
        task_id = int(row["id"])
        trigger = self._build_trigger(row)
        self._remove_job(task_id)
        job = self.scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            args=[task_id],
            id=self._job_id(task_id),
            replace_existing=True,
            misfire_grace_time=60,
        )
        self._update_next_run_at(task_id, self._resolve_job_next_run_time(job, trigger))

    def _build_trigger(self, row: dict[str, Any]):
        schedule_type = str(row["schedule_type"])
        if schedule_type == "once":
            run_at = self._to_datetime(row.get("run_at"))
            if run_at is None:
                raise ValueError("一次性任务缺少运行时间")
            return DateTrigger(run_date=run_at, timezone=self.timezone)
        if schedule_type == "interval":
            seconds = int(row.get("interval_seconds") or 0)
            if seconds <= 0:
                raise ValueError("间隔任务缺少有效 interval_seconds")
            start_date = self._to_datetime(row.get("run_at")) or (datetime.now(self.timezone) + timedelta(seconds=seconds))
            return IntervalTrigger(seconds=seconds, start_date=start_date, timezone=self.timezone)
        if schedule_type == "cron":
            expression = str(row.get("cron_expression") or "").strip()
            if not expression:
                raise ValueError("Cron 任务缺少 cron_expression")
            return CronTrigger.from_crontab(expression, timezone=self.timezone)
        raise ValueError(f"不支持的 schedule_type: {schedule_type}")

    async def _execute_task(self, task_id: int) -> None:
        await self._dispatch_task(task_id, ignore_status=False)

    async def _dispatch_task(self, task_id: int, *, ignore_status: bool) -> None:
        row = database.fetch_one("SELECT * FROM bot_scheduled_task WHERE id=%s", (int(task_id),))
        if not row:
            return
        task = self._normalize_task_row(row)
        if not ignore_status and task["status"] != "active":
            return
        success = False
        error_message: str | None = None
        try:
            bot = get_bot()
            target_ids = task["target_ids"]
            for target_id in target_ids:
                prompt = task["message_content"]
                if task["target_type"] == "group":
                    display_name = self._lookup_display_name("group", int(target_id))
                    event = _ScheduledTaskEvent(
                        session_type="group",
                        session_id=int(target_id),
                        task_name=task["name"],
                        display_name=display_name,
                    )
                    should_reply, reply_content = await self.ai_service.process_message(
                        event,
                        prompt,
                        task["name"],
                        True,
                    )
                    if not should_reply or not reply_content:
                        raise RuntimeError(f"任务 {task['name']} 未生成群聊回复")
                    await bot.send_group_msg(group_id=int(target_id), message=build_at_message(reply_content))
                else:
                    display_name = self._lookup_display_name("private", int(target_id))
                    event = _ScheduledTaskEvent(
                        session_type="private",
                        session_id=int(target_id),
                        task_name=task["name"],
                        display_name=display_name,
                    )
                    should_reply, reply_content = await self.ai_service.process_message(
                        event,
                        prompt,
                        task["name"],
                        True,
                    )
                    if not should_reply or not reply_content:
                        raise RuntimeError(f"任务 {task['name']} 未生成私聊回复")
                    await bot.send_private_msg(user_id=int(target_id), message=reply_content)
            success = True
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            logger.error("定时任务执行失败: task_id=%s error=%s", task_id, exc)

        next_run_at = None
        job = self.scheduler.get_job(self._job_id(task_id))
        if job is not None:
            next_run_at = self._resolve_job_next_run_time(job)
        if task["schedule_type"] == "once":
            new_status = "completed" if success else "paused"
            if job is not None:
                self.scheduler.remove_job(self._job_id(task_id))
        else:
            new_status = task["status"]

        database.execute(
            """
            UPDATE bot_scheduled_task
            SET last_run_at=%s,
                next_run_at=%s,
                last_run_status=%s,
                last_error=%s,
                run_count=run_count+1,
                status=%s
            WHERE id=%s
            """,
            (
                datetime.now(self.timezone),
                next_run_at,
                "success" if success else "failed",
                error_message,
                new_status,
                int(task_id),
            ),
        )

    @staticmethod
    def _job_id(task_id: int) -> str:
        return f"scheduled_task:{int(task_id)}"

    def _resolve_job_next_run_time(self, job: Any, trigger: Any | None = None) -> datetime | None:
        next_run_at = getattr(job, "next_run_time", None)
        if next_run_at is not None:
            return next_run_at
        if trigger is None:
            trigger = getattr(job, "trigger", None)
        if trigger is None:
            return None
        try:
            return trigger.get_next_fire_time(None, datetime.now(self.timezone))
        except Exception:  # noqa: BLE001
            return None

    def _update_next_run_at(self, task_id: int, next_run_at: datetime | None) -> None:
        database.execute(
            "UPDATE bot_scheduled_task SET next_run_at=%s WHERE id=%s",
            (next_run_at, int(task_id)),
        )

    def _normalize_task_row(self, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        target_ids = row.get("target_ids_json")
        if not isinstance(target_ids, list):
            target_ids = loads_json(str(target_ids) if target_ids is not None else None, [])
        return {
            **row,
            "target_ids": [int(item) for item in target_ids or []],
        }

    def _lookup_display_name(self, target_type: str, target_id: int) -> str | None:
        if target_type == "group":
            row = database.fetch_one(
                "SELECT group_name FROM bot_group_config WHERE group_id=%s",
                (int(target_id),),
            )
            return str(row.get("group_name") or "").strip() or None if row else None
        row = database.fetch_one(
            "SELECT user_nickname FROM bot_private_config WHERE user_id=%s",
            (int(target_id),),
        )
        return str(row.get("user_nickname") or "").strip() or None if row else None

    def _validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name 不能为空")
        schedule_type = str(payload.get("schedule_type") or "").strip()
        if schedule_type not in {"once", "interval", "cron"}:
            raise ValueError("schedule_type 仅支持 once / interval / cron")
        status = str(payload.get("status") or "active").strip() or "active"
        if status not in {"active", "paused", "completed"}:
            raise ValueError("status 仅支持 active / paused / completed")
        target_type = str(payload.get("target_type") or "").strip()
        if target_type not in {"group", "private"}:
            raise ValueError("target_type 仅支持 group / private")
        target_ids_raw = payload.get("target_ids") or []
        target_ids = sorted({int(item) for item in target_ids_raw if int(item) > 0})
        if not target_ids:
            raise ValueError("target_ids 不能为空")
        message_content = str(payload.get("message_content") or "").strip()
        if not message_content:
            raise ValueError("message_content 不能为空")

        run_at = self._to_datetime(payload.get("run_at"))
        cron_expression = str(payload.get("cron_expression") or "").strip() or None
        interval_seconds = payload.get("interval_seconds")
        if schedule_type == "once" and run_at is None:
            raise ValueError("一次性任务必须提供 run_at")
        if schedule_type == "interval":
            if interval_seconds is None or int(interval_seconds) <= 0:
                raise ValueError("间隔任务必须提供大于 0 的 interval_seconds")
            interval_seconds = int(interval_seconds)
        else:
            interval_seconds = None
        if schedule_type == "cron":
            if not cron_expression:
                raise ValueError("Cron 任务必须提供 cron_expression")
            try:
                CronTrigger.from_crontab(cron_expression, timezone=self.timezone)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Cron 表达式格式无效") from exc

        return {
            "name": name,
            "description": str(payload.get("description") or "").strip() or None,
            "status": status,
            "schedule_type": schedule_type,
            "cron_expression": cron_expression,
            "run_at": run_at,
            "interval_seconds": interval_seconds,
            "target_type": target_type,
            "target_ids": target_ids,
            "message_content": message_content,
        }

    def _to_datetime(self, value: Any) -> datetime | None:
        if value in {None, "", 0}:
            return None
        if isinstance(value, datetime):
            return value.astimezone(self.timezone) if value.tzinfo else value.replace(tzinfo=self.timezone)
        raw = str(value).strip().replace("T", " ")
        try:
            parsed = datetime.fromisoformat(raw)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("时间格式必须为 YYYY-MM-DD HH:mm:ss") from exc
        return parsed.astimezone(self.timezone) if parsed.tzinfo else parsed.replace(tzinfo=self.timezone)
