"""Runtime config service."""

from __future__ import annotations

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
    CFG_SUMMARY_ONLY_GROUP,
)
from ..infrastructure.runtime_config_store import RuntimeConfigStore


class ConfigService:
    """Read and update runtime config."""

    def __init__(self, runtime_config_store: RuntimeConfigStore) -> None:
        self.runtime_config_store = runtime_config_store

    def get_config(self) -> dict:
        runtime_snapshot = self.runtime_config_store.get_runtime_snapshot()
        return {
            "ai_base_url": runtime_snapshot["ai_base_url"],
            "text_model": runtime_snapshot["text_model"],
            "vision_model": runtime_snapshot["vision_model"],
            "text_model_fallback": runtime_snapshot["text_model_fallback"],
            "vision_model_fallback": runtime_snapshot["vision_model_fallback"],
            "max_history": runtime_snapshot["max_history"],
            "log_level": runtime_snapshot["log_level"],
            "default_reply_rate": self.runtime_config_store.get_int(
                CFG_DEFAULT_REPLY_RATE, settings.default_reply_rate
            ),
            "blocked_groups": self.runtime_config_store.get_list(
                CFG_BLOCKED_GROUPS, settings.blocked_groups
            ),
            "blocked_users": self.runtime_config_store.get_list(
                CFG_BLOCKED_USERS, settings.blocked_users
            ),
            "enable_summary_memory": self.runtime_config_store.get_bool(
                CFG_ENABLE_SUMMARY_MEMORY, True
            ),
            "summary_only_group": self.runtime_config_store.get_bool(CFG_SUMMARY_ONLY_GROUP, True),
            "enable_tools": self.runtime_config_store.get_bool(CFG_ENABLE_TOOLS, True),
            "prompt_base": str(self.runtime_config_store.get(CFG_PROMPT_BASE, DEFAULT_PROMPT_BASE)),
            "prompt_logic_private": str(
                self.runtime_config_store.get(CFG_PROMPT_LOGIC_PRIVATE, DEFAULT_PROMPT_LOGIC_PRIVATE)
            ),
            "prompt_logic_at_me": str(
                self.runtime_config_store.get(CFG_PROMPT_LOGIC_AT_ME, DEFAULT_PROMPT_LOGIC_AT_ME)
            ),
            "prompt_logic_group": str(
                self.runtime_config_store.get(CFG_PROMPT_LOGIC_GROUP, DEFAULT_PROMPT_LOGIC_GROUP)
            ),
            "prompt_summary_system": str(
                self.runtime_config_store.get(
                    CFG_PROMPT_SUMMARY_SYSTEM, DEFAULT_PROMPT_SUMMARY_SYSTEM
                )
            ),
        }

    def update_default_reply_rate(self, rate: int) -> dict:
        self.runtime_config_store.set(CFG_DEFAULT_REPLY_RATE, max(0, min(100, int(rate))))
        return self.get_config()

    def update_blocklist(
        self,
        blocked_groups: list[int] | None,
        blocked_users: list[int] | None,
    ) -> dict:
        payload: dict[str, object] = {}
        if blocked_groups is not None:
            payload[CFG_BLOCKED_GROUPS] = blocked_groups
        if blocked_users is not None:
            payload[CFG_BLOCKED_USERS] = blocked_users
        self.runtime_config_store.update(payload)
        return self.get_config()

    def update_features(
        self,
        enable_summary_memory: bool | None,
        summary_only_group: bool | None,
        enable_tools: bool | None,
    ) -> dict:
        payload: dict[str, object] = {}
        if enable_summary_memory is not None:
            payload[CFG_ENABLE_SUMMARY_MEMORY] = enable_summary_memory
        if summary_only_group is not None:
            payload[CFG_SUMMARY_ONLY_GROUP] = summary_only_group
        if enable_tools is not None:
            payload[CFG_ENABLE_TOOLS] = enable_tools
        self.runtime_config_store.update(payload)
        return self.get_config()

    def update_prompts(
        self,
        *,
        prompt_base: str | None = None,
        prompt_logic_private: str | None = None,
        prompt_logic_at_me: str | None = None,
        prompt_logic_group: str | None = None,
        prompt_summary_system: str | None = None,
    ) -> dict:
        payload: dict[str, object] = {}
        if prompt_base is not None:
            payload[CFG_PROMPT_BASE] = prompt_base
        if prompt_logic_private is not None:
            payload[CFG_PROMPT_LOGIC_PRIVATE] = prompt_logic_private
        if prompt_logic_at_me is not None:
            payload[CFG_PROMPT_LOGIC_AT_ME] = prompt_logic_at_me
        if prompt_logic_group is not None:
            payload[CFG_PROMPT_LOGIC_GROUP] = prompt_logic_group
        if prompt_summary_system is not None:
            payload[CFG_PROMPT_SUMMARY_SYSTEM] = prompt_summary_system
        self.runtime_config_store.update(payload)
        return self.get_config()
