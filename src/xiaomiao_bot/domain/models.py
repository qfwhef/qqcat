"""Domain DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nonebot.adapters.onebot.v11 import Message


@dataclass(slots=True)
class SessionScope:
    session_type: str
    session_id: int


@dataclass(slots=True)
class SummaryState:
    summary_version: int = 0
    last_summary_message_id: int = 0
    cooldown_until: int = 0


@dataclass(slots=True)
class ChatHandleResult:
    should_finish: bool = False
    finish_text: str = ""
    should_send: bool = False
    send_message: Message | None = None


HistoryItem = dict[str, Any]
