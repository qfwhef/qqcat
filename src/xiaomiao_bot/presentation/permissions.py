"""Permission rule for NoneBot."""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import Event, GroupMessageEvent

from ..core.config import settings
from ..core.constants import CFG_BLOCKED_GROUPS, CFG_BLOCKED_USERS
from ..core.logging import get_logger
from ..infrastructure.runtime_config_store import runtime_config_store

logger = get_logger("权限检查")


async def permission_checker(event: Event) -> bool:
    user_id = int(getattr(event, "user_id", 0) or 0)
    blocked_users = runtime_config_store.get_list(CFG_BLOCKED_USERS, settings.blocked_users)
    if user_id and user_id in blocked_users:
        logger.info("🚫 用户命中黑名单: user_id=%s", int(event.user_id))
        return False
    group_id = getattr(event, "group_id", None)
    if isinstance(event, GroupMessageEvent) or group_id not in {None, ""}:
        blocked_groups = runtime_config_store.get_list(CFG_BLOCKED_GROUPS, settings.blocked_groups)
        if int(group_id) in blocked_groups:
            logger.info("🚫 群聊命中黑名单: group_id=%s", int(group_id))
            return False
    return True
