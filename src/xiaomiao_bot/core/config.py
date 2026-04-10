"""Application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from openai import AsyncOpenAI


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        os.environ.setdefault(key, value)


def _bootstrap_env() -> None:
    project_root = Path(__file__).resolve().parents[3]
    base_env = project_root / ".env"
    _load_env_file(base_env)
    env_name = os.getenv("ENVIRONMENT", "").strip()
    if env_name:
        _load_env_file(project_root / f".env.{env_name}")


_bootstrap_env()


def _parse_int_list(value: str) -> list[int]:
    result: list[int] = []
    normalized = value.strip().strip("[]")
    for item in normalized.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError:
            continue
    return result


def _parse_str_list(value: str) -> list[str]:
    result: list[str] = []
    normalized = value.strip().strip("[]")
    for item in normalized.split(","):
        item = item.strip().strip("'").strip('"')
        if item:
            result.append(item)
    return result


@dataclass(slots=True)
class Settings:
    api_key: str = os.getenv("AI_API_KEY", "")
    base_url: str = os.getenv("AI_BASE_URL", "http://localhost:8317/v1")
    serper_api_key: str = os.getenv("SERPER_API_KEY", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    amap_api_key: str = os.getenv("AMAP_API_KEY", "")

    text_model: str = os.getenv("TEXT_MODEL", "qwen/qwen3.6-plus:free")
    vision_model: str = os.getenv("VISION_MODEL", "qwen/qwen3.6-plus:free")
    text_model_fallback: list[str] = field(
        default_factory=lambda: _parse_str_list(os.getenv("TEXT_MODEL_FALLBACK", ""))
        or [
            "bytedance-seed/dola-seed-2.0-pro:free",
            "x-ai/grok-code-fast-1:optimized:free",
            "kilo-auto/free",
            "stepfun/step-3.5-flash:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "openrouter/free",
            "arcee-ai/trinity-large-preview:free",
        ]
    )
    vision_model_fallback: list[str] = field(
        default_factory=lambda: _parse_str_list(os.getenv("VISION_MODEL_FALLBACK", ""))
        or [
            "bytedance-seed/dola-seed-2.0-pro:free",
            "openrouter/free",
        ]
    )

    admin_uid: int = int(os.getenv("ADMIN_UID", "843341710"))
    admin_api_token: str = os.getenv("ADMIN_API_TOKEN", "")
    default_reply_rate: int = int(os.getenv("DEFAULT_REPLY_RATE", "100"))

    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_db: str = os.getenv("MYSQL_DB", "xiaomiao")

    blocked_groups: list[int] = field(
        default_factory=lambda: _parse_int_list(os.getenv("BLOCKED_GROUPS", ""))
    )
    blocked_users: list[int] = field(
        default_factory=lambda: _parse_int_list(os.getenv("BLOCKED_USERS", ""))
    )

    minecraft_api_secret: str = os.getenv("MINECRAFT_API_SECRET", "minecraft_restart_2024")
    minecraft_notify_group: int = int(os.getenv("MINECRAFT_NOTIFY_GROUP", "0"))

    max_history: int = 100

    @property
    def openai_client(self) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)


settings = Settings()
