"""Chat orchestration service."""

from __future__ import annotations

import random
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
