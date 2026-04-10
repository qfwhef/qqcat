"""Runtime config stored in MySQL V2 schema."""

from __future__ import annotations

from typing import Any

from ..application.prompt_defaults import (
    DEFAULT_PROMPT_BASE,
    DEFAULT_PROMPT_LOGIC_AT_ME,
    DEFAULT_PROMPT_LOGIC_GROUP,
    DEFAULT_PROMPT_LOGIC_PRIVATE,
    DEFAULT_PROMPT_SUMMARY_SYSTEM,
)
from ..core.config import settings
from ..core.constants import (
    CFG_BLOCKED_GROUPS,
    CFG_BLOCKED_USERS,
    CFG_DEFAULT_REPLY_RATE,
    CFG_ENABLE_SUMMARY_MEMORY,
    CFG_ENABLE_TOOLS,
    CFG_PROMPT_BASE,
    CFG_PROMPT_LOGIC_AT_ME,
    CFG_PROMPT_LOGIC_GROUP,
    CFG_PROMPT_LOGIC_PRIVATE,
    CFG_PROMPT_SUMMARY_SYSTEM,
    CFG_SUMMARY_COOLDOWN_SECONDS,
    CFG_SUMMARY_KEEP_RECENT_MESSAGES,
    CFG_SUMMARY_MIN_NEW_MESSAGES,
    CFG_SUMMARY_ONLY_GROUP,
    CFG_SUMMARY_TRIGGER_ROUNDS,
)
from ..core.logging import get_logger
from ..infrastructure.database import database, dumps_json, loads_json

logger = get_logger("运行时配置")

PROMPT_TYPE_MAP = {
    CFG_PROMPT_BASE: "base",
    CFG_PROMPT_LOGIC_PRIVATE: "private",
    CFG_PROMPT_LOGIC_AT_ME: "at_me",
    CFG_PROMPT_LOGIC_GROUP: "group",
    CFG_PROMPT_SUMMARY_SYSTEM: "summary_system",
}

PROMPT_DEFAULT_MAP = {
    CFG_PROMPT_BASE: DEFAULT_PROMPT_BASE,
    CFG_PROMPT_LOGIC_PRIVATE: DEFAULT_PROMPT_LOGIC_PRIVATE,
    CFG_PROMPT_LOGIC_AT_ME: DEFAULT_PROMPT_LOGIC_AT_ME,
    CFG_PROMPT_LOGIC_GROUP: DEFAULT_PROMPT_LOGIC_GROUP,
    CFG_PROMPT_SUMMARY_SYSTEM: DEFAULT_PROMPT_SUMMARY_SYSTEM,
}

RUNTIME_COLUMN_MAP = {
    "ai_base_url": "ai_base_url",
    "text_model": "text_model",
    "vision_model": "vision_model",
    "text_model_fallback": "text_model_fallback_json",
    "vision_model_fallback": "vision_model_fallback_json",
    CFG_DEFAULT_REPLY_RATE: "default_reply_rate",
    CFG_ENABLE_SUMMARY_MEMORY: "enable_summary_memory",
    CFG_SUMMARY_ONLY_GROUP: "summary_only_group",
    CFG_SUMMARY_TRIGGER_ROUNDS: "summary_trigger_rounds",
    CFG_SUMMARY_KEEP_RECENT_MESSAGES: "summary_keep_recent_messages",
    CFG_SUMMARY_COOLDOWN_SECONDS: "summary_cooldown_seconds",
    CFG_SUMMARY_MIN_NEW_MESSAGES: "summary_min_new_messages",
    CFG_ENABLE_TOOLS: "enable_tools",
    "max_history": "max_history",
    "log_level": "log_level",
}


