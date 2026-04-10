"""Admin authentication service."""

from __future__ import annotations

import hmac
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..application.secret_service import SecretService
from ..core.config import settings
from ..core.logging import get_logger
from ..infrastructure.database import database

logger = get_logger("后台鉴权")


class AdminAuthService:
    """Cookie and token based admin authentication."""

    session_cookie_name = "xiaomiao_admin_session"
    session_max_age_seconds = 7 * 24 * 60 * 60

    def __init__(self, secret_service: SecretService) -> None:
        self.secret_service = secret_service

    def bootstrap(self) -> None:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_admin_user (
                user_id BIGINT NOT NULL,
                nickname VARCHAR(255) NULL,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='后台管理员用户表'
            """,
            (),
        )
        total = database.fetch_one("SELECT COUNT(*) AS total FROM bot_admin_user", ())
        if not total or int(total["total"] or 0) == 0:
            database.execute(
                """
                INSERT INTO bot_admin_user(user_id, nickname, is_active)
                VALUES(%s, %s, 1)
                """,
                (settings.admin_uid, f"管理员{settings.admin_uid}"),
            )
            logger.info("管理员白名单为空，已自动写入默认管理员: %s", settings.admin_uid)

    def login(self, qq: int, token: str) -> dict[str, Any]:
        self._validate_token(token)
        admin_user = self._get_admin_user(qq)
        if not admin_user or not bool(admin_user.get("is_active")):
            raise PermissionError("当前 QQ 不在管理员白名单中")
        return {
            "user_id": int(admin_user["user_id"]),
            "nickname": str(admin_user.get("nickname") or admin_user["user_id"]),
        }

    def get_current_admin(
        self,
        *,
        session_cookie: str | None,
        x_admin_token: str | None,
    ) -> dict[str, Any]:
        if x_admin_token:
            self._validate_token(x_admin_token)
            return {
                "user_id": None,
                "nickname": "token-admin",
                "auth_mode": "token",
            }
        if not session_cookie:
            raise PermissionError("未登录")
        payload = self._loads_session(session_cookie)
        admin_user = self._get_admin_user(int(payload["user_id"]))
        if not admin_user or not bool(admin_user.get("is_active")):
            raise PermissionError("管理员身份已失效")
        return {
            "user_id": int(admin_user["user_id"]),
            "nickname": str(admin_user.get("nickname") or admin_user["user_id"]),
            "auth_mode": "cookie",
        }

    def create_session_cookie(self, user_id: int, nickname: str) -> str:
        return self._serializer().dumps({"user_id": user_id, "nickname": nickname})

    def list_admin_users(self) -> list[dict[str, Any]]:
        return database.fetch_all(
            """
            SELECT user_id, nickname, is_active, created_at, updated_at
            FROM bot_admin_user
            ORDER BY user_id ASC
            """,
            (),
        )

    def create_admin_user(self, user_id: int, nickname: str | None, *, is_active: bool) -> dict[str, Any]:
        database.execute(
            """
            INSERT INTO bot_admin_user(user_id, nickname, is_active)
            VALUES(%s, %s, %s)
            ON DUPLICATE KEY UPDATE nickname=VALUES(nickname), is_active=VALUES(is_active)
            """,
            (user_id, nickname, 1 if is_active else 0),
        )
        return self._get_admin_user(user_id) or {
            "user_id": user_id,
            "nickname": nickname,
            "is_active": 1 if is_active else 0,
        }

    def update_admin_user(
        self,
        user_id: int,
        *,
        nickname: str | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any]:
        row = self._get_admin_user(user_id)
        if not row:
            raise ValueError("管理员不存在")
        database.execute(
            """
            UPDATE bot_admin_user
            SET nickname=%s, is_active=%s
            WHERE user_id=%s
            """,
            (
                nickname if nickname is not None else row.get("nickname"),
                1 if (is_active if is_active is not None else bool(row.get("is_active"))) else 0,
                user_id,
            ),
        )
        return self._get_admin_user(user_id) or row

    def _get_admin_user(self, user_id: int) -> dict[str, Any] | None:
        return database.fetch_one(
            """
            SELECT user_id, nickname, is_active, created_at, updated_at
            FROM bot_admin_user
            WHERE user_id=%s
            LIMIT 1
            """,
            (user_id,),
        )

    def _validate_token(self, token: str) -> None:
        current_token = self.secret_service.get_secret("ADMIN_API_TOKEN", settings.admin_api_token)
        if current_token and not hmac.compare_digest(token or "", current_token):
            raise PermissionError("后台令牌无效")

    def _serializer(self) -> URLSafeTimedSerializer:
        secret = self.secret_service.get_secret("ADMIN_API_TOKEN", settings.admin_api_token) or "xiaomiao-admin"
        return URLSafeTimedSerializer(secret_key=secret, salt="xiaomiao-admin-session")

    def _loads_session(self, session_cookie: str) -> dict[str, Any]:
        try:
            data = self._serializer().loads(session_cookie, max_age=self.session_max_age_seconds)
        except SignatureExpired as exc:
            raise PermissionError("登录已过期") from exc
        except BadSignature as exc:
            raise PermissionError("登录态无效") from exc
        if not isinstance(data, dict) or "user_id" not in data:
            raise PermissionError("登录态无效")
        return data
