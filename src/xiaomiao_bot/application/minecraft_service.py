"""Minecraft notify service."""

from __future__ import annotations

import datetime as dt

from nonebot import get_bot

from ..application.secret_service import SecretService, secret_service
from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger("MinecraftService")


class MinecraftService:
    """Handle Minecraft restart notifications."""

    def __init__(self, secret_service_instance: SecretService | None = None) -> None:
        self.secret_service = secret_service_instance or secret_service

    async def notify_restart(self, message: str, secret: str) -> dict:
        current_secret = self.secret_service.get_secret(
            "MINECRAFT_API_SECRET",
            settings.minecraft_api_secret,
        )
        if secret != current_secret:
            logger.warning("unauthorized minecraft notify request")
            raise PermissionError("Invalid secret")

        bot = get_bot()
        notify_msg = (
            "⚠️ Minecraft服务器通知\n\n"
            f"{message}\n\n"
            f"时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if settings.minecraft_notify_group:
            await bot.send_group_msg(group_id=settings.minecraft_notify_group, message=notify_msg)
            return {"status": "success", "message": "通知已发送"}
        return {"status": "success", "message": "MINECRAFT_NOTIFY_GROUP 未配置，已跳过发送"}
