"""Chat orchestration service."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.exception import FinishedException

from ..adapters.onebot import MessageParser, build_at_message, enrich_reply_context
from ..core.config import settings
from ..core.logging import get_logger
from ..domain.models import ChatHandleResult
from ..infrastructure.session_store import SessionStore
from .ai_service import AIService
from .command_service import CommandService

logger = get_logger("聊天服务")


@dataclass(slots=True)
class _SyntheticSender:
    nickname: str
    card: str | None = None


class _SyntheticNoticeEvent:
    def __init__(
        self,
        *,
        session_type: str,
        session_id: int,
        user_id: int,
        user_name: str,
        group_name: str | None = None,
    ) -> None:
        self.user_id = int(user_id)
        self.group_id = int(session_id) if session_type == "group" else None
        self.group_name = group_name
        self.message_id = int(datetime.now().timestamp() * 1000)
        self.message = []
        self.reply = None
        self.sender = _SyntheticSender(nickname=user_name, card=user_name)


class ChatService:
    """Coordinate parsing, commands, storage and AI response."""

    def __init__(
        self,
        parser: MessageParser,
        session_store: SessionStore,
        command_service: CommandService,
        ai_service: AIService,
    ) -> None:
        self.parser = parser
        self.session_store = session_store
        self.command_service = command_service
        self.ai_service = ai_service

    async def handle_event(self, bot: Bot, event: Event) -> ChatHandleResult:
        is_at_me = self.parser.check_at_bot(bot, event)
        msg = await self.parser.parse_message(bot, event)
        msg = await enrich_reply_context(bot, event, msg)
        logger.info(
            "📨 收到消息: user_id=%s group_id=%s at_me=%s content=%s",
            getattr(event, "user_id", ""),
            getattr(event, "group_id", "private"),
            is_at_me,
            msg[:200],
        )
        if is_at_me and "@小喵" not in msg:
            msg = "@小喵" if not msg else f"@小喵 {msg}".strip()
        if not msg and not is_at_me:
            logger.info("ℹ️ 消息解析后为空且未@机器人，跳过处理")
            return ChatHandleResult()

        cmd, args = self.command_service.parse_command(msg)
        if cmd:
            try:
                reply = await self.command_service.execute(event, cmd, args)
                if reply is not None:
                    return ChatHandleResult(should_finish=True, finish_text=reply)
            except FinishedException:
                raise

        if self.session_store.is_sleeping(event):
            logger.info("😴 当前会话处于睡眠状态，跳过回复")
            return ChatHandleResult()

        user_name = self.parser.get_user_name(event)
        if not is_at_me:
            reply_rate = self.session_store.get_reply_rate(event, self.ai_service.get_default_reply_rate())
            if reply_rate == 0 or random.randint(1, 100) > reply_rate:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if hasattr(event, "group_id"):
                    context_msg = f"[{timestamp}][{user_name}|{getattr(event, 'user_id', '')}]: {msg}"
                else:
                    context_msg = f"[{timestamp}][{user_name}]: {msg}"
                self.session_store.append_user_message(event, context_msg, is_at_bot=is_at_me)
                logger.info("🎲 未命中回复率，本次不回复，仅写入历史。reply_rate=%s%%", reply_rate)
                await self.ai_service.maybe_summarize_memory(event)
                return ChatHandleResult()

        should_reply, reply_content = await self.ai_service.process_message(event, msg, user_name, is_at_me)
        if should_reply and reply_content:
            logger.info("✅ AI已生成回复，准备发送")
            return ChatHandleResult(should_send=True, send_message=build_at_message(reply_content))
        logger.info("ℹ️ 本次未生成可发送回复")
        return ChatHandleResult()

    async def handle_poke_event(self, bot: Bot, event: Event) -> ChatHandleResult:
        if getattr(event, "notice_type", "") != "notify" or getattr(event, "sub_type", "") != "poke":
            return ChatHandleResult()

        scope = self.session_store.get_scope(event)
        actor_name = await self._resolve_poke_name(bot, event, int(getattr(event, "user_id", 0) or 0))
        target_id = int(getattr(event, "target_id", 0) or 0)
        target_name = await self._resolve_poke_target_name(bot, event, target_id)
        poke_text = self._build_poke_text(event, actor_name, target_name)
        logger.info(
            "👆 收到拍一拍: session=%s:%s actor=%s target=%s content=%s",
            scope.session_type,
            scope.session_id,
            actor_name,
            target_name,
            poke_text,
        )

        synthetic_event = _SyntheticNoticeEvent(
            session_type=scope.session_type,
            session_id=scope.session_id,
            user_id=int(getattr(event, "user_id", 0) or 0),
            user_name=actor_name,
            group_name=getattr(event, "group_name", None),
        )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if scope.session_type == "group":
            context_msg = f"[{timestamp}][{actor_name}|{getattr(event, 'user_id', '')}]: {poke_text}"
        else:
            context_msg = f"[{timestamp}][{actor_name}]: {poke_text}"

        if target_id != int(bot.self_id):
            self.session_store.append_user_message(synthetic_event, context_msg, is_at_bot=False)
            await self.ai_service.maybe_summarize_memory(synthetic_event)
            return ChatHandleResult()

        should_reply, reply_content = await self.ai_service.process_message(
            synthetic_event,
            poke_text,
            actor_name,
            False,
            is_poke=True,
        )
        if should_reply and reply_content:
            logger.info("✅ 拍一拍触发了强制回复")
            return ChatHandleResult(should_send=True, send_message=build_at_message(reply_content))
        return ChatHandleResult()

    async def _resolve_poke_name(self, bot: Bot, event: Event, qq: int) -> str:
        if qq <= 0:
            return "未知用户"
        group_id = getattr(event, "group_id", None)
        if group_id not in {None, ""}:
            try:
                info = await bot.get_group_member_info(group_id=int(group_id), user_id=qq, no_cache=False)
                return str(info.get("card") or info.get("nickname") or qq)
            except Exception:
                return str(qq)
        return str(qq)

    async def _resolve_poke_target_name(self, bot: Bot, event: Event, qq: int) -> str:
        if qq == int(bot.self_id):
            return "小喵"
        return await self._resolve_poke_name(bot, event, qq)

    @staticmethod
    def _build_poke_text(event: Event, actor_name: str, target_name: str) -> str:
        raw_info = getattr(event, "raw_info", None) or []
        parts: list[str] = []
        qq_index = 0
        for item in raw_info:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).strip()
            if item_type == "qq":
                name = actor_name if qq_index == 0 else target_name
                parts.append(f"“{name}”")
                qq_index += 1
            elif item_type == "nor":
                text = str(item.get("txt", "")).strip()
                if text:
                    parts.append(text)
        content = "".join(parts).strip()
        return content or f"“{actor_name}”戳了戳“{target_name}”"
