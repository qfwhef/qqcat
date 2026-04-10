"""Minecraft notify service."""

from __future__ import annotations

import datetime as dt
from typing import Any

from nonebot import get_bot

from ..application.secret_service import SecretService, secret_service
from ..core.config import settings
from ..core.logging import get_logger
from ..infrastructure.database import database, dumps_json, loads_json

logger = get_logger("MinecraftService")


class MinecraftService:
    """Handle Minecraft restart notifications."""

    def __init__(self, secret_service_instance: SecretService | None = None) -> None:
        self.secret_service = secret_service_instance or secret_service
        self._ensure_runtime_table()

    def _ensure_runtime_table(self) -> None:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_minecraft_runtime_config (
                id BIGINT NOT NULL AUTO_INCREMENT,
                config_scope VARCHAR(32) NOT NULL DEFAULT 'global',
                scope_ref VARCHAR(64) NOT NULL DEFAULT 'default',
                notify_group_ids_json JSON NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uk_minecraft_runtime_scope (config_scope, scope_ref)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Minecraft 运行时配置表'
            """,
            (),
        )

    def get_runtime_config(self) -> dict[str, Any]:
        row = database.fetch_one(
            """
            SELECT notify_group_ids_json, updated_at
            FROM bot_minecraft_runtime_config
            WHERE config_scope=%s AND scope_ref=%s
            LIMIT 1
            """,
            ("global", "default"),
        )
        if row and row.get("notify_group_ids_json") is not None:
            raw = row["notify_group_ids_json"]
            notify_group_ids = raw if isinstance(raw, list) else loads_json(str(raw), [])
            if not isinstance(notify_group_ids, list):
                notify_group_ids = []
            groups = [int(item) for item in notify_group_ids if str(item).strip()]
            return {
                "minecraft_notify_groups": groups,
                "updated_at": row.get("updated_at"),
            }
        fallback_groups = [int(settings.minecraft_notify_group)] if int(settings.minecraft_notify_group or 0) else []
        return {"minecraft_notify_groups": fallback_groups, "updated_at": None}

    def update_runtime_config(self, *, minecraft_notify_groups: list[int]) -> dict[str, Any]:
        normalized = sorted({int(item) for item in minecraft_notify_groups if int(item) > 0})
        database.execute(
            """
            INSERT INTO bot_minecraft_runtime_config(config_scope, scope_ref, notify_group_ids_json)
            VALUES(%s, %s, %s)
            ON DUPLICATE KEY UPDATE notify_group_ids_json=VALUES(notify_group_ids_json)
            """,
            ("global", "default", dumps_json(normalized)),
        )
        return self.get_runtime_config()

    def get_allowed_groups(self) -> list[int]:
        return list(self.get_runtime_config().get("minecraft_notify_groups") or [])

    async def notify_restart(self, message: str, secret: str, group_ids: list[int] | None = None) -> dict:
        current_secret = self.secret_service.get_secret(
            "MINECRAFT_API_SECRET",
            settings.minecraft_api_secret,
        )
        if secret != current_secret:
            logger.warning("unauthorized minecraft notify request")
            raise PermissionError("Invalid secret")

        bot = get_bot()
        allowed_groups = self.get_allowed_groups()
        if not allowed_groups:
            return {"status": "success", "message": "Minecraft 通知群白名单未配置，已跳过发送"}

        requested_groups = sorted({int(item) for item in (group_ids or []) if int(item) > 0})
        if requested_groups:
            forbidden = [group_id for group_id in requested_groups if group_id not in allowed_groups]
            if forbidden:
                logger.warning("minecraft notify rejected, groups not in whitelist: %s", forbidden)
                raise PermissionError("Target groups are not in whitelist")
            target_groups = requested_groups
        else:
            target_groups = allowed_groups

        notify_msg = (
            "⚠️ Minecraft服务器通知\n\n"
            f"{message}\n\n"
            f"时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        for group_id in target_groups:
            await bot.send_group_msg(group_id=group_id, message=notify_msg)
        return {
            "status": "success",
            "message": f"通知已发送到 {len(target_groups)} 个群",
            "group_ids": target_groups,
        }
