"""Secret config service."""

from __future__ import annotations

from typing import Any

from ..core.config import settings
from ..core.logging import get_logger
from ..infrastructure.database import database

logger = get_logger("密钥服务")

SECRET_DEFAULTS: dict[str, dict[str, Any]] = {
    "AI_API_KEY": {"env_value": settings.api_key, "value_hint": "AI 模型调用密钥"},
    "SERPER_API_KEY": {"env_value": settings.serper_api_key, "value_hint": "Serper 搜索密钥"},
    "TAVILY_API_KEY": {"env_value": settings.tavily_api_key, "value_hint": "Tavily 搜索密钥"},
    "AMAP_API_KEY": {"env_value": settings.amap_api_key, "value_hint": "高德天气密钥"},
    "ADMIN_API_TOKEN": {"env_value": settings.admin_api_token, "value_hint": "后台管理员令牌"},
    "MINECRAFT_API_SECRET": {
        "env_value": settings.minecraft_api_secret,
        "value_hint": "Minecraft 重启通知签名",
    },
}


class SecretService:
    """Read and update secrets with DB-first fallback."""

    def get_secret(self, secret_key: str, fallback: str = "") -> str:
        row = database.fetch_one(
            """
            SELECT secret_value
            FROM bot_secret_config
            WHERE secret_key=%s
            LIMIT 1
            """,
            (secret_key,),
        )
        if row and row.get("secret_value") is not None:
            return str(row["secret_value"])
        if secret_key in SECRET_DEFAULTS:
            return str(SECRET_DEFAULTS[secret_key]["env_value"] or fallback)
        return fallback

    def list_secrets(self) -> list[dict[str, Any]]:
        rows = {
            str(row["secret_key"]): row
            for row in database.fetch_all(
                """
                SELECT secret_key, secret_value, value_hint, is_encrypted, updated_at
                FROM bot_secret_config
                ORDER BY secret_key ASC
                """,
                (),
            )
        }
        result: list[dict[str, Any]] = []
        for secret_key, meta in SECRET_DEFAULTS.items():
            row = rows.get(secret_key)
            value = (
                str(row["secret_value"])
                if row and row.get("secret_value") is not None
                else str(meta["env_value"] or "")
            )
            result.append(
                {
                    "secret_key": secret_key,
                    "masked_value": self.mask_secret(value),
                    "value_hint": str(
                        (row.get("value_hint") if row else None) or meta["value_hint"] or ""
                    ),
                    "is_configured": bool(value),
                    "is_encrypted": bool(row.get("is_encrypted")) if row else False,
                    "updated_at": row.get("updated_at") if row else None,
                    "source": "db" if row else "env",
                }
            )
        return result

    def update_secret(
        self,
        secret_key: str,
        secret_value: str,
        *,
        updated_by: str,
        value_hint: str | None = None,
    ) -> dict[str, Any]:
        default_hint = SECRET_DEFAULTS.get(secret_key, {}).get("value_hint", "")
        database.execute(
            """
            INSERT INTO bot_secret_config(secret_key, secret_value, value_hint, is_encrypted, updated_by)
            VALUES(%s, %s, %s, 0, %s)
            ON DUPLICATE KEY UPDATE
                secret_value=VALUES(secret_value),
                value_hint=VALUES(value_hint),
                is_encrypted=VALUES(is_encrypted),
                updated_by=VALUES(updated_by)
            """,
            (secret_key, secret_value, value_hint or default_hint, updated_by),
        )
        logger.info("已更新密钥配置: %s", secret_key)
        row = database.fetch_one(
            """
            SELECT secret_key, value_hint, is_encrypted, updated_at
            FROM bot_secret_config
            WHERE secret_key=%s
            LIMIT 1
            """,
            (secret_key,),
        )
        return {
            "secret_key": secret_key,
            "masked_value": self.mask_secret(secret_value),
            "value_hint": (row or {}).get("value_hint") or default_hint,
            "is_configured": bool(secret_value),
            "is_encrypted": bool((row or {}).get("is_encrypted")),
            "updated_at": (row or {}).get("updated_at"),
            "source": "db",
        }

    @staticmethod
    def mask_secret(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) <= 6:
            return "*" * len(text)
        return f"{text[:3]}***{text[-3:]}"


secret_service = SecretService()
