"""Admin panel service."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..application.admin_auth_service import AdminAuthService
from ..application.minecraft_service import MinecraftService
from ..application.prompt_defaults import (
    DEFAULT_PROMPT_BASE,
    DEFAULT_PROMPT_LOGIC_AT_ME,
    DEFAULT_PROMPT_LOGIC_GROUP,
    DEFAULT_PROMPT_LOGIC_POKE,
    DEFAULT_PROMPT_LOGIC_PRIVATE,
    DEFAULT_PROMPT_SUMMARY_SYSTEM,
)
from ..application.scheduled_task_service import ScheduledTaskService
from ..application.secret_service import SecretService
from ..core.constants import (
    CFG_BLOCKED_GROUPS,
    CFG_BLOCKED_USERS,
    CFG_ENABLE_SUMMARY_MEMORY,
    CFG_ENABLE_TOOLS,
    CFG_PROMPT_BASE,
    CFG_PROMPT_LOGIC_AT_ME,
    CFG_PROMPT_LOGIC_GROUP,
    CFG_PROMPT_LOGIC_POKE,
    CFG_PROMPT_LOGIC_PRIVATE,
    CFG_PROMPT_SUMMARY_SYSTEM,
    CFG_SUMMARY_ONLY_GROUP,
)
from ..core.logging import get_logger
from ..infrastructure.database import database, dumps_json, loads_json
from ..infrastructure.runtime_config_store import RuntimeConfigStore
from ..infrastructure.session_store import session_store

logger = get_logger("后台服务")


class AdminService:
    """Admin APIs backing service."""

    def __init__(
        self,
        runtime_config_store: RuntimeConfigStore,
        secret_service: SecretService,
        admin_auth_service: AdminAuthService,
        minecraft_service: MinecraftService,
        scheduled_task_service: ScheduledTaskService,
    ) -> None:
        self.runtime_config_store = runtime_config_store
        self.secret_service = secret_service
        self.admin_auth_service = admin_auth_service
        self.minecraft_service = minecraft_service
        self.scheduled_task_service = scheduled_task_service

    def get_overview(self) -> dict[str, Any]:
        since = datetime.now() - timedelta(hours=24)
        group_msg = session_store.count_recent_messages(session_type="group", since=since)
        private_msg = session_store.count_recent_messages(session_type="private", since=since)
        group_summary = self._count(
            "SELECT COUNT(*) AS total FROM bot_group_summary WHERE created_at >= %s",
            (since,),
        )
        private_summary = self._count(
            "SELECT COUNT(*) AS total FROM bot_private_summary WHERE created_at >= %s",
            (since,),
        )
        tool_messages = session_store.count_recent_messages(session_type="group", since=since, role="tool")
        tool_messages += session_store.count_recent_messages(session_type="private", since=since, role="tool")
        failed_ai_calls = self._count(
            "SELECT COUNT(*) AS total FROM bot_ai_call_log WHERE is_success=0 AND created_at >= %s",
            (since,),
        )
        recent_failures = database.fetch_all(
            """
            SELECT id, session_type, session_id, stage, model_name, failure_reason, latency_ms, created_at
            FROM bot_ai_call_log
            WHERE is_success=0
            ORDER BY id DESC
            LIMIT 10
            """,
            (),
        )
        recent_changes = database.fetch_all(
            """
            SELECT id, config_domain, scope_ref, change_type, changed_by, created_at
            FROM bot_config_change_log
            ORDER BY id DESC
            LIMIT 10
            """,
            (),
        )
        return {
            "stats": {
                "messages_24h": int(group_msg + private_msg),
                "summaries_24h": int(group_summary + private_summary),
                "tool_messages_24h": int(tool_messages),
                "ai_failures_24h": int(failed_ai_calls),
            },
            "runtime_config": self.runtime_config_store.get_runtime_snapshot(),
            "recent_failures": recent_failures,
            "recent_config_changes": recent_changes,
        }

    def get_runtime_config(self) -> dict[str, Any]:
        return {
            **self.runtime_config_store.get_runtime_snapshot(),
            **self.minecraft_service.get_runtime_config(),
        }

    def update_runtime_config(self, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        before = self.get_runtime_config()
        runtime_payload = dict(payload)
        minecraft_notify_groups = runtime_payload.pop("minecraft_notify_groups", None)
        self.runtime_config_store.update_runtime_settings(runtime_payload)
        if minecraft_notify_groups is not None:
            self.minecraft_service.update_runtime_config(
                minecraft_notify_groups=[int(item) for item in minecraft_notify_groups],
            )
        after = self.get_runtime_config()
        self._log_config_change(
            config_domain="ai_runtime",
            scope_ref="global:default",
            change_type="update",
            before_json=before,
            after_json=after,
            changed_by=changed_by,
        )
        return after

    def get_prompts(self) -> dict[str, Any]:
        return {
            "prompt_base": str(self.runtime_config_store.get(CFG_PROMPT_BASE, DEFAULT_PROMPT_BASE)),
            "prompt_logic_private": str(
                self.runtime_config_store.get(CFG_PROMPT_LOGIC_PRIVATE, DEFAULT_PROMPT_LOGIC_PRIVATE)
            ),
            "prompt_logic_at_me": str(
                self.runtime_config_store.get(CFG_PROMPT_LOGIC_AT_ME, DEFAULT_PROMPT_LOGIC_AT_ME)
            ),
            "prompt_logic_poke": str(
                self.runtime_config_store.get(CFG_PROMPT_LOGIC_POKE, DEFAULT_PROMPT_LOGIC_POKE)
            ),
            "prompt_logic_group": str(
                self.runtime_config_store.get(CFG_PROMPT_LOGIC_GROUP, DEFAULT_PROMPT_LOGIC_GROUP)
            ),
            "prompt_summary_system": str(
                self.runtime_config_store.get(CFG_PROMPT_SUMMARY_SYSTEM, DEFAULT_PROMPT_SUMMARY_SYSTEM)
            ),
        }

    def update_prompts(self, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        before = self.get_prompts()
        self.runtime_config_store.update(payload)
        after = self.get_prompts()
        self._log_config_change(
            config_domain="prompt",
            scope_ref="global",
            change_type="update",
            before_json=before,
            after_json=after,
            changed_by=changed_by,
        )
        return after

    def get_blocklist(self) -> dict[str, Any]:
        return {
            "blocked_groups": self.runtime_config_store.get_list(CFG_BLOCKED_GROUPS, []),
            "blocked_users": self.runtime_config_store.get_list(CFG_BLOCKED_USERS, []),
        }

    def update_blocklist(
        self,
        *,
        blocked_groups: list[int] | None,
        blocked_users: list[int] | None,
        changed_by: str,
    ) -> dict[str, Any]:
        before = self.get_blocklist()
        payload: dict[str, Any] = {}
        if blocked_groups is not None:
            payload[CFG_BLOCKED_GROUPS] = blocked_groups
        if blocked_users is not None:
            payload[CFG_BLOCKED_USERS] = blocked_users
        self.runtime_config_store.update(payload)
        after = self.get_blocklist()
        self._log_config_change(
            config_domain="blocklist",
            scope_ref="global",
            change_type="update",
            before_json=before,
            after_json=after,
            changed_by=changed_by,
        )
        return after

    def list_secrets(self) -> list[dict[str, Any]]:
        return self.secret_service.list_secrets()

    def update_secret(
        self,
        *,
        secret_key: str,
        secret_value: str,
        value_hint: str | None,
        changed_by: str,
    ) -> dict[str, Any]:
        before = self._find_secret_public(secret_key)
        after = self.secret_service.update_secret(
            secret_key,
            secret_value,
            updated_by=changed_by,
            value_hint=value_hint,
        )
        self._log_config_change(
            config_domain="secret",
            scope_ref=secret_key,
            change_type="update" if before else "create",
            before_json=before,
            after_json=after,
            changed_by=changed_by,
        )
        return after

    def list_tools(self) -> list[dict[str, Any]]:
        rows = database.fetch_all(
            """
            SELECT
                id, tool_name, display_name, description, parameters_json, tool_type,
                method, url, headers_json, body_template, timeout_seconds, is_enabled,
                created_at, updated_at
            FROM bot_tool_config
            ORDER BY tool_type ASC, tool_name ASC
            """,
            (),
        )
        for row in rows:
            row["parameters_json"] = loads_json(
                str(row.get("parameters_json")) if row.get("parameters_json") is not None else None,
                {},
            )
            row["headers_json"] = loads_json(
                str(row.get("headers_json")) if row.get("headers_json") is not None else None,
                {},
            )
        return rows

    def list_scheduled_tasks(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str = "",
        status: str = "",
        target_type: str = "",
    ) -> dict[str, Any]:
        return self.scheduled_task_service.list_tasks(
            page=page,
            page_size=page_size,
            keyword=keyword,
            status=status,
            target_type=target_type,
        )

    def create_scheduled_task(self, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        task = self.scheduled_task_service.create_task(payload, changed_by=changed_by)
        self._log_config_change(
            config_domain="scheduled_task",
            scope_ref=f"task:{task.get('id')}",
            change_type="create",
            before_json=None,
            after_json=task,
            changed_by=changed_by,
        )
        return task

    def update_scheduled_task(self, task_id: int, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        before = self.scheduled_task_service.get_task(task_id)
        if not before:
            raise ValueError("定时任务不存在")
        task = self.scheduled_task_service.update_task(task_id, payload, changed_by=changed_by)
        self._log_config_change(
            config_domain="scheduled_task",
            scope_ref=f"task:{task_id}",
            change_type="update",
            before_json=before,
            after_json=task,
            changed_by=changed_by,
        )
        return task

    def delete_scheduled_task(self, task_id: int, *, changed_by: str) -> dict[str, Any]:
        before = self.scheduled_task_service.get_task(task_id)
        if not before:
            raise ValueError("定时任务不存在")
        result = self.scheduled_task_service.delete_task(task_id)
        self._log_config_change(
            config_domain="scheduled_task",
            scope_ref=f"task:{task_id}",
            change_type="delete",
            before_json=before,
            after_json=result,
            changed_by=changed_by,
        )
        return result

    async def run_scheduled_task_now(self, task_id: int, *, changed_by: str) -> dict[str, Any]:
        before = self.scheduled_task_service.get_task(task_id)
        if not before:
            raise ValueError("定时任务不存在")
        task = await self.scheduled_task_service.run_task_now(task_id)
        self._log_config_change(
            config_domain="scheduled_task",
            scope_ref=f"task:{task_id}",
            change_type="update",
            before_json=before,
            after_json=task,
            changed_by=changed_by,
        )
        return task

    def create_http_tool(self, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        tool_name = str(payload.get("tool_name") or "").strip()
        if not tool_name:
            raise ValueError("tool_name 不能为空")
        if self._find_tool_config(tool_name):
            raise ValueError("工具名已存在")
        parameters_json = payload.get("parameters_json") or {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
        headers_json = payload.get("headers_json") or {}
        database.execute(
            """
            INSERT INTO bot_tool_config(
                tool_name, display_name, description, parameters_json, tool_type,
                method, url, headers_json, body_template, timeout_seconds, is_enabled
            ) VALUES(%s, %s, %s, %s, 'http', %s, %s, %s, %s, %s, %s)
            """,
            (
                tool_name,
                payload.get("display_name") or tool_name,
                payload.get("description") or "",
                dumps_json(parameters_json),
                str(payload.get("method") or "GET").upper(),
                str(payload.get("url") or "").strip(),
                dumps_json(headers_json),
                payload.get("body_template") or None,
                int(payload.get("timeout_seconds") or 15),
                1 if bool(payload.get("is_enabled", True)) else 0,
            ),
        )
        after = self._find_tool_config(tool_name)
        self._log_config_change(
            config_domain="tool",
            scope_ref=tool_name,
            change_type="create",
            before_json=None,
            after_json=after,
            changed_by=changed_by,
        )
        return after or {}

    def update_tool(self, tool_name: str, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        before = self._find_tool_config(tool_name)
        if not before:
            raise ValueError("工具不存在")
        updates: list[str] = []
        params: list[Any] = []
        allowed_plain_fields = ["display_name", "description", "method", "url", "body_template", "timeout_seconds"]
        for field in allowed_plain_fields:
            if field not in payload:
                continue
            value = payload[field]
            if field == "method" and value is not None:
                value = str(value).upper()
            if field == "timeout_seconds" and value is not None:
                value = int(value)
            updates.append(f"{field}=%s")
            params.append(value)
        if "is_enabled" in payload:
            updates.append("is_enabled=%s")
            params.append(1 if bool(payload["is_enabled"]) else 0)
        if "parameters_json" in payload:
            updates.append("parameters_json=%s")
            params.append(dumps_json(payload["parameters_json"]) if payload["parameters_json"] is not None else None)
        if "headers_json" in payload:
            updates.append("headers_json=%s")
            params.append(dumps_json(payload["headers_json"]) if payload["headers_json"] is not None else None)
        if not updates:
            return before
        params.append(tool_name)
        database.execute(
            f"UPDATE bot_tool_config SET {', '.join(updates)} WHERE tool_name=%s",
            tuple(params),
        )
        after = self._find_tool_config(tool_name)
        self._log_config_change(
            config_domain="tool",
            scope_ref=tool_name,
            change_type="update",
            before_json=before,
            after_json=after,
            changed_by=changed_by,
        )
        return after or before

    def delete_tool(self, tool_name: str, *, changed_by: str) -> dict[str, Any]:
        before = self._find_tool_config(tool_name)
        if not before:
            raise ValueError("工具不存在")
        if str(before.get("tool_type") or "") == "builtin":
            raise ValueError("内置工具不允许删除")
        database.execute("DELETE FROM bot_tool_config WHERE tool_name=%s", (tool_name,))
        self._log_config_change(
            config_domain="tool",
            scope_ref=tool_name,
            change_type="delete",
            before_json=before,
            after_json={"deleted": True, "tool_name": tool_name},
            changed_by=changed_by,
        )
        return {"deleted": True, "tool_name": tool_name}

    def list_admin_users(self) -> list[dict[str, Any]]:
        return self.admin_auth_service.list_admin_users()

    def create_admin_user(
        self,
        *,
        user_id: int,
        nickname: str | None,
        is_active: bool,
        changed_by: str,
    ) -> dict[str, Any]:
        before = self._find_admin_user(user_id)
        row = self.admin_auth_service.create_admin_user(user_id, nickname, is_active=is_active)
        self._log_config_change(
            config_domain="admin_user",
            scope_ref=f"user:{user_id}",
            change_type="update" if before else "create",
            before_json=before,
            after_json=row,
            changed_by=changed_by,
        )
        return row

    def update_admin_user(
        self,
        *,
        user_id: int,
        nickname: str | None,
        is_active: bool | None,
        changed_by: str,
    ) -> dict[str, Any]:
        before = self._find_admin_user(user_id)
        row = self.admin_auth_service.update_admin_user(user_id, nickname=nickname, is_active=is_active)
        self._log_config_change(
            config_domain="admin_user",
            scope_ref=f"user:{user_id}",
            change_type="update",
            before_json=before,
            after_json=row,
            changed_by=changed_by,
        )
        return row

    def list_group_configs(self, *, page: int, page_size: int, keyword: str = "") -> dict[str, Any]:
        filters = []
        params: list[Any] = []
        if keyword.strip():
            filters.append("(CAST(group_id AS CHAR) LIKE %s OR group_name LIKE %s)")
            like = f"%{keyword.strip()}%"
            params.extend([like, like])
        return self._paged_query(
            table_sql="FROM bot_group_config",
            filters=filters,
            params=params,
            order_by="updated_at DESC, group_id DESC",
            page=page,
            page_size=page_size,
            columns="group_id, group_name, reply_rate, is_sleeping, enable_ai, enable_summary, updated_at",
        )

    def update_group_config(self, group_id: int, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        before = database.fetch_one("SELECT * FROM bot_group_config WHERE group_id=%s", (group_id,))
        row = before or {
            "group_id": group_id,
            "group_name": None,
            "reply_rate": 100,
            "is_sleeping": 0,
            "enable_ai": 1,
            "enable_summary": 1,
        }
        database.execute(
            """
            INSERT INTO bot_group_config(group_id, group_name, reply_rate, is_sleeping, enable_ai, enable_summary, updated_by)
            VALUES(%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                group_name=VALUES(group_name),
                reply_rate=VALUES(reply_rate),
                is_sleeping=VALUES(is_sleeping),
                enable_ai=VALUES(enable_ai),
                enable_summary=VALUES(enable_summary),
                updated_by=VALUES(updated_by)
            """,
            (
                group_id,
                payload.get("group_name", row.get("group_name")),
                payload.get("reply_rate", row.get("reply_rate")),
                1 if bool(payload.get("is_sleeping", row.get("is_sleeping"))) else 0,
                1 if bool(payload.get("enable_ai", row.get("enable_ai"))) else 0,
                1 if bool(payload.get("enable_summary", row.get("enable_summary"))) else 0,
                changed_by,
            ),
        )
        after = database.fetch_one("SELECT * FROM bot_group_config WHERE group_id=%s", (group_id,))
        self._log_config_change(
            config_domain="group_config",
            scope_ref=f"group:{group_id}",
            change_type="update" if before else "create",
            before_json=before,
            after_json=after,
            changed_by=changed_by,
        )
        return after or row

    def list_private_configs(self, *, page: int, page_size: int, keyword: str = "") -> dict[str, Any]:
        filters = []
        params: list[Any] = []
        if keyword.strip():
            filters.append("(CAST(user_id AS CHAR) LIKE %s OR user_nickname LIKE %s)")
            like = f"%{keyword.strip()}%"
            params.extend([like, like])
        return self._paged_query(
            table_sql="FROM bot_private_config",
            filters=filters,
            params=params,
            order_by="updated_at DESC, user_id DESC",
            page=page,
            page_size=page_size,
            columns="user_id, user_nickname, reply_rate, is_sleeping, enable_ai, enable_summary, updated_at",
        )

    def update_private_config(self, user_id: int, payload: dict[str, Any], *, changed_by: str) -> dict[str, Any]:
        before = database.fetch_one("SELECT * FROM bot_private_config WHERE user_id=%s", (user_id,))
        row = before or {
            "user_id": user_id,
            "user_nickname": None,
            "reply_rate": 100,
            "is_sleeping": 0,
            "enable_ai": 1,
            "enable_summary": 1,
        }
        database.execute(
            """
            INSERT INTO bot_private_config(user_id, user_nickname, reply_rate, is_sleeping, enable_ai, enable_summary, updated_by)
            VALUES(%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                user_nickname=VALUES(user_nickname),
                reply_rate=VALUES(reply_rate),
                is_sleeping=VALUES(is_sleeping),
                enable_ai=VALUES(enable_ai),
                enable_summary=VALUES(enable_summary),
                updated_by=VALUES(updated_by)
            """,
            (
                user_id,
                payload.get("user_nickname", row.get("user_nickname")),
                payload.get("reply_rate", row.get("reply_rate")),
                1 if bool(payload.get("is_sleeping", row.get("is_sleeping"))) else 0,
                1 if bool(payload.get("enable_ai", row.get("enable_ai"))) else 0,
                1 if bool(payload.get("enable_summary", row.get("enable_summary"))) else 0,
                changed_by,
            ),
        )
        after = database.fetch_one("SELECT * FROM bot_private_config WHERE user_id=%s", (user_id,))
        self._log_config_change(
            config_domain="private_config",
            scope_ref=f"user:{user_id}",
            change_type="update" if before else "create",
            before_json=before,
            after_json=after,
            changed_by=changed_by,
        )
        return after or row

    def list_messages(
        self,
        *,
        session_type: str,
        page: int,
        page_size: int,
        session_id: int | None = None,
        sender_user_id: int | None = None,
        role: str = "",
        keyword: str = "",
        start_at: str = "",
        end_at: str = "",
        is_reply: bool | None = None,
        is_tool: bool | None = None,
    ) -> dict[str, Any]:
        if session_id is None:
            return {"items": [], "page": max(1, page), "page_size": max(1, min(page_size, 200)), "total": 0}
        return session_store.list_messages_for_admin(
            session_type=session_type,
            session_id=session_id,
            page=page,
            page_size=page_size,
            sender_user_id=sender_user_id,
            role=role,
            keyword=keyword,
            start_at=start_at,
            end_at=end_at,
            is_reply=is_reply,
            is_tool=is_tool,
        )

    def list_message_sessions(
        self,
        *,
        session_type: str,
        keyword: str = "",
    ) -> list[dict[str, Any]]:
        sessions = session_store.list_registered_sessions(session_type, keyword=keyword)
        for item in sessions:
            item["display_name"] = item.get("display_name") or (
                f"群聊 {item['session_id']}" if session_type == "group" else f"QQ {item['session_id']}"
            )
        return sessions

    def get_message_detail(self, *, session_type: str, session_id: int, message_id: int) -> dict[str, Any]:
        row = session_store.get_message_for_admin(
            session_type=session_type,
            session_id=session_id,
            message_id=message_id,
        )
        if not row:
            raise ValueError("消息不存在")
        return row

    def update_message(
        self,
        *,
        session_type: str,
        session_id: int,
        message_id: int,
        payload: dict[str, Any],
        changed_by: str,
    ) -> dict[str, Any]:
        before = self.get_message_detail(
            session_type=session_type,
            session_id=session_id,
            message_id=message_id,
        )
        after = session_store.update_message_for_admin(
            session_type=session_type,
            session_id=session_id,
            message_id=message_id,
            payload=payload,
        )
        if not after:
            raise ValueError("消息不存在")
        self._log_config_change(
            config_domain="message_edit",
            scope_ref=f"{session_type}:{session_id}:message:{message_id}",
            change_type="update",
            before_json=before,
            after_json=after,
            changed_by=changed_by,
        )
        return after

    def delete_messages(
        self,
        *,
        session_type: str,
        session_id: int,
        message_ids: list[int],
        changed_by: str,
    ) -> dict[str, Any]:
        before_rows = []
        for message_id in message_ids:
            row = session_store.get_message_for_admin(
                session_type=session_type,
                session_id=session_id,
                message_id=message_id,
            )
            if row:
                before_rows.append(row)
        deleted = session_store.delete_messages_for_admin(
            session_type=session_type,
            session_id=session_id,
            message_ids=message_ids,
        )
        self._log_config_change(
            config_domain="message_delete",
            scope_ref=f"{session_type}:{session_id}",
            change_type="delete",
            before_json=before_rows,
            after_json={"deleted_count": deleted, "message_ids": message_ids},
            changed_by=changed_by,
        )
        return {
            "deleted_count": deleted,
            "message_ids": message_ids,
        }

    def clear_session_messages(
        self,
        *,
        session_type: str,
        session_id: int,
        changed_by: str,
    ) -> dict[str, Any]:
        deleted = session_store.clear_session_for_admin(
            session_type=session_type,
            session_id=session_id,
        )
        self._log_config_change(
            config_domain="message_delete",
            scope_ref=f"{session_type}:{session_id}",
            change_type="delete",
            before_json={"mode": "clear_session"},
            after_json={"deleted_count": deleted, "session_type": session_type, "session_id": session_id},
            changed_by=changed_by,
        )
        return {
            "deleted_count": deleted,
            "session_type": session_type,
            "session_id": session_id,
        }

    def create_summary(self, *, session_type: str, payload: dict[str, Any], changed_by: str) -> dict[str, Any]:
        meta = self._summary_meta(session_type)
        session_id = int(payload.get("session_id") or 0)
        if session_id <= 0:
            raise ValueError("session_id 不能为空")
        summary_text = str(payload.get("summary_text") or "").strip()
        if not summary_text:
            raise ValueError("summary_text 不能为空")
        version_row = database.fetch_one(
            f"SELECT MAX(summary_version) AS max_version FROM {meta['summary_table']} WHERE {meta['summary_key']}=%s",
            (session_id,),
        )
        next_version = int(version_row["max_version"] or 0) + 1 if version_row else 1
        is_active = bool(payload.get("is_active", True))
        if is_active:
            database.execute(
                f"UPDATE {meta['summary_table']} SET is_active=0 WHERE {meta['summary_key']}=%s",
                (session_id,),
            )
        database.execute(
            f"""
            INSERT INTO {meta['summary_table']}(
                {meta['summary_key']}, {meta['name_column']}, summary_version, summary_text, summary_json,
                source_start_message_id, source_end_message_id, source_message_count,
                created_by_model, is_active
            ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                payload.get("session_name"),
                next_version,
                summary_text,
                dumps_json(payload["summary_json"]) if payload.get("summary_json") is not None else None,
                payload.get("source_start_message_id"),
                payload.get("source_end_message_id"),
                int(payload.get("source_message_count") or 0),
                payload.get("created_by_model"),
                1 if is_active else 0,
            ),
        )
        row = database.fetch_one(
            f"SELECT id FROM {meta['summary_table']} WHERE {meta['summary_key']}=%s AND summary_version=%s LIMIT 1",
            (session_id, next_version),
        )
        self._ensure_active_summary(session_type, session_id)
        self._sync_summary_state_from_active(session_type, session_id)
        created = self.get_summary_detail(session_type=session_type, summary_id=int(row["id"])) if row else {}
        self._log_config_change(
            config_domain="summary",
            scope_ref=f"{session_type}:{session_id}",
            change_type="create",
            before_json=None,
            after_json=created,
            changed_by=changed_by,
        )
        return created

    def get_summary_detail(self, *, session_type: str, summary_id: int) -> dict[str, Any]:
        meta = self._summary_meta(session_type)
        row = database.fetch_one(
            f"""
            SELECT
                s.id, s.{meta['summary_key']} AS session_id, s.{meta['name_column']} AS session_name,
                s.summary_version, s.summary_text, s.summary_json,
                s.source_start_message_id, s.source_end_message_id, s.source_message_count,
                s.created_by_model, s.is_active, s.created_at, s.updated_at,
                st.last_message_id, st.last_summary_message_id, st.summary_version AS current_summary_version, st.summary_cooldown_until
            FROM {meta['summary_table']} s
            LEFT JOIN {meta['state_table']} st ON s.{meta['summary_key']}=st.{meta['state_key']}
            WHERE s.id=%s
            LIMIT 1
            """,
            (int(summary_id),),
        )
        if not row:
            raise ValueError("摘要不存在")
        row["summary_json"] = loads_json(
            str(row.get("summary_json")) if row.get("summary_json") is not None else None,
            row.get("summary_json"),
        )
        return row

    def update_summary(
        self,
        *,
        session_type: str,
        summary_id: int,
        payload: dict[str, Any],
        changed_by: str,
    ) -> dict[str, Any]:
        before = self.get_summary_detail(session_type=session_type, summary_id=summary_id)
        meta = self._summary_meta(session_type)
        updates: list[str] = []
        params: list[Any] = []
        for field in ["summary_text", "created_by_model", "source_start_message_id", "source_end_message_id", "source_message_count"]:
            if field not in payload:
                continue
            value = payload[field]
            if field == "source_message_count" and value is not None:
                value = int(value)
            updates.append(f"{field}=%s")
            params.append(value)
        if "session_name" in payload:
            updates.append(f"{meta['name_column']}=%s")
            params.append(payload["session_name"])
        if "summary_json" in payload:
            updates.append("summary_json=%s")
            params.append(dumps_json(payload["summary_json"]) if payload["summary_json"] is not None else None)
        if "is_active" in payload:
            is_active = bool(payload["is_active"])
            if is_active:
                database.execute(
                    f"UPDATE {meta['summary_table']} SET is_active=0 WHERE {meta['summary_key']}=%s",
                    (before["session_id"],),
                )
            updates.append("is_active=%s")
            params.append(1 if is_active else 0)
        if not updates:
            return before
        params.append(int(summary_id))
        database.execute(
            f"UPDATE {meta['summary_table']} SET {', '.join(updates)} WHERE id=%s",
            tuple(params),
        )
        self._ensure_active_summary(session_type, int(before["session_id"]))
        self._sync_summary_state_from_active(session_type, int(before["session_id"]))
        after = self.get_summary_detail(session_type=session_type, summary_id=summary_id)
        self._log_config_change(
            config_domain="summary",
            scope_ref=f"{session_type}:{before['session_id']}:summary:{summary_id}",
            change_type="update",
            before_json=before,
            after_json=after,
            changed_by=changed_by,
        )
        return after

    def delete_summary(self, *, session_type: str, summary_id: int, changed_by: str) -> dict[str, Any]:
        before = self.get_summary_detail(session_type=session_type, summary_id=summary_id)
        meta = self._summary_meta(session_type)
        database.execute(f"DELETE FROM {meta['summary_table']} WHERE id=%s", (int(summary_id),))
        self._ensure_active_summary(session_type, int(before["session_id"]))
        self._sync_summary_state_from_active(session_type, int(before["session_id"]))
        result = {"deleted": True, "summary_id": int(summary_id)}
        self._log_config_change(
            config_domain="summary",
            scope_ref=f"{session_type}:{before['session_id']}:summary:{summary_id}",
            change_type="delete",
            before_json=before,
            after_json=result,
            changed_by=changed_by,
        )
        return result

    def list_summaries(
        self,
        *,
        session_type: str,
        page: int,
        page_size: int,
        session_id: int | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any]:
        summary_table = "bot_group_summary" if session_type == "group" else "bot_private_summary"
        state_table = "bot_group_session_state" if session_type == "group" else "bot_private_session_state"
        summary_key = "group_id" if session_type == "group" else "peer_user_id"
        state_key = "group_id" if session_type == "group" else "user_id"
        name_column = "group_name" if session_type == "group" else "peer_nickname"
        filters: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            filters.append(f"s.{summary_key}=%s")
            params.append(session_id)
        if is_active is not None:
            filters.append("s.is_active=%s")
            params.append(1 if is_active else 0)
        return self._paged_query(
            table_sql=f"FROM {summary_table} s LEFT JOIN {state_table} st ON s.{summary_key}=st.{state_key}",
            filters=filters,
            params=params,
            order_by="s.updated_at DESC, s.id DESC",
            page=page,
            page_size=page_size,
            columns=(
                f"s.id, s.{summary_key} AS session_id, s.{name_column} AS session_name, s.summary_version, s.summary_text, s.summary_json, "
                "s.source_start_message_id, s.source_end_message_id, s.source_message_count, "
                "s.created_by_model, s.is_active, s.created_at, s.updated_at, "
                "st.last_message_id, st.last_summary_message_id, st.summary_version AS current_summary_version, st.summary_cooldown_until"
            ),
        )

    def _summary_meta(self, session_type: str) -> dict[str, str]:
        return {
            "summary_table": "bot_group_summary" if session_type == "group" else "bot_private_summary",
            "state_table": "bot_group_session_state" if session_type == "group" else "bot_private_session_state",
            "summary_key": "group_id" if session_type == "group" else "peer_user_id",
            "state_key": "group_id" if session_type == "group" else "user_id",
            "name_column": "group_name" if session_type == "group" else "peer_nickname",
        }

    def _ensure_active_summary(self, session_type: str, session_id: int) -> None:
        meta = self._summary_meta(session_type)
        active_row = database.fetch_one(
            f"SELECT id FROM {meta['summary_table']} WHERE {meta['summary_key']}=%s AND is_active=1 LIMIT 1",
            (session_id,),
        )
        if active_row:
            return
        latest_row = database.fetch_one(
            f"""
            SELECT id
            FROM {meta['summary_table']}
            WHERE {meta['summary_key']}=%s
            ORDER BY summary_version DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        )
        if latest_row:
            database.execute(
                f"UPDATE {meta['summary_table']} SET is_active=1 WHERE id=%s",
                (int(latest_row["id"]),),
            )

    def _sync_summary_state_from_active(self, session_type: str, session_id: int) -> None:
        meta = self._summary_meta(session_type)
        active_row = database.fetch_one(
            f"""
            SELECT summary_version, source_end_message_id
            FROM {meta['summary_table']}
            WHERE {meta['summary_key']}=%s AND is_active=1
            ORDER BY summary_version DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        )
        state = database.fetch_one(
            f"SELECT last_message_id, summary_cooldown_until FROM {meta['state_table']} WHERE {meta['state_key']}=%s",
            (session_id,),
        ) or {}
        if active_row:
            database.execute(
                f"""
                INSERT INTO {meta['state_table']}({meta['state_key']}, last_message_id, last_summary_message_id, summary_version, summary_cooldown_until)
                VALUES(%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    last_message_id=VALUES(last_message_id),
                    last_summary_message_id=VALUES(last_summary_message_id),
                    summary_version=VALUES(summary_version),
                    summary_cooldown_until=VALUES(summary_cooldown_until)
                """,
                (
                    session_id,
                    state.get("last_message_id"),
                    int(active_row.get("source_end_message_id") or 0),
                    int(active_row.get("summary_version") or 0),
                    state.get("summary_cooldown_until"),
                ),
            )
            return
        database.execute(
            f"""
            INSERT INTO {meta['state_table']}({meta['state_key']}, last_message_id, last_summary_message_id, summary_version, summary_cooldown_until)
            VALUES(%s, %s, 0, 0, %s)
            ON DUPLICATE KEY UPDATE
                last_message_id=VALUES(last_message_id),
                last_summary_message_id=VALUES(last_summary_message_id),
                summary_version=VALUES(summary_version),
                summary_cooldown_until=VALUES(summary_cooldown_until)
            """,
            (
                session_id,
                state.get("last_message_id"),
                state.get("summary_cooldown_until"),
            ),
        )

    def list_ai_call_logs(
        self,
        *,
        page: int,
        page_size: int,
        session_type: str = "",
        session_id: int | None = None,
        stage: str = "",
        model_name: str = "",
        failure_reason: str = "",
        is_success: bool | None = None,
        start_at: str = "",
        end_at: str = "",
    ) -> dict[str, Any]:
        filters: list[str] = []
        params: list[Any] = []
        if session_type:
            filters.append("session_type=%s")
            params.append(session_type)
        if session_id is not None:
            filters.append("session_id=%s")
            params.append(session_id)
        if stage:
            filters.append("stage=%s")
            params.append(stage)
        if model_name:
            filters.append("model_name LIKE %s")
            params.append(f"%{model_name}%")
        if failure_reason:
            filters.append("failure_reason=%s")
            params.append(failure_reason)
        if is_success is not None:
            filters.append("is_success=%s")
            params.append(1 if is_success else 0)
        if start_at:
            filters.append("created_at >= %s")
            params.append(start_at)
        if end_at:
            filters.append("created_at <= %s")
            params.append(end_at)
        return self._paged_query(
            table_sql="FROM bot_ai_call_log",
            filters=filters,
            params=params,
            order_by="created_at DESC, id DESC",
            page=page,
            page_size=page_size,
            columns=(
                "id, session_type, session_id, message_table, message_row_id, stage, model_name, "
                "fallback_index, allow_tools, failure_reason, is_success, latency_ms, request_excerpt, created_at"
            ),
        )

    def _paged_query(
        self,
        *,
        table_sql: str,
        filters: list[str],
        params: list[Any],
        order_by: str,
        page: int,
        page_size: int,
        columns: str,
    ) -> dict[str, Any]:
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        where_sql = f" WHERE {' AND '.join(filters)}" if filters else ""
        count_row = database.fetch_one(
            f"SELECT COUNT(*) AS total {table_sql}{where_sql}",
            tuple(params),
        )
        total = int(count_row["total"] or 0) if count_row else 0
        rows = database.fetch_all(
            f"SELECT {columns} {table_sql}{where_sql} ORDER BY {order_by} LIMIT %s OFFSET %s",
            tuple([*params, safe_page_size, (safe_page - 1) * safe_page_size]),
        )
        return {
            "items": rows,
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
        }

    def _count(self, sql: str, params: tuple[Any, ...]) -> int:
        row = database.fetch_one(sql, params)
        return int(row["total"] or 0) if row else 0

    def _log_config_change(
        self,
        *,
        config_domain: str,
        scope_ref: str,
        change_type: str,
        before_json: Any,
        after_json: Any,
        changed_by: str,
    ) -> None:
        database.execute(
            """
            INSERT INTO bot_config_change_log(
                config_domain, scope_ref, change_type, before_json, after_json, changed_by
            ) VALUES(%s, %s, %s, %s, %s, %s)
            """,
            (
                config_domain,
                scope_ref,
                change_type,
                dumps_json(before_json) if before_json is not None else None,
                dumps_json(after_json) if after_json is not None else None,
                changed_by,
            ),
        )

    def _find_secret_public(self, secret_key: str) -> dict[str, Any] | None:
        for item in self.secret_service.list_secrets():
            if item["secret_key"] == secret_key:
                return item
        return None

    def _find_admin_user(self, user_id: int) -> dict[str, Any] | None:
        for item in self.admin_auth_service.list_admin_users():
            if int(item["user_id"]) == int(user_id):
                return item
        return None

    def _find_tool_config(self, tool_name: str) -> dict[str, Any] | None:
        rows = [item for item in self.list_tools() if str(item.get("tool_name")) == str(tool_name)]
        return rows[0] if rows else None