class RuntimeConfigStore:
    """Global runtime configuration persisted in MySQL."""

    DEFAULTS: dict[str, Any] = {
        CFG_DEFAULT_REPLY_RATE: settings.default_reply_rate,
        CFG_BLOCKED_GROUPS: settings.blocked_groups,
        CFG_BLOCKED_USERS: settings.blocked_users,
        CFG_ENABLE_SUMMARY_MEMORY: True,
        CFG_SUMMARY_ONLY_GROUP: True,
        CFG_SUMMARY_TRIGGER_ROUNDS: 150,
        CFG_SUMMARY_KEEP_RECENT_MESSAGES: 16,
        CFG_SUMMARY_COOLDOWN_SECONDS: 90,
        CFG_SUMMARY_MIN_NEW_MESSAGES: 12,
        CFG_ENABLE_TOOLS: True,
        CFG_PROMPT_BASE: DEFAULT_PROMPT_BASE,
        CFG_PROMPT_LOGIC_PRIVATE: DEFAULT_PROMPT_LOGIC_PRIVATE,
        CFG_PROMPT_LOGIC_AT_ME: DEFAULT_PROMPT_LOGIC_AT_ME,
        CFG_PROMPT_LOGIC_GROUP: DEFAULT_PROMPT_LOGIC_GROUP,
        CFG_PROMPT_SUMMARY_SYSTEM: DEFAULT_PROMPT_SUMMARY_SYSTEM,
    }

    def get(self, key: str, fallback: Any = None) -> Any:
        if key in RUNTIME_COLUMN_MAP:
            row = self._get_active_runtime_row()
            if row and row.get(RUNTIME_COLUMN_MAP[key]) is not None:
                return row[RUNTIME_COLUMN_MAP[key]]
            return self._default_value(key, fallback)

        if key in PROMPT_TYPE_MAP:
            content = self._get_prompt_content(PROMPT_TYPE_MAP[key])
            return content if content is not None else self._default_value(key, fallback)

        if key == CFG_BLOCKED_GROUPS:
            return self._get_blocked_ids("bot_blocked_group", "group_id")

        if key == CFG_BLOCKED_USERS:
            return self._get_blocked_ids("bot_blocked_user", "user_id")

        return self._default_value(key, fallback)

    def set(self, key: str, value: Any) -> None:
        self.update({key: value})

    def update(self, payload: dict[str, Any]) -> None:
        if not payload:
            return

        runtime_updates: dict[str, Any] = {}
        prompt_updates: dict[str, str] = {}
        for key, value in payload.items():
            if key in RUNTIME_COLUMN_MAP:
                runtime_updates[RUNTIME_COLUMN_MAP[key]] = value
            elif key in PROMPT_TYPE_MAP:
                prompt_updates[PROMPT_TYPE_MAP[key]] = str(value)
            elif key == CFG_BLOCKED_GROUPS:
                self._replace_blocked_ids("bot_blocked_group", "group_id", value)
            elif key == CFG_BLOCKED_USERS:
                self._replace_blocked_ids("bot_blocked_user", "user_id", value)

        if runtime_updates:
            self._upsert_runtime_row(runtime_updates)
        for prompt_type, content in prompt_updates.items():
            self._upsert_prompt(prompt_type, content)

    def get_int(self, key: str, fallback: int) -> int:
        try:
            return int(self.get(key, fallback))
        except Exception:
            return fallback

    def get_bool(self, key: str, fallback: bool) -> bool:
        value = self.get(key, fallback)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def get_list(self, key: str, fallback: list[int]) -> list[int]:
        value = self.get(key, fallback)
        if not isinstance(value, list):
            return fallback
        result: list[int] = []
        for item in value:
            try:
                result.append(int(item))
            except Exception:
                continue
        return result

    def get_runtime_snapshot(self) -> dict[str, Any]:
        row = self._get_active_runtime_row() or {}
        raw_text_fallback = row.get("text_model_fallback_json")
        raw_vision_fallback = row.get("vision_model_fallback_json")
        text_model_fallback = (
            raw_text_fallback
            if isinstance(raw_text_fallback, list)
            else loads_json(
                str(raw_text_fallback) if raw_text_fallback is not None else None,
                settings.text_model_fallback,
            )
        )
        vision_model_fallback = (
            raw_vision_fallback
            if isinstance(raw_vision_fallback, list)
            else loads_json(
                str(raw_vision_fallback) if raw_vision_fallback is not None else None,
                settings.vision_model_fallback,
            )
        )
        return {
            "ai_base_url": row.get("ai_base_url") or settings.base_url,
            "text_model": row.get("text_model") or settings.text_model,
            "vision_model": row.get("vision_model") or settings.vision_model,
            "text_model_fallback": text_model_fallback
            if isinstance(text_model_fallback, list)
            else settings.text_model_fallback,
            "vision_model_fallback": vision_model_fallback
            if isinstance(vision_model_fallback, list)
            else settings.vision_model_fallback,
            "default_reply_rate": int(
                row.get("default_reply_rate")
                if row.get("default_reply_rate") is not None
                else settings.default_reply_rate
            ),
            "enable_tools": bool(
                row.get("enable_tools") if row.get("enable_tools") is not None else True
            ),
            "enable_summary_memory": bool(
                row.get("enable_summary_memory")
                if row.get("enable_summary_memory") is not None
                else True
            ),
            "summary_only_group": bool(
                row.get("summary_only_group") if row.get("summary_only_group") is not None else True
            ),
            "summary_trigger_rounds": int(row.get("summary_trigger_rounds") or self.DEFAULTS[CFG_SUMMARY_TRIGGER_ROUNDS]),
            "summary_keep_recent_messages": int(
                row.get("summary_keep_recent_messages") or self.DEFAULTS[CFG_SUMMARY_KEEP_RECENT_MESSAGES]
            ),
            "summary_cooldown_seconds": int(
                row.get("summary_cooldown_seconds") or self.DEFAULTS[CFG_SUMMARY_COOLDOWN_SECONDS]
            ),
            "summary_min_new_messages": int(
                row.get("summary_min_new_messages") or self.DEFAULTS[CFG_SUMMARY_MIN_NEW_MESSAGES]
            ),
            "max_history": int(row.get("max_history") or settings.max_history),
            "log_level": str(row.get("log_level") or "INFO"),
        }

    def get_text_model(self) -> str:
        return str(self.get_runtime_snapshot()["text_model"])

    def get_vision_model(self) -> str:
        return str(self.get_runtime_snapshot()["vision_model"])

    def get_text_model_fallback(self) -> list[str]:
        return [str(item) for item in self.get_runtime_snapshot()["text_model_fallback"]]

    def get_vision_model_fallback(self) -> list[str]:
        return [str(item) for item in self.get_runtime_snapshot()["vision_model_fallback"]]

    def _default_value(self, key: str, fallback: Any) -> Any:
        if fallback is not None:
            return fallback
        return self.DEFAULTS.get(key)

    def _get_active_runtime_row(self) -> dict[str, Any] | None:
        return database.fetch_one(
            """
            SELECT *
            FROM bot_ai_runtime_config
            WHERE config_scope=%s AND scope_ref=%s AND is_active=1
            ORDER BY version DESC, id DESC
            LIMIT 1
            """,
            ("global", "default"),
        )

    def _upsert_runtime_row(self, updates: dict[str, Any]) -> None:
        row = self._get_active_runtime_row()
        if row:
            assignments = ", ".join(f"{column}=%s" for column in updates)
            params = tuple(self._normalize_runtime_value(column, value) for column, value in updates.items()) + (
                row["id"],
            )
            database.execute(
                f"UPDATE bot_ai_runtime_config SET {assignments} WHERE id=%s",
                params,
            )
            logger.info("已更新 AI 运行时配置字段: %s", ",".join(updates.keys()))
            return

        payload = {
            "config_scope": "global",
            "scope_ref": "default",
            "ai_base_url": settings.base_url,
            "text_model": settings.text_model,
            "vision_model": settings.vision_model,
            "text_model_fallback_json": dumps_json(settings.text_model_fallback),
            "vision_model_fallback_json": dumps_json(settings.vision_model_fallback),
            "enable_tools": 1,
            "enable_summary_memory": 1,
            "summary_only_group": 1,
            "summary_trigger_rounds": self.DEFAULTS[CFG_SUMMARY_TRIGGER_ROUNDS],
            "summary_keep_recent_messages": self.DEFAULTS[CFG_SUMMARY_KEEP_RECENT_MESSAGES],
            "summary_cooldown_seconds": self.DEFAULTS[CFG_SUMMARY_COOLDOWN_SECONDS],
            "summary_min_new_messages": self.DEFAULTS[CFG_SUMMARY_MIN_NEW_MESSAGES],
            "default_reply_rate": settings.default_reply_rate,
            "max_history": settings.max_history,
            "log_level": "INFO",
        }
        for column, value in updates.items():
            payload[column] = self._normalize_runtime_value(column, value)
        database.execute(
            """
            INSERT INTO bot_ai_runtime_config(
                config_scope, scope_ref, ai_base_url, text_model, vision_model,
                text_model_fallback_json, vision_model_fallback_json, enable_tools,
                enable_summary_memory, summary_only_group, summary_trigger_rounds,
                summary_keep_recent_messages, summary_cooldown_seconds, summary_min_new_messages, default_reply_rate,
                max_history, log_level, is_active, version
            ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 1)
            """,
            (
                payload["config_scope"],
                payload["scope_ref"],
                payload["ai_base_url"],
                payload["text_model"],
                payload["vision_model"],
                payload["text_model_fallback_json"],
                payload["vision_model_fallback_json"],
                payload["enable_tools"],
                payload["enable_summary_memory"],
                payload["summary_only_group"],
                payload["summary_trigger_rounds"],
                payload["summary_keep_recent_messages"],
                payload["summary_cooldown_seconds"],
                payload["summary_min_new_messages"],
                payload["default_reply_rate"],
                payload["max_history"],
                payload["log_level"],
            ),
        )
        logger.info("已创建 AI 运行时配置记录")

    def update_runtime_settings(self, payload: dict[str, Any]) -> None:
        updates: dict[str, Any] = {}
        for key, value in payload.items():
            column = RUNTIME_COLUMN_MAP.get(key)
            if not column:
                continue
            updates[column] = value
        if updates:
            self._upsert_runtime_row(updates)

    @staticmethod
    def _normalize_runtime_value(column: str, value: Any) -> Any:
        if column in {"enable_tools", "enable_summary_memory", "summary_only_group"}:
            return 1 if bool(value) else 0
        if column in {"text_model_fallback_json", "vision_model_fallback_json"} and not isinstance(value, str):
            return dumps_json(value)
        return value

    def _get_prompt_content(self, prompt_type: str) -> str | None:
        row = database.fetch_one(
            """
            SELECT content
            FROM bot_prompt_template
            WHERE prompt_type=%s AND scope_type=%s AND is_active=1
            ORDER BY version DESC, id DESC
            LIMIT 1
            """,
            (prompt_type, "global"),
        )
        return str(row["content"]) if row and row.get("content") is not None else None

    def _upsert_prompt(self, prompt_type: str, content: str) -> None:
        row = database.fetch_one(
            """
            SELECT id
            FROM bot_prompt_template
            WHERE prompt_type=%s AND scope_type=%s AND is_active=1
            ORDER BY version DESC, id DESC
            LIMIT 1
            """,
            (prompt_type, "global"),
        )
        if row:
            database.execute(
                "UPDATE bot_prompt_template SET content=%s WHERE id=%s",
                (content, row["id"]),
            )
        else:
            database.execute(
                """
                INSERT INTO bot_prompt_template(
                    prompt_type, scope_type, scope_id, title, content, is_active, version
                ) VALUES(%s, %s, NULL, %s, %s, 1, 1)
                """,
                (prompt_type, "global", prompt_type, content),
            )
        logger.info("已更新提示词模板: %s", prompt_type)

    def _get_blocked_ids(self, table_name: str, id_column: str) -> list[int]:
        rows = database.fetch_all(
            f"SELECT {id_column} FROM {table_name} ORDER BY {id_column} ASC",
            (),
        )
        result: list[int] = []
        for row in rows:
            try:
                result.append(int(row[id_column]))
            except Exception:
                continue
        return result

    def _replace_blocked_ids(self, table_name: str, id_column: str, values: Any) -> None:
        normalized: list[int] = []
        for item in values or []:
            try:
                normalized.append(int(item))
            except Exception:
                continue
        database.execute(f"DELETE FROM {table_name}", ())
        if normalized:
            database.execute_many(
                f"INSERT INTO {table_name}({id_column}) VALUES(%s)",
                [(item,) for item in normalized],
            )
        logger.info("已更新黑名单表 %s，数量=%s", table_name, len(normalized))


runtime_config_store = RuntimeConfigStore()
