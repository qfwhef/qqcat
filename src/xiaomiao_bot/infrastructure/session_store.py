"""Session persistence in MySQL V2 schema."""

from __future__ import annotations

import json
import re
from datetime import datetime
from threading import Lock
from typing import Any

from nonebot.adapters.onebot.v11 import Event, GroupMessageEvent

from ..core.config import settings
from ..core.logging import get_logger
from ..domain.models import HistoryItem, SessionScope, SummaryState
from ..infrastructure.database import database, dumps_json
from ..infrastructure.runtime_config_store import runtime_config_store

logger = get_logger("会话存储")

_SAFE_TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


class SessionStore:
    """MySQL-backed session state and memory."""

    def __init__(self) -> None:
        self._schema_lock = Lock()
        self._registry_schema_ready = False
        self._known_tables: set[str] = set()

    @staticmethod
    def get_scope(event: Event) -> SessionScope:
        if isinstance(event, GroupMessageEvent):
            return SessionScope(session_type="group", session_id=int(event.group_id))
        return SessionScope(session_type="private", session_id=int(event.user_id))

    def is_sleeping(self, event: Event) -> bool:
        row = self._get_config_row(self.get_scope(event))
        return bool(row and row.get("is_sleeping"))

    def set_sleeping(self, event: Event, sleeping: bool) -> None:
        scope = self.get_scope(event)
        if scope.session_type == "group":
            database.execute(
                """
                INSERT INTO bot_group_config(group_id, reply_rate, is_sleeping, enable_ai, enable_summary)
                VALUES(%s, %s, %s, 1, 1)
                ON DUPLICATE KEY UPDATE is_sleeping=VALUES(is_sleeping)
                """,
                (scope.session_id, self.get_reply_rate(event, 100), 1 if sleeping else 0),
            )
        else:
            database.execute(
                """
                INSERT INTO bot_private_config(user_id, user_nickname, reply_rate, is_sleeping, enable_ai, enable_summary)
                VALUES(%s, %s, %s, %s, 1, 1)
                ON DUPLICATE KEY UPDATE user_nickname=VALUES(user_nickname), is_sleeping=VALUES(is_sleeping)
                """,
                (
                    scope.session_id,
                    self._get_user_nickname(event),
                    self.get_reply_rate(event, 100),
                    1 if sleeping else 0,
                ),
            )
        logger.info("写入睡眠状态: session=%s:%s sleeping=%s", scope.session_type, scope.session_id, sleeping)

    def get_reply_rate(self, event: Event, fallback: int) -> int:
        row = self._get_config_row(self.get_scope(event))
        try:
            return int(row["reply_rate"]) if row and row.get("reply_rate") is not None else fallback
        except Exception:
            return fallback

    def set_reply_rate(self, event: Event, rate: int) -> None:
        scope = self.get_scope(event)
        if scope.session_type == "group":
            database.execute(
                """
                INSERT INTO bot_group_config(group_id, reply_rate, is_sleeping, enable_ai, enable_summary)
                VALUES(%s, %s, %s, 1, 1)
                ON DUPLICATE KEY UPDATE reply_rate=VALUES(reply_rate)
                """,
                (scope.session_id, int(rate), 1 if self.is_sleeping(event) else 0),
            )
        else:
            database.execute(
                """
                INSERT INTO bot_private_config(user_id, user_nickname, reply_rate, is_sleeping, enable_ai, enable_summary)
                VALUES(%s, %s, %s, %s, 1, 1)
                ON DUPLICATE KEY UPDATE user_nickname=VALUES(user_nickname), reply_rate=VALUES(reply_rate)
                """,
                (
                    scope.session_id,
                    self._get_user_nickname(event),
                    int(rate),
                    1 if self.is_sleeping(event) else 0,
                ),
            )
        logger.info("写入回复率: session=%s:%s rate=%s", scope.session_type, scope.session_id, rate)

    def append_user_message(self, event: Event, content: str, *, is_at_bot: bool) -> int:
        scope = self.get_scope(event)
        row = self._build_user_message_row(event, scope, content, is_at_bot=is_at_bot)
        row_id = self._insert_message_row(scope, row, display_name=self._scope_display_name(scope, event))
        logger.info("写入用户消息: session=%s:%s row_id=%s", scope.session_type, scope.session_id, row_id)
        return row_id

    def append_assistant_message(self, event: Event, content: str, *, model_name: str | None = None) -> int:
        scope = self.get_scope(event)
        row = self._build_assistant_message_row(event, scope, content, model_name=model_name)
        row_id = self._insert_message_row(scope, row, display_name=self._scope_display_name(scope, event))
        logger.info(
            "写入AI回复消息: session=%s:%s row_id=%s model=%s",
            scope.session_type,
            scope.session_id,
            row_id,
            model_name or "",
        )
        return row_id

    def append_tool_message(
        self,
        event: Event,
        *,
        tool_name: str,
        tool_args: dict[str, Any] | None,
        tool_result: dict[str, Any],
    ) -> int:
        scope = self.get_scope(event)
        row = self._build_tool_message_row(
            event,
            scope,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
        )
        row_id = self._insert_message_row(scope, row, display_name=self._scope_display_name(scope, event))
        logger.info(
            "写入工具消息: session=%s:%s row_id=%s tool=%s",
            scope.session_type,
            scope.session_id,
            row_id,
            tool_name,
        )
        return row_id

    def log_ai_call(
        self,
        event: Event,
        *,
        stage: str,
        model_name: str,
        fallback_index: int,
        allow_tools: bool,
        is_success: bool,
        failure_reason: str | None = None,
        latency_ms: int | None = None,
        request_excerpt: str | None = None,
        message_row_id: int | None = None,
    ) -> int:
        scope = self.get_scope(event)
        message_table = self.get_message_table_name(scope.session_type, scope.session_id) or self._compose_message_table_name(scope)
        return database.insert(
            """
            INSERT INTO bot_ai_call_log(
                session_type, session_id, message_table, message_row_id, stage,
                model_name, fallback_index, allow_tools, failure_reason, is_success,
                latency_ms, request_excerpt
            ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                scope.session_type,
                scope.session_id,
                message_table,
                message_row_id,
                stage,
                model_name,
                int(fallback_index),
                1 if allow_tools else 0,
                failure_reason,
                1 if is_success else 0,
                latency_ms,
                (request_excerpt or "")[:500] or None,
            ),
        )

    def get_history_entries(self, event: Event) -> list[dict[str, Any]]:
        scope = self.get_scope(event)
        table_name = self._message_table(scope)
        if not table_name:
            return []
        state = self.get_summary_state(event)
        rows = database.fetch_all(
            f"""
            SELECT id, role, content_text, model_name, created_at
            FROM (
                SELECT id, role, content_text, model_name, created_at
                FROM {self._quoted_table_name(table_name)}
                WHERE id > %s
                ORDER BY id DESC
                LIMIT %s
            ) recent
            ORDER BY id ASC
            """,
            (
                state.last_summary_message_id,
                int(runtime_config_store.get_runtime_snapshot().get("max_history", settings.max_history)) * 2,
            ),
        )
        return rows

    def get_history(self, event: Event) -> list[HistoryItem]:
        return [
            {"role": str(row["role"]), "content": str(row["content_text"])}
            for row in self.get_history_entries(event)
        ]

    def save_history(self, event: Event, history: list[HistoryItem], max_history: int) -> None:
        scope = self.get_scope(event)
        logger.warning("save_history 仍被调用，已退化为兼容模式: session=%s:%s", scope.session_type, scope.session_id)
        current = self.get_history(event)
        if history == current:
            return
        table_name = self._message_table(scope, create=True, display_name=self._scope_display_name(scope, event))
        active_ids = [int(row["id"]) for row in self.get_history_entries(event)]
        if active_ids:
            database.execute(
                f"DELETE FROM {self._quoted_table_name(table_name)} WHERE id >= %s AND id <= %s",
                (min(active_ids), max(active_ids)),
            )
        self._sync_message_registry(scope, display_name=self._scope_display_name(scope, event))
        trimmed = history[-(max_history * 2) :]
        for item in trimmed:
            role = str(item.get('role', 'user'))
            content = str(item.get('content', ''))
            if role == "assistant":
                self.append_assistant_message(event, content)
            else:
                self.append_user_message(event, content, is_at_bot="@小喵" in content)

    def clear_history(self, event: Event) -> None:
        scope = self.get_scope(event)
        logger.info("清空历史记录: session=%s:%s", scope.session_type, scope.session_id)
        message_table = self._message_table(scope)
        summary_table, summary_key = self._summary_table(scope)
        state_table, state_key = self._state_table(scope)
        if message_table:
            database.execute(f"DELETE FROM {self._quoted_table_name(message_table)}", ())
            self._sync_message_registry(scope, display_name=self._scope_display_name(scope, event))
        database.execute(f"DELETE FROM {summary_table} WHERE {summary_key}=%s", (scope.session_id,))
        database.execute(f"DELETE FROM {state_table} WHERE {state_key}=%s", (scope.session_id,))
        logger.info("历史记录已清空: session=%s:%s", scope.session_type, scope.session_id)

    def get_summary(self, event: Event) -> str:
        scope = self.get_scope(event)
        summary_table, summary_key = self._summary_table(scope)
        row = database.fetch_one(
            f"""
            SELECT summary_text
            FROM {summary_table}
            WHERE {summary_key}=%s AND is_active=1
            ORDER BY summary_version DESC, id DESC
            LIMIT 1
            """,
            (scope.session_id,),
        )
        return str(row["summary_text"]).strip() if row else ""

    def save_summary(
        self,
        event: Event,
        summary: str,
        *,
        source_start_message_id: int | None,
        source_end_message_id: int,
        source_message_count: int,
        created_by_model: str | None = None,
    ) -> int:
        scope = self.get_scope(event)
        summary_table, summary_key = self._summary_table(scope)
        state = self.get_summary_state(event)
        version = state.summary_version + 1
        database.execute(
            f"UPDATE {summary_table} SET is_active=0 WHERE {summary_key}=%s",
            (scope.session_id,),
        )
        if scope.session_type == "group":
            database.execute(
                """
                INSERT INTO bot_group_summary(
                    group_id, group_name, summary_version, summary_text, summary_json,
                    source_start_message_id, source_end_message_id, source_message_count,
                    created_by_model, is_active
                ) VALUES(%s, %s, %s, %s, NULL, %s, %s, %s, %s, 1)
                """,
                (
                    scope.session_id,
                    self._get_group_name(event),
                    version,
                    summary,
                    source_start_message_id,
                    source_end_message_id,
                    int(source_message_count),
                    created_by_model,
                ),
            )
        else:
            database.execute(
                """
                INSERT INTO bot_private_summary(
                    peer_user_id, peer_nickname, summary_version, summary_text, summary_json,
                    source_start_message_id, source_end_message_id, source_message_count,
                    created_by_model, is_active
                ) VALUES(%s, %s, %s, %s, NULL, %s, %s, %s, %s, 1)
                """,
                (
                    scope.session_id,
                    self._get_user_nickname(event),
                    version,
                    summary,
                    source_start_message_id,
                    source_end_message_id,
                    int(source_message_count),
                    created_by_model,
                ),
            )
        logger.info(
            "会话摘要保存成功: session=%s:%s version=%s source_end=%s source_count=%s",
            scope.session_type,
            scope.session_id,
            version,
            source_end_message_id,
            source_message_count,
        )
        return version

    def get_history_version(self, event: Event) -> int:
        scope = self.get_scope(event)
        table_name = self._message_table(scope)
        if not table_name:
            return 0
        row = database.fetch_one(
            f"SELECT COUNT(*) AS total FROM {self._quoted_table_name(table_name)}",
            (),
        )
        return int(row["total"] or 0) if row else 0

    def get_summary_state(self, event: Event) -> SummaryState:
        scope = self.get_scope(event)
        state_table, state_key = self._state_table(scope)
        row = database.fetch_one(
            f"""
            SELECT summary_version, last_summary_message_id, summary_cooldown_until
            FROM {state_table}
            WHERE {state_key}=%s
            """,
            (scope.session_id,),
        )
        if not row:
            return SummaryState()
        return SummaryState(
            summary_version=int(row.get("summary_version") or 0),
            last_summary_message_id=int(row.get("last_summary_message_id") or 0),
            cooldown_until=self._datetime_to_timestamp(row.get("summary_cooldown_until")),
        )

    def save_summary_state(
        self,
        event: Event,
        *,
        summary_version: int,
        last_summary_message_id: int,
        cooldown_until: int,
    ) -> None:
        scope = self.get_scope(event)
        state_table, state_key = self._state_table(scope)
        last_message_id = self._get_last_message_id(scope)
        cooldown_dt = datetime.fromtimestamp(cooldown_until) if cooldown_until else None
        database.execute(
            f"""
            INSERT INTO {state_table}({state_key}, last_message_id, last_summary_message_id, summary_version, summary_cooldown_until)
            VALUES(%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                last_message_id=VALUES(last_message_id),
                last_summary_message_id=VALUES(last_summary_message_id),
                summary_version=VALUES(summary_version),
                summary_cooldown_until=VALUES(summary_cooldown_until)
            """,
            (
                scope.session_id,
                last_message_id,
                int(last_summary_message_id),
                int(summary_version),
                cooldown_dt,
            ),
        )
        logger.info(
            "摘要状态已保存: session=%s:%s summary_version=%s last_summary_message_id=%s cooldown_until=%s",
            scope.session_type,
            scope.session_id,
            summary_version,
            last_summary_message_id,
            cooldown_until,
        )

    def ensure_message_registry_schema(self) -> None:
        if self._registry_schema_ready:
            return
        with self._schema_lock:
            if self._registry_schema_ready:
                return
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_message_session_registry (
                    session_type VARCHAR(16) NOT NULL COMMENT '会话类型：group/private',
                    session_id BIGINT NOT NULL COMMENT '群号或QQ号',
                    table_name VARCHAR(64) NOT NULL COMMENT '实际消息表名',
                    display_name VARCHAR(255) NULL COMMENT '会话展示名',
                    total_messages BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '累计消息数',
                    last_message_id BIGINT NULL COMMENT '最新消息主键',
                    last_message_at DATETIME NULL COMMENT '最新消息时间',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                    PRIMARY KEY (session_type, session_id),
                    UNIQUE KEY uk_message_session_table (table_name),
                    KEY idx_message_session_last_time (session_type, last_message_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息分表注册表'
                """,
                (),
            )
            self._registry_schema_ready = True

    def get_message_table_name(self, session_type: str, session_id: int) -> str | None:
        self.ensure_message_registry_schema()
        row = database.fetch_one(
            """
            SELECT table_name
            FROM bot_message_session_registry
            WHERE session_type=%s AND session_id=%s
            """,
            (session_type, int(session_id)),
        )
        return str(row["table_name"]) if row and row.get("table_name") else None

    def list_registered_sessions(self, session_type: str, *, keyword: str = "") -> list[dict[str, Any]]:
        self.ensure_message_registry_schema()
        filters = ["session_type=%s"]
        params: list[Any] = [session_type]
        if keyword.strip():
            filters.append("(CAST(session_id AS CHAR) LIKE %s OR display_name LIKE %s)")
            like = f"%{keyword.strip()}%"
            params.extend([like, like])
        where_sql = f"WHERE {' AND '.join(filters)}"
        return database.fetch_all(
            f"""
            SELECT session_id, display_name, table_name, total_messages, last_message_id, last_message_at, updated_at
            FROM bot_message_session_registry
            {where_sql}
            ORDER BY last_message_at DESC, session_id DESC
            """,
            tuple(params),
        )

    def count_recent_messages(self, *, session_type: str, since: datetime, role: str | None = None) -> int:
        total = 0
        for registry in self.list_registered_sessions(session_type):
            table_name = self._safe_table_name(str(registry["table_name"]))
            sql = f"SELECT COUNT(*) AS total FROM {self._quoted_table_name(table_name)} WHERE created_at >= %s"
            params: tuple[Any, ...] = (since,)
            if role:
                sql += " AND role=%s"
                params = (since, role)
            row = database.fetch_one(sql, params)
            total += int(row["total"] or 0) if row else 0
        return total

    def list_messages_for_admin(
        self,
        *,
        session_type: str,
        session_id: int,
        page: int,
        page_size: int,
        sender_user_id: int | None = None,
        role: str = "",
        keyword: str = "",
        start_at: str = "",
        end_at: str = "",
        is_reply: bool | None = None,
        is_tool: bool | None = None,
    ) -> dict[str, Any]:
        table_name = self.get_message_table_name(session_type, session_id)
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 100))
        if not table_name:
            return {"items": [], "page": safe_page, "page_size": safe_page_size, "total": 0}
        filters: list[str] = []
        params: list[Any] = []
        if sender_user_id is not None:
            filters.append("sender_user_id=%s")
            params.append(sender_user_id)
        if role:
            filters.append("role=%s")
            params.append(role)
        if keyword.strip():
            filters.append("(content_text LIKE %s OR quoted_text LIKE %s OR tool_name LIKE %s)")
            like = f"%{keyword.strip()}%"
            params.extend([like, like, like])
        if start_at:
            filters.append("created_at >= %s")
            params.append(start_at)
        if end_at:
            filters.append("created_at <= %s")
            params.append(end_at)
        if is_reply is not None:
            filters.append("is_reply=%s")
            params.append(1 if is_reply else 0)
        if is_tool is True:
            filters.append("role=%s")
            params.append("tool")
        elif is_tool is False:
            filters.append("role<>%s")
            params.append("tool")
        where_sql = f" WHERE {' AND '.join(filters)}" if filters else ""
        registry = self._registry_row(SessionScope(session_type=session_type, session_id=int(session_id))) or {}
        columns = (
            "id, platform_message_id, role, message_type, content_text, raw_message_json, "
            "sender_user_id, sender_nickname, "
            + ("sender_card, group_name, is_at_bot, " if session_type == "group" else "peer_nickname, ")
            + "is_reply, quoted_platform_message_id, quoted_role, quoted_sender_user_id, "
            "quoted_sender_nickname, quoted_text, tool_name, tool_args_json, model_name, created_at"
        )
        count_row = database.fetch_one(
            f"SELECT COUNT(*) AS total FROM {self._quoted_table_name(table_name)}{where_sql}",
            tuple(params),
        )
        rows = database.fetch_all(
            f"""
            SELECT {columns}
            FROM {self._quoted_table_name(table_name)}
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*params, safe_page_size, (safe_page - 1) * safe_page_size]),
        )
        for item in rows:
            if item.get("tool_args_json") is not None:
                item["tool_args_json"] = self._load_json_like(item["tool_args_json"], {})
            if session_type == "group":
                item["group_id"] = int(session_id)
                item["group_name"] = item.get("group_name") or registry.get("display_name")
            else:
                item["peer_user_id"] = int(session_id)
                item["peer_nickname"] = item.get("peer_nickname") or registry.get("display_name")
        return {
            "items": rows,
            "page": safe_page,
            "page_size": safe_page_size,
            "total": int(count_row["total"] or 0) if count_row else 0,
        }

    def get_message_for_admin(
        self,
        *,
        session_type: str,
        session_id: int,
        message_id: int,
    ) -> dict[str, Any] | None:
        table_name = self.get_message_table_name(session_type, session_id)
        if not table_name:
            return None
        columns = (
            "id, platform_message_id, role, message_type, content_text, raw_message_json, "
            "sender_user_id, sender_nickname, "
            + ("sender_card, group_name, is_at_bot, " if session_type == "group" else "peer_nickname, ")
            + "is_reply, quoted_platform_message_id, quoted_role, quoted_sender_user_id, "
            "quoted_sender_nickname, quoted_text, tool_name, tool_args_json, model_name, created_at"
        )
        row = database.fetch_one(
            f"""
            SELECT {columns}
            FROM {self._quoted_table_name(table_name)}
            WHERE id=%s
            LIMIT 1
            """,
            (int(message_id),),
        )
        if not row:
            return None
        if row.get("tool_args_json") is not None:
            row["tool_args_json"] = self._load_json_like(row["tool_args_json"], {})
        if session_type == "group":
            row["group_id"] = int(session_id)
        else:
            row["peer_user_id"] = int(session_id)
        return row

    def update_message_for_admin(
        self,
        *,
        session_type: str,
        session_id: int,
        message_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        table_name = self.get_message_table_name(session_type, session_id)
        if not table_name:
            return None
        updates: list[str] = []
        params: list[Any] = []
        allowed_fields = [
            "sender_user_id",
            "sender_nickname",
            "role",
            "message_type",
            "content_text",
            "tool_name",
            "model_name",
        ]
        if session_type == "group":
            allowed_fields.extend(["sender_card", "group_name", "is_at_bot"])
        else:
            allowed_fields.append("peer_nickname")
        for field in allowed_fields:
            if field not in payload:
                continue
            value = payload[field]
            if field in {"sender_user_id"} and value is not None:
                value = int(value)
            if field == "is_at_bot":
                value = 1 if bool(value) else 0
            updates.append(f"{field}=%s")
            params.append(value)
        if "tool_args_json" in payload:
            updates.append("tool_args_json=%s")
            params.append(dumps_json(payload["tool_args_json"]) if payload["tool_args_json"] is not None else None)
        if "quoted_text" in payload:
            updates.append("quoted_text=%s")
            params.append(payload["quoted_text"])
        if "is_reply" in payload:
            updates.append("is_reply=%s")
            params.append(1 if bool(payload["is_reply"]) else 0)
        if not updates:
            return self.get_message_for_admin(
                session_type=session_type,
                session_id=session_id,
                message_id=message_id,
            )
        params.append(int(message_id))
        affected = database.execute(
            f"UPDATE {self._quoted_table_name(table_name)} SET {', '.join(updates)} WHERE id=%s",
            tuple(params),
        )
        if affected == 0:
            return None
        scope = SessionScope(session_type=session_type, session_id=int(session_id))
        self._sync_message_registry(scope)
        return self.get_message_for_admin(
            session_type=session_type,
            session_id=session_id,
            message_id=message_id,
        )

    def delete_messages_for_admin(
        self,
        *,
        session_type: str,
        session_id: int,
        message_ids: list[int],
    ) -> int:
        table_name = self.get_message_table_name(session_type, session_id)
        unique_ids = sorted({int(message_id) for message_id in message_ids if message_id is not None})
        if not table_name or not unique_ids:
            return 0
        placeholders = ", ".join(["%s"] * len(unique_ids))
        affected = database.execute(
            f"DELETE FROM {self._quoted_table_name(table_name)} WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        if affected:
            scope = SessionScope(session_type=session_type, session_id=int(session_id))
            self._sync_message_registry(scope)
            self._refresh_or_clear_last_message_state(scope)
        return int(affected)

    @staticmethod
    def _summary_table(scope: SessionScope) -> tuple[str, str]:
        if scope.session_type == "group":
            return "bot_group_summary", "group_id"
        return "bot_private_summary", "peer_user_id"

    @staticmethod
    def _state_table(scope: SessionScope) -> tuple[str, str]:
        if scope.session_type == "group":
            return "bot_group_session_state", "group_id"
        return "bot_private_session_state", "user_id"

    def _get_config_row(self, scope: SessionScope) -> dict[str, Any] | None:
        if scope.session_type == "group":
            return database.fetch_one(
                "SELECT * FROM bot_group_config WHERE group_id=%s",
                (scope.session_id,),
            )
        return database.fetch_one(
            "SELECT * FROM bot_private_config WHERE user_id=%s",
            (scope.session_id,),
        )

    def _insert_message_row(self, scope: SessionScope, row: tuple[Any, ...], *, display_name: str | None) -> int:
        table_name = self._message_table(scope, create=True, display_name=display_name)
        if scope.session_type == "group":
            sql = f"""
                INSERT INTO {self._quoted_table_name(table_name)}(
                    platform_message_id, group_name, sender_user_id, sender_nickname, sender_card,
                    role, message_type, content_text, raw_message_json, is_at_bot, is_reply,
                    quoted_platform_message_id, quoted_role, quoted_sender_user_id, quoted_sender_nickname,
                    quoted_text, tool_name, tool_args_json, model_name, created_at
                ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        else:
            sql = f"""
                INSERT INTO {self._quoted_table_name(table_name)}(
                    platform_message_id, peer_nickname, sender_user_id, sender_nickname,
                    role, message_type, content_text, raw_message_json, is_reply,
                    quoted_platform_message_id, quoted_role, quoted_sender_user_id, quoted_sender_nickname,
                    quoted_text, tool_name, tool_args_json, model_name, created_at
                ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        row_id = database.insert(sql, row)
        self._refresh_last_message_state(scope)
        self._sync_message_registry(scope, display_name=display_name)
        return row_id

    def _build_user_message_row(
        self,
        event: Event,
        scope: SessionScope,
        content: str,
        *,
        is_at_bot: bool,
    ) -> tuple[Any, ...]:
        reply_meta = self._extract_reply_metadata(event, scope)
        platform_message_id = str(getattr(event, "message_id", "") or "") or None
        sender_user_id = int(getattr(event, "user_id", 0) or 0) or None
        sender_nickname = self._get_user_nickname(event)
        sender_card = self._get_user_card(event)
        raw_message_json = dumps_json(
            {
                "message_id": getattr(event, "message_id", None),
                "raw_message": str(getattr(event, "message", "")),
                "plain_text": str(getattr(event, "get_plaintext", lambda: "")() or ""),
            }
        )
        message_type = self._detect_message_type(content)
        created_at = datetime.now()
        if scope.session_type == "group":
            return (
                platform_message_id,
                self._get_group_name(event),
                sender_user_id,
                sender_nickname,
                sender_card,
                "user",
                message_type,
                content,
                raw_message_json,
                1 if is_at_bot else 0,
                1 if reply_meta["quoted_platform_message_id"] else 0,
                reply_meta["quoted_platform_message_id"],
                reply_meta["quoted_role"],
                reply_meta["quoted_sender_user_id"],
                reply_meta["quoted_sender_nickname"],
                reply_meta["quoted_text"],
                None,
                None,
                None,
                created_at,
            )
        return (
            platform_message_id,
            self._get_user_nickname(event),
            sender_user_id,
            sender_nickname,
            "user",
            message_type,
            content,
            raw_message_json,
            1 if reply_meta["quoted_platform_message_id"] else 0,
            reply_meta["quoted_platform_message_id"],
            reply_meta["quoted_role"],
            reply_meta["quoted_sender_user_id"],
            reply_meta["quoted_sender_nickname"],
            reply_meta["quoted_text"],
            None,
            None,
            None,
            created_at,
        )

    def _build_assistant_message_row(
        self,
        event: Event,
        scope: SessionScope,
        content: str,
        *,
        model_name: str | None,
    ) -> tuple[Any, ...]:
        created_at = datetime.now()
        message_type = self._detect_message_type(content)
        if scope.session_type == "group":
            return (
                None,
                self._get_group_name(event),
                None,
                None,
                None,
                "assistant",
                message_type,
                content,
                None,
                0,
                0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                model_name,
                created_at,
            )
        return (
            None,
            self._get_user_nickname(event),
            None,
            None,
            "assistant",
            message_type,
            content,
            None,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            model_name,
            created_at,
        )

    def _build_tool_message_row(
        self,
        event: Event,
        scope: SessionScope,
        *,
        tool_name: str,
        tool_args: dict[str, Any] | None,
        tool_result: dict[str, Any],
    ) -> tuple[Any, ...]:
        created_at = datetime.now()
        content = dumps_json(tool_result)
        tool_args_json = dumps_json(tool_args or {})
        if scope.session_type == "group":
            return (
                None,
                self._get_group_name(event),
                None,
                None,
                None,
                "tool",
                "tool",
                content,
                None,
                0,
                0,
                None,
                None,
                None,
                None,
                None,
                tool_name,
                tool_args_json,
                None,
                created_at,
            )
        return (
            None,
            self._get_user_nickname(event),
            None,
            None,
            "tool",
            "tool",
            content,
            None,
            0,
            None,
            None,
            None,
            None,
            None,
            tool_name,
            tool_args_json,
            None,
            created_at,
        )

    def _refresh_last_message_state(self, scope: SessionScope) -> None:
        state_table, state_key = self._state_table(scope)
        last_message_id = self._get_last_message_id(scope)
        if last_message_id is None:
            return
        current_state = self._get_summary_state_by_scope(scope)
        database.execute(
            f"""
            INSERT INTO {state_table}({state_key}, last_message_id, last_summary_message_id, summary_version)
            VALUES(%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE last_message_id=VALUES(last_message_id)
            """,
            (
                scope.session_id,
                last_message_id,
                current_state.last_summary_message_id,
                current_state.summary_version,
            ),
        )

    def _refresh_or_clear_last_message_state(self, scope: SessionScope) -> None:
        state_table, state_key = self._state_table(scope)
        last_message_id = self._get_last_message_id(scope)
        if last_message_id is None:
            database.execute(
                f"""
                INSERT INTO {state_table}({state_key}, last_message_id)
                VALUES(%s, NULL)
                ON DUPLICATE KEY UPDATE last_message_id=VALUES(last_message_id)
                """,
                (scope.session_id,),
            )
            return
        self._refresh_last_message_state(scope)

    def _get_last_message_id(self, scope: SessionScope) -> int | None:
        table_name = self._message_table(scope)
        if not table_name:
            return None
        row = database.fetch_one(
            f"SELECT MAX(id) AS last_id FROM {self._quoted_table_name(table_name)}",
            (),
        )
        if not row or row.get("last_id") is None:
            return None
        return int(row["last_id"])

    def _get_summary_state_by_scope(self, scope: SessionScope) -> SummaryState:
        state_table, state_key = self._state_table(scope)
        row = database.fetch_one(
            f"""
            SELECT summary_version, last_summary_message_id, summary_cooldown_until
            FROM {state_table}
            WHERE {state_key}=%s
            """,
            (scope.session_id,),
        )
        if not row:
            return SummaryState()
        return SummaryState(
            summary_version=int(row.get("summary_version") or 0),
            last_summary_message_id=int(row.get("last_summary_message_id") or 0),
            cooldown_until=self._datetime_to_timestamp(row.get("summary_cooldown_until")),
        )

    @staticmethod
    def _detect_message_type(content: str) -> str:
        has_image = "[图片" in content
        has_text = bool(re.sub(r"\[图片:[^\]]+\]|\[图片\]", "", content).strip())
        if has_image and has_text:
            return "mixed"
        if has_image:
            return "image"
        return "text"

    def _extract_reply_metadata(self, event: Event, scope: SessionScope) -> dict[str, Any]:
        reply_obj = getattr(event, "reply", None)
        if not reply_obj:
            return {
                "quoted_platform_message_id": None,
                "quoted_role": None,
                "quoted_sender_user_id": None,
                "quoted_sender_nickname": None,
                "quoted_text": None,
            }
        is_dict = isinstance(reply_obj, dict)
        sender = (reply_obj.get("sender") if is_dict else getattr(reply_obj, "sender", None)) or {}
        sender_user_id = getattr(sender, "user_id", None) if not isinstance(sender, dict) else sender.get("user_id")
        sender_nickname = (
            getattr(sender, "card", None) if not isinstance(sender, dict) else sender.get("card")
        ) or (
            getattr(sender, "nickname", None) if not isinstance(sender, dict) else sender.get("nickname")
        )
        quoted_text = str(
            (reply_obj.get("message") if is_dict else getattr(reply_obj, "message", ""))
            or (reply_obj.get("raw_message") if is_dict else getattr(reply_obj, "raw_message", ""))
            or ""
        ).strip() or None
        if quoted_text:
            quoted_text = re.sub(r"\[CQ:[^\]]+\]", "[CQ消息]", quoted_text)
        result = {
            "quoted_platform_message_id": str(
                (reply_obj.get("message_id") if is_dict else getattr(reply_obj, "message_id", None))
                or (reply_obj.get("id") if is_dict else getattr(reply_obj, "id", None))
                or ""
            )
            or None,
            "quoted_role": "user",
            "quoted_sender_user_id": int(sender_user_id) if sender_user_id else None,
            "quoted_sender_nickname": str(sender_nickname).strip() if sender_nickname else None,
            "quoted_text": quoted_text,
        }
        quoted_platform_message_id = result["quoted_platform_message_id"]
        if quoted_platform_message_id:
            db_row = self._find_message_by_platform_id(scope, quoted_platform_message_id)
            if db_row:
                result["quoted_role"] = db_row.get("role") or result["quoted_role"]
                result["quoted_sender_user_id"] = (
                    db_row.get("sender_user_id") or result["quoted_sender_user_id"]
                )
                result["quoted_sender_nickname"] = (
                    db_row.get("sender_card")
                    or db_row.get("sender_nickname")
                    or result["quoted_sender_nickname"]
                )
                result["quoted_text"] = db_row.get("content_text") or result["quoted_text"]
        return result

    def _find_message_by_platform_id(
        self,
        scope: SessionScope,
        platform_message_id: str,
    ) -> dict[str, Any] | None:
        table_name = self._message_table(scope)
        if not table_name:
            return None
        columns = "role, sender_user_id, sender_nickname, content_text"
        if scope.session_type == "group":
            columns = "role, sender_user_id, sender_nickname, sender_card, content_text"
        return database.fetch_one(
            f"""
            SELECT {columns}
            FROM {self._quoted_table_name(table_name)}
            WHERE platform_message_id=%s
            LIMIT 1
            """,
            (platform_message_id,),
        )

    def _message_table(
        self,
        scope: SessionScope,
        *,
        create: bool = False,
        display_name: str | None = None,
    ) -> str | None:
        registry = self._registry_row(scope)
        if registry and registry.get("table_name"):
            table_name = self._safe_table_name(str(registry["table_name"]))
            if create:
                self._ensure_dynamic_message_table(scope, table_name)
                if display_name:
                    self._sync_message_registry(scope, display_name=display_name)
            return table_name
        if not create:
            return None
        table_name = self._compose_message_table_name(scope)
        self._ensure_dynamic_message_table(scope, table_name)
        self._sync_message_registry(scope, display_name=display_name)
        return table_name

    def _registry_row(self, scope: SessionScope) -> dict[str, Any] | None:
        self.ensure_message_registry_schema()
        return database.fetch_one(
            """
            SELECT session_type, session_id, table_name, display_name, total_messages, last_message_id, last_message_at
            FROM bot_message_session_registry
            WHERE session_type=%s AND session_id=%s
            """,
            (scope.session_type, scope.session_id),
        )

    def _ensure_dynamic_message_table(self, scope: SessionScope, table_name: str) -> None:
        self.ensure_message_registry_schema()
        safe_name = self._safe_table_name(table_name)
        if safe_name in self._known_tables:
            return
        with self._schema_lock:
            if safe_name in self._known_tables:
                return
            if scope.session_type == "group":
                database.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._quoted_table_name(safe_name)} (
                        id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                        platform_message_id VARCHAR(64) NULL COMMENT '平台原始消息ID',
                        group_name VARCHAR(255) NULL COMMENT '群昵称',
                        sender_user_id BIGINT NULL COMMENT '发送者QQ',
                        sender_nickname VARCHAR(255) NULL COMMENT '发送者昵称',
                        sender_card VARCHAR(255) NULL COMMENT '发送者群昵称',
                        role VARCHAR(16) NOT NULL COMMENT '消息角色：user/assistant/system/tool',
                        message_type VARCHAR(32) NOT NULL DEFAULT 'text' COMMENT '消息类型：text/image/mixed/tool',
                        content_text LONGTEXT NOT NULL COMMENT '标准化后的消息文本',
                        raw_message_json LONGTEXT NULL COMMENT '原始消息 JSON',
                        is_at_bot TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否@机器人',
                        is_reply TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为引用消息',
                        quoted_platform_message_id VARCHAR(64) NULL COMMENT '被引用的平台消息ID',
                        quoted_role VARCHAR(16) NULL COMMENT '被引用消息角色',
                        quoted_sender_user_id BIGINT NULL COMMENT '被引用消息发送者QQ',
                        quoted_sender_nickname VARCHAR(255) NULL COMMENT '被引用消息发送者昵称',
                        quoted_text LONGTEXT NULL COMMENT '被引用消息文本',
                        tool_name VARCHAR(64) NULL COMMENT '工具名称',
                        tool_args_json JSON NULL COMMENT '工具参数',
                        model_name VARCHAR(128) NULL COMMENT '本条消息使用的模型',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '消息时间',
                        PRIMARY KEY (id),
                        UNIQUE KEY uk_platform_message (platform_message_id),
                        KEY idx_message_time (created_at),
                        KEY idx_sender_time (sender_user_id, created_at),
                        KEY idx_role_time (role, created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='群聊动态消息表'
                    """,
                    (),
                )
            else:
                database.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._quoted_table_name(safe_name)} (
                        id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                        platform_message_id VARCHAR(64) NULL COMMENT '平台原始消息ID',
                        peer_nickname VARCHAR(255) NULL COMMENT '私聊对端昵称',
                        sender_user_id BIGINT NULL COMMENT '发送方QQ',
                        sender_nickname VARCHAR(255) NULL COMMENT '发送方昵称',
                        role VARCHAR(16) NOT NULL COMMENT '消息角色：user/assistant/system/tool',
                        message_type VARCHAR(32) NOT NULL DEFAULT 'text' COMMENT '消息类型：text/image/mixed/tool',
                        content_text LONGTEXT NOT NULL COMMENT '标准化后的消息文本',
                        raw_message_json LONGTEXT NULL COMMENT '原始消息 JSON',
                        is_reply TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为引用消息',
                        quoted_platform_message_id VARCHAR(64) NULL COMMENT '被引用的平台消息ID',
                        quoted_role VARCHAR(16) NULL COMMENT '被引用消息角色',
                        quoted_sender_user_id BIGINT NULL COMMENT '被引用消息发送者QQ',
                        quoted_sender_nickname VARCHAR(255) NULL COMMENT '被引用消息发送者昵称',
                        quoted_text LONGTEXT NULL COMMENT '被引用消息文本',
                        tool_name VARCHAR(64) NULL COMMENT '工具名称',
                        tool_args_json JSON NULL COMMENT '工具参数',
                        model_name VARCHAR(128) NULL COMMENT '本条消息使用的模型',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '消息时间',
                        PRIMARY KEY (id),
                        UNIQUE KEY uk_platform_message (platform_message_id),
                        KEY idx_message_time (created_at),
                        KEY idx_sender_time (sender_user_id, created_at),
                        KEY idx_role_time (role, created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='私聊动态消息表'
                    """,
                    (),
                )
            self._known_tables.add(safe_name)

    def _sync_message_registry(self, scope: SessionScope, *, display_name: str | None = None) -> None:
        table_name = self._message_table(scope, create=False)
        if not table_name:
            return
        stats = database.fetch_one(
            f"""
            SELECT COUNT(*) AS total_messages, MAX(id) AS last_message_id, MAX(created_at) AS last_message_at
            FROM {self._quoted_table_name(table_name)}
            """,
            (),
        ) or {}
        existing = self._registry_row(scope) or {}
        final_display_name = display_name or existing.get("display_name") or str(scope.session_id)
        database.execute(
            """
            INSERT INTO bot_message_session_registry(
                session_type, session_id, table_name, display_name, total_messages, last_message_id, last_message_at
            ) VALUES(%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                table_name=VALUES(table_name),
                display_name=COALESCE(VALUES(display_name), display_name),
                total_messages=VALUES(total_messages),
                last_message_id=VALUES(last_message_id),
                last_message_at=VALUES(last_message_at)
            """,
            (
                scope.session_type,
                scope.session_id,
                table_name,
                final_display_name,
                int(stats.get("total_messages") or 0),
                stats.get("last_message_id"),
                stats.get("last_message_at"),
            ),
        )

    @staticmethod
    def _compose_message_table_name(scope: SessionScope) -> str:
        prefix = "bot_group_message_" if scope.session_type == "group" else "bot_private_message_"
        return f"{prefix}{scope.session_id}"

    @staticmethod
    def _safe_table_name(name: str) -> str:
        if not _SAFE_TABLE_NAME_RE.fullmatch(name):
            raise ValueError(f"非法表名: {name}")
        return name

    @classmethod
    def _quoted_table_name(cls, name: str) -> str:
        return f"`{cls._safe_table_name(name)}`"

    @staticmethod
    def _datetime_to_timestamp(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, datetime):
            return int(value.timestamp())
        if isinstance(value, str):
            try:
                return int(datetime.fromisoformat(value).timestamp())
            except Exception:
                return 0
        return 0

    @staticmethod
    def _load_json_like(raw: Any, default: Any) -> Any:
        if raw is None:
            return default
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(str(raw))
        except Exception:
            return default

    @staticmethod
    def _get_user_nickname(event: Event) -> str | None:
        sender = getattr(event, "sender", None)
        return (
            getattr(sender, "nickname", None)
            or getattr(sender, "card", None)
            or str(getattr(event, "user_id", "")) or None
        )

    @staticmethod
    def _get_user_card(event: Event) -> str | None:
        sender = getattr(event, "sender", None)
        return getattr(sender, "card", None) or getattr(sender, "nickname", None) or None

    @staticmethod
    def _get_group_name(event: Event) -> str | None:
        return getattr(event, "group_name", None) or None

    def _scope_display_name(self, scope: SessionScope, event: Event) -> str:
        if scope.session_type == "group":
            return self._get_group_name(event) or f"群聊 {scope.session_id}"
        return self._get_user_nickname(event) or f"QQ {scope.session_id}"


session_store = SessionStore()
