"""Message parsing helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, PrivateMessageEvent

from ...core.logging import get_logger

logger = get_logger("MessageParser")


class MessageParser:
    """Parse OneBot messages into prompt-friendly text."""

    @staticmethod
    def get_user_name(event: Event) -> str:
        if isinstance(event, GroupMessageEvent):
            return event.sender.card or event.sender.nickname or str(event.user_id)
        if isinstance(event, PrivateMessageEvent):
            return event.sender.nickname or str(event.user_id)
        return "未知用户"

    async def parse_message(self, bot: Bot, event: Event) -> str:
        raw_text_list: list[str] = []
        at_bot_present = False
        reply_present = False
        raw_message_text = str(event.message)
        event_reply_id = self._extract_reply_id_from_event_reply(getattr(event, "reply", None))
        raw_reply_id = event_reply_id or self._extract_reply_id(raw_message_text)

        for segment in event.message:
            if segment.type == "text":
                raw_text_list.append(segment.data.get("text", ""))
                continue

            if segment.type == "reply":
                reply_present = True
                reply_text = await self._parse_reply_segment(bot, segment.data)
                if reply_text:
                    raw_text_list.append(f"{reply_text} ")
                continue

            if segment.type == "image":
                image_url = str((getattr(segment, "data", {}) or {}).get("url") or "").strip()
                raw_text_list.append(f" [图片:{image_url}] " if image_url else " [图片] ")
                continue

            if segment.type != "at":
                continue

            target_qq = str(segment.data.get("qq", ""))
            if target_qq == str(bot.self_id):
                at_bot_present = True
                raw_text_list.append(" @小喵 ")
                continue

            mention_text = await self._resolve_at_target(bot, event, target_qq)
            raw_text_list.append(mention_text)

        if not reply_present and raw_reply_id:
            fallback_reply_text = await self._parse_reply_segment(bot, {"id": raw_reply_id})
            raw_text_list.insert(0, f"{fallback_reply_text or f'[回复消息 id={raw_reply_id}]'} ")
        elif raw_reply_id and "[回复消息" not in "".join(raw_text_list):
            fallback_reply_text = await self._parse_reply_segment(bot, {"id": raw_reply_id})
            raw_text_list.insert(0, f"{fallback_reply_text or f'[回复消息 id={raw_reply_id}]'} ")

        parsed_message = "".join(raw_text_list).strip()
        if parsed_message:
            return parsed_message
        if at_bot_present:
            return "@小喵"
        return ""

    @staticmethod
    def check_at_bot(bot: Bot, event: Event) -> bool:
        if event.is_tome():
            return True
        if isinstance(event, GroupMessageEvent):
            for segment in event.message:
                if segment.type == "at" and str(segment.data.get("qq")) == str(bot.self_id):
                    return True
        return False

    async def _resolve_at_target(self, bot: Bot, event: Event, target_qq: str) -> str:
        if isinstance(event, GroupMessageEvent):
            try:
                info = await bot.get_group_member_info(
                    group_id=event.group_id,
                    user_id=int(target_qq),
                    no_cache=False,
                )
                target_name = info.get("card") or info.get("nickname") or target_qq
                return f" @{target_name} "
            except Exception:
                return f" @{target_qq} "
        return f" @{target_qq} "

    async def _parse_reply_segment(self, bot: Bot, reply_data: dict[str, Any]) -> str:
        message_id = reply_data.get("id")
        if not message_id:
            return ""

        try:
            message = await bot.get_msg(message_id=int(message_id))
        except Exception:
            logger.warning("reply get_msg failed: %s", message_id)
            return "[回复消息]"

        sender = self._get_mapping_value(message, "sender") or {}
        sender_name = (
            self._get_mapping_value(sender, "card")
            or self._get_mapping_value(sender, "nickname")
            or self._get_mapping_value(sender, "remark")
            or str(self._get_mapping_value(sender, "user_id") or "未知用户")
        )
        quoted_content = self._extract_reply_content(message)
        return f"[回复消息 [{sender_name}] {quoted_content}]" if quoted_content else f"[回复消息 [{sender_name}]]"

    @staticmethod
    def _parse_cq_codes(text: str) -> str:
        def _decode_html(content: str) -> str:
            return (
                content.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&#91;", "[")
                .replace("&#93;", "]")
                .replace("&apos;", "'")
                .replace("&quot;", '"')
            )

        def _replace(match: re.Match[str]) -> str:
            content = match.group(1)
            parts = content.split(",")
            cq_type = parts[0].strip()
            params: dict[str, str] = {}
            for part in parts[1:]:
                if "=" in part:
                    key, value = part.split("=", 1)
                    params[key.strip()] = _decode_html(value.strip())
            if cq_type == "image":
                url_match = re.search(r"(?:^|,)url=([^,\]]+)", content)
                url = _decode_html(url_match.group(1).strip()) if url_match else params.get("url", "")
                if url:
                    return f"[图片:{url}]"
                summary = params.get("summary", "")
                return f"[图片({summary})]" if summary else "[图片]"
            if cq_type == "at":
                return f"@{params.get('qq', '未知')}"
            if cq_type == "face":
                return "[表情]"
            if cq_type in {"record", "audio"}:
                return "[语音]"
            if cq_type == "video":
                return "[视频]"
            return ""

        return re.sub(r"\[CQ:([^\]]+)\]", _replace, text)

    @staticmethod
    def _extract_reply_id(raw_message: str) -> str:
        match = re.search(r"\[reply:id=(\d+)\]", raw_message)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_reply_id_from_event_reply(reply_obj: Any) -> str:
        if reply_obj is None:
            return ""
        if isinstance(reply_obj, Mapping):
            message_id = reply_obj.get("message_id") or reply_obj.get("id")
            return str(message_id) if message_id else ""
        message_id = getattr(reply_obj, "message_id", None) or getattr(reply_obj, "id", None)
        return str(message_id) if message_id else ""

    def _extract_reply_content(self, message: Any) -> str:
        raw_message = str(self._get_mapping_value(message, "raw_message") or "").strip()
        if raw_message:
            return self._parse_cq_codes(raw_message)

        segments = self._get_mapping_value(message, "message")
        if not isinstance(segments, list):
            return ""

        parts: list[str] = []
        for segment in segments:
            segment_type = self._get_mapping_value(segment, "type")
            data = self._get_mapping_value(segment, "data") or {}
            if segment_type == "text":
                parts.append(str(data.get("text", "")))
            elif segment_type == "at":
                parts.append(f"@{data.get('qq', '')}")
            elif segment_type == "image":
                url = str(data.get("url") or "").strip()
                parts.append(f"[图片:{url}]" if url else "[图片]")
        return "".join(parts).strip()

    @staticmethod
    def extract_image_urls(event: Event) -> list[str]:
        urls: list[str] = []
        for segment in getattr(event, "message", []):
            if getattr(segment, "type", "") != "image":
                continue
            data = getattr(segment, "data", {}) or {}
            url = str(data.get("url") or "").strip()
            if url and url not in urls:
                urls.append(url)
        return urls

    @staticmethod
    def _get_mapping_value(target: Any, key: str) -> Any:
        if isinstance(target, Mapping):
            return target.get(key)
        if hasattr(target, key):
            return getattr(target, key)
        return None

