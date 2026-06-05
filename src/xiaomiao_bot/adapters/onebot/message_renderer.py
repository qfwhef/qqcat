"""Render and enrich OneBot messages."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageSegment

from ...core.text_splitting import split_text_chunks


def build_at_message(reply_content: str) -> Message:
    msg = Message()
    pattern = re.compile(r"(\[@(\d+)\])|(?<![\w/])[@＠](\d{5,20})(?!\d)")
    last_end = 0
    for match in pattern.finditer(reply_content):
        text_before = reply_content[last_end:match.start()]
        if text_before:
            msg += MessageSegment.text(text_before)
        qq = match.group(2) or match.group(3)
        if qq:
            msg += MessageSegment.at(int(qq))
        last_end = match.end()
    tail = reply_content[last_end:]
    if tail:
        msg += MessageSegment.text(tail)
    return msg


def build_expression_message(
    reply_content: str = "",
    *,
    face_id: int | None = None,
    image_path: str | None = None,
    parse_at: bool = True,
) -> Message:
    msg = build_at_message(reply_content) if parse_at else Message(reply_content)
    if face_id is not None:
        msg += MessageSegment.face(int(face_id))
    if image_path:
        path = Path(image_path).resolve()
        msg += MessageSegment.image(path.as_uri())
    return msg


def build_text_messages(reply_content: str, *, max_chars: int, parse_at: bool = True) -> list[Message]:
    chunks = split_text_chunks(reply_content, max_chars=max_chars)
    if parse_at:
        return [build_at_message(chunk) for chunk in chunks]
    return [Message(chunk) for chunk in chunks]


async def enrich_reply_context(bot: Bot, event: Event, msg: str) -> str:
    reply_obj = getattr(event, "reply", None)
    reply_id = _extract_reply_id(reply_obj, str(getattr(event, "message", "")))
    if not reply_id or "[回复消息" in msg:
        return msg

    try:
        quoted = await bot.get_msg(message_id=int(reply_id))
        sender = quoted.get("sender", {}) if isinstance(quoted, dict) else {}
        sender_name = sender.get("card") or sender.get("nickname") or str(sender.get("user_id", "未知用户"))
        quoted_raw = str(quoted.get("raw_message") or "").strip() if isinstance(quoted, dict) else ""
        if not quoted_raw:
            quoted_raw = f"id={reply_id}"
        return f"[回复消息 [{sender_name}] {quoted_raw}] {msg}".strip()
    except Exception:
        return f"[回复消息 id={reply_id}] {msg}".strip()


def _extract_reply_id(reply_obj: Any, raw_message: str) -> str:
    if isinstance(reply_obj, dict):
        message_id = reply_obj.get("message_id") or reply_obj.get("id")
        if message_id:
            return str(message_id)
    elif reply_obj is not None:
        message_id = getattr(reply_obj, "message_id", None) or getattr(reply_obj, "id", None)
        if message_id:
            return str(message_id)

    match = re.search(r"\[reply:id=(\d+)\]", raw_message)
    return match.group(1) if match else ""
