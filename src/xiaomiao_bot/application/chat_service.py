"""Chat orchestration service."""

from __future__ import annotations

import asyncio
import contextvars
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from nonebot.adapters.onebot.v11 import Bot, Event, Message
from nonebot.exception import FinishedException

from ..adapters.onebot import MessageParser, build_at_message, build_expression_message, enrich_reply_context
from ..core.config import settings
from ..core.logging import get_logger
from ..domain.models import ChatHandleResult
from ..infrastructure.session_store import SessionStore
from .ai_service import AIService
from .command_service import CommandService

logger = get_logger("聊天服务")
_T = TypeVar("_T")
_QUEUE_LATEST_CHECKER: contextvars.ContextVar[Callable[[], bool] | None] = contextvars.ContextVar(
    "queue_latest_checker",
    default=None,
)


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


@dataclass(slots=True)
class _ReplyDecision:
    should_reply: bool
    reason: str
    priority: int = 0


@dataclass(slots=True)
class _QuickReply:
    text: str
    face_id: int | None = None
    meme_tag: str | None = None
    image_path: str | None = None

    @property
    def history_content(self) -> str:
        parts = [self.text] if self.text else []
        if self.face_id is not None:
            parts.append(f"[QQ表情:{self.face_id}]")
        if self.image_path:
            parts.append(f"[表情包:{Path(self.image_path).name}]")
        return " ".join(parts).strip()


class ChatService:
    """Coordinate parsing, commands, storage and AI response."""

    BOT_ALIASES = ("小喵", "小猫", "猫娘", "喵喵", "qqcat", "QQcat")
    QUIET_PATTERNS = (
        r"^[哈啊嘿呵]{2,}[哈啊嘿呵]*$",
        r"^(6|66|666|草|艹|笑死|乐|哦|噢|嗯|好|ok|OK|1|对|是)$",
        r"^[。.!！?？~～\s]+$",
    )
    QUESTION_HINTS = (
        "吗",
        "嘛",
        "么",
        "呢",
        "咋",
        "怎么",
        "如何",
        "为什么",
        "为啥",
        "求助",
        "帮忙",
        "有没有",
        "谁知道",
    )
    DISCUSSION_HINTS = ("建议", "推荐", "方案", "规划", "问题", "报错", "失败", "咋办", "怎么办")
    QUICK_BLOCK_HINTS = ("怎么", "如何", "为什么", "为啥", "报错", "失败", "方案", "推荐", "建议", "帮", "查", "搜")
    MEME_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

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
        self._session_queue_locks: dict[str, asyncio.Lock] = {}
        self._session_latest_tokens: dict[str, int] = {}
        self._session_token_counter = 0
        self._session_token_lock = asyncio.Lock()
        self._last_group_auto_reply_at: dict[int, datetime] = {}
        self.group_auto_reply_cooldown_seconds = 90
        project_root = Path(__file__).resolve().parents[3]
        meme_dir = Path(settings.meme_dir)
        self.meme_dir = meme_dir if meme_dir.is_absolute() else project_root / meme_dir

    def should_queue_event(self, bot: Bot, event: Event) -> bool:
        """需要机器人主动回复的事件进入同会话等待队列。"""
        if self._is_private_event(event):
            return True
        return self.parser.check_at_bot(bot, event)

    def should_queue_poke_event(self, bot: Bot, event: Event) -> bool:
        """拍机器人本体会触发回复，也需要与普通 @ 回复串行。"""
        if (
            getattr(event, "notice_type", "") != "notify"
            or getattr(event, "sub_type", "") != "poke"
        ):
            return False
        return int(getattr(event, "target_id", 0) or 0) == int(bot.self_id)

    async def is_command_event(self, bot: Bot, event: Event) -> bool:
        _ = bot
        msg = await self.parser.parse_message(bot, event)
        return msg.startswith("/") and bool(msg[1:].split())

    async def run_in_session_queue(
        self,
        event: Event,
        action: Callable[[], Awaitable[_T]],
        *,
        coalesce: bool = True,
        debounce_seconds: float = 1.2,
        stale_result_factory: Callable[[], _T] | None = None,
    ) -> _T:
        scope = self.session_store.get_scope(event)
        queue_key = f"{scope.session_type}:{scope.session_id}"
        token = await self._mark_latest_queue_token(queue_key) if coalesce else 0
        if coalesce and debounce_seconds > 0:
            await asyncio.sleep(debounce_seconds)
            if not self._is_latest_queue_token(queue_key, token):
                logger.info("⏭️ 会话回复已被更新触发覆盖，跳过旧请求: session=%s", queue_key)
                return self._stale_result(stale_result_factory)

        lock = self._session_queue_locks.setdefault(queue_key, asyncio.Lock())
        if lock.locked():
            logger.info("⏳ 会话回复队列等待中: session=%s", queue_key)
        async with lock:
            if coalesce and not self._is_latest_queue_token(queue_key, token):
                logger.info("⏭️ 会话回复排队期间被新触发覆盖: session=%s", queue_key)
                return self._stale_result(stale_result_factory)
            logger.info("▶️ 会话回复队列开始处理: session=%s", queue_key)
            checker_token = (
                _QUEUE_LATEST_CHECKER.set(lambda: self._is_latest_queue_token(queue_key, token))
                if coalesce
                else None
            )
            try:
                result = await action()
            finally:
                if checker_token is not None:
                    _QUEUE_LATEST_CHECKER.reset(checker_token)
            if coalesce and not self._is_latest_queue_token(queue_key, token):
                logger.info("⏭️ AI已生成但不是最新触发，取消发送旧回复: session=%s", queue_key)
                return self._stale_result(stale_result_factory)
            logger.info("✅ 会话回复队列处理完成: session=%s", queue_key)
            return result

    async def _mark_latest_queue_token(self, queue_key: str) -> int:
        async with self._session_token_lock:
            self._session_token_counter += 1
            token = self._session_token_counter
            self._session_latest_tokens[queue_key] = token
            return token

    def _is_latest_queue_token(self, queue_key: str, token: int) -> bool:
        return self._session_latest_tokens.get(queue_key) == token

    @staticmethod
    def _stale_result(stale_result_factory: Callable[[], _T] | None) -> _T:
        if stale_result_factory is None:
            raise RuntimeError("stale_result_factory is required when coalescing queued actions")
        return stale_result_factory()

    @staticmethod
    def _current_queue_is_latest() -> bool:
        checker = _QUEUE_LATEST_CHECKER.get()
        return checker() if checker is not None else True

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
        decision = self._decide_reply(bot, event, msg, is_at_me)
        if not decision.should_reply:
            self._append_silent_user_message(event, msg, user_name, is_at_me)
            logger.info("🤫 普通群聊未触发回复: reason=%s priority=%s", decision.reason, decision.priority)
            await self.ai_service.maybe_summarize_memory(event)
            return ChatHandleResult()

        if not is_at_me:
            reply_rate = self.session_store.get_reply_rate(event, self.ai_service.get_default_reply_rate())
            if reply_rate == 0 or random.randint(1, 100) > reply_rate:
                self._append_silent_user_message(event, msg, user_name, is_at_me)
                logger.info("🎲 未命中回复率，本次不回复，仅写入历史。reply_rate=%s%%", reply_rate)
                await self.ai_service.maybe_summarize_memory(event)
                return ChatHandleResult()

        quick_reply = self._pick_quick_reply(event, msg, is_at_me, decision)
        if quick_reply:
            self._append_silent_user_message(event, msg, user_name, is_at_me)
            self.session_store.append_assistant_message(event, quick_reply.history_content)
            self._remember_group_auto_reply(event, is_at_me)
            logger.info("😺 使用轻量回复: text=%s face=%s meme=%s", quick_reply.text, quick_reply.face_id, quick_reply.image_path or "")
            return ChatHandleResult(
                should_send=True,
                send_message=self._build_quick_reply_message(event, quick_reply),
            )

        should_reply, reply_content = await self.ai_service.process_message(
            event,
            msg,
            user_name,
            is_at_me,
            should_continue=self._current_queue_is_latest,
        )
        if should_reply and reply_content:
            logger.info("✅ AI已生成回复，准备发送")
            self._remember_group_auto_reply(event, is_at_me)
            return ChatHandleResult(
                should_send=True,
                send_message=self._build_reply_message(event, reply_content),
            )
        logger.info("ℹ️ 本次未生成可发送回复")
        return ChatHandleResult()

    @staticmethod
    def _is_private_event(event: Event) -> bool:
        return getattr(event, "group_id", None) in {None, ""}

    def _decide_reply(self, bot: Bot, event: Event, msg: str, is_at_me: bool) -> _ReplyDecision:
        """Decide whether a normal message deserves an AI response."""
        if self._is_private_event(event):
            return _ReplyDecision(True, "private", 100)
        if is_at_me:
            return _ReplyDecision(True, "at_bot", 100)
        if self._is_reply_to_bot(bot, event):
            return _ReplyDecision(True, "reply_to_bot", 95)

        cleaned = self._clean_decision_text(msg)
        if not cleaned:
            return _ReplyDecision(False, "empty_group_message", 0)
        if self._mentions_bot_alias(cleaned):
            return _ReplyDecision(True, "mentions_bot_alias", 90)
        if self._is_quiet_group_message(cleaned):
            return _ReplyDecision(False, "lightweight_chatter", 5)

        group_id = int(getattr(event, "group_id", 0) or 0)
        if self._is_group_auto_reply_on_cooldown(group_id):
            return _ReplyDecision(False, "auto_reply_cooldown", 10)

        priority = self._group_reply_priority(cleaned)
        if priority <= 0:
            return _ReplyDecision(False, "no_clear_invitation", 0)
        if random.randint(1, 100) > priority:
            return _ReplyDecision(False, "low_priority_roll", priority)
        return _ReplyDecision(True, "group_context_match", priority)

    def _append_silent_user_message(self, event: Event, msg: str, user_name: str, is_at_me: bool) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self._is_private_event(event):
            context_msg = f"[{timestamp}][{user_name}|{getattr(event, 'user_id', '')}]: {msg}"
        else:
            context_msg = f"[{timestamp}][{user_name}]: {msg}"
        self.session_store.append_user_message(event, context_msg, is_at_bot=is_at_me)

    def _remember_group_auto_reply(self, event: Event, is_at_me: bool) -> None:
        if is_at_me or self._is_private_event(event):
            return
        group_id = int(getattr(event, "group_id", 0) or 0)
        if group_id > 0:
            self._last_group_auto_reply_at[group_id] = datetime.now()

    def _is_group_auto_reply_on_cooldown(self, group_id: int) -> bool:
        last_at = self._last_group_auto_reply_at.get(group_id)
        if not last_at:
            return False
        elapsed = (datetime.now() - last_at).total_seconds()
        return elapsed < self.group_auto_reply_cooldown_seconds

    @classmethod
    def _clean_decision_text(cls, msg: str) -> str:
        text = re.sub(r"\[回复消息[^\]]*(?:\][^\[]*)?\]", "", msg)
        text = re.sub(r"\[[^\]]+\]", "", text)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _mentions_bot_alias(cls, text: str) -> bool:
        lowered = text.lower()
        return any(alias.lower() in lowered for alias in cls.BOT_ALIASES)

    @classmethod
    def _is_quiet_group_message(cls, text: str) -> bool:
        if len(text) <= 2:
            return True
        return any(re.fullmatch(pattern, text.strip()) for pattern in cls.QUIET_PATTERNS)

    @classmethod
    def _group_reply_priority(cls, text: str) -> int:
        priority = 0
        if "?" in text or "？" in text:
            priority += 25
        if any(hint in text for hint in cls.QUESTION_HINTS):
            priority += 25
        if any(hint in text for hint in cls.DISCUSSION_HINTS):
            priority += 15
        if len(text) >= 16:
            priority += 10
        return min(priority, 45)

    @staticmethod
    def _is_reply_to_bot(bot: Bot, event: Event) -> bool:
        reply_obj = getattr(event, "reply", None)
        if not reply_obj:
            return False
        sender = reply_obj.get("sender") if isinstance(reply_obj, dict) else getattr(reply_obj, "sender", None)
        sender = sender or {}
        user_id = sender.get("user_id") if isinstance(sender, dict) else getattr(sender, "user_id", None)
        try:
            return int(user_id or 0) == int(bot.self_id)
        except Exception:
            return False

    def _pick_quick_reply(
        self,
        event: Event,
        msg: str,
        is_at_me: bool,
        decision: _ReplyDecision,
    ) -> _QuickReply | None:
        if not is_at_me and decision.reason not in {"mentions_bot_alias", "reply_to_bot"}:
            return None
        cleaned = self._clean_quick_reply_text(msg)
        if not cleaned:
            return _QuickReply("在呢", face_id=14, meme_tag="hello")
        if any(hint in cleaned for hint in self.QUICK_BLOCK_HINTS):
            return None
        if len(cleaned) > 18:
            return None

        reply: _QuickReply | None = None
        if any(word in cleaned for word in ("早", "早安", "早上好")):
            reply = _QuickReply("早呀", face_id=74, meme_tag="happy")
        elif any(word in cleaned for word in ("晚安", "睡了", "睡觉")):
            reply = _QuickReply("晚安喵", face_id=75, meme_tag="goodnight")
        elif any(word in cleaned for word in ("谢谢", "感谢", "谢啦")):
            reply = _QuickReply("不用谢喵", face_id=76, meme_tag="happy")
        elif any(word in cleaned for word in ("贴贴", "摸摸", "抱抱")):
            reply = _QuickReply("喵呜", face_id=66, meme_tag="cute")
        elif any(word in cleaned for word in ("可爱", "乖", "好猫")):
            reply = _QuickReply("嘿嘿", face_id=30, meme_tag="happy")
        elif any(word in cleaned for word in ("哈哈", "笑死", "乐")):
            reply = _QuickReply("笑什么啦", face_id=30, meme_tag="funny")
        elif any(word in cleaned for word in ("在吗", "在不在", "出来", "冒泡", "喵")):
            reply = _QuickReply("在呢", face_id=14, meme_tag="hello")

        if reply is None:
            return None
        reply.image_path = self._choose_meme_path(reply.meme_tag)
        return reply

    def _choose_meme_path(self, meme_tag: str | None) -> str | None:
        if not meme_tag or not self.meme_dir.exists():
            return None
        if random.randint(1, 100) > max(0, min(100, int(settings.meme_reply_rate))):
            return None
        candidates: list[Path] = []
        for folder_name in (meme_tag, "default"):
            folder = self.meme_dir / folder_name
            if folder.exists():
                candidates.extend(
                    path for path in folder.iterdir()
                    if path.is_file() and path.suffix.lower() in self.MEME_EXTENSIONS
                )
        if not candidates:
            return None
        return str(random.choice(candidates).resolve())

    @classmethod
    def _clean_quick_reply_text(cls, msg: str) -> str:
        text = cls._clean_decision_text(msg)
        text = re.sub(r"@小喵", "", text, flags=re.IGNORECASE)
        for alias in cls.BOT_ALIASES:
            text = re.sub(re.escape(alias), "", text, flags=re.IGNORECASE)
        return re.sub(r"\s+", "", text).strip("，。,.!！?？~～")

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

        if self.session_store.is_sleeping(synthetic_event):
            self.session_store.append_user_message(synthetic_event, context_msg, is_at_bot=False)
            logger.info("😴 当前会话处于睡眠状态，忽略拍一拍触发回复")
            await self.ai_service.maybe_summarize_memory(synthetic_event)
            return ChatHandleResult()

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
            should_continue=self._current_queue_is_latest,
        )
        if should_reply and reply_content:
            logger.info("✅ 拍一拍触发了强制回复")
            return ChatHandleResult(
                should_send=True,
                send_message=self._build_reply_message(synthetic_event, reply_content),
            )
        return ChatHandleResult()

    def _build_reply_message(self, event: Event, reply_content: str) -> Message:
        if self._is_private_event(event):
            return Message(reply_content)
        return build_at_message(reply_content)

    def _build_quick_reply_message(self, event: Event, quick_reply: _QuickReply) -> Message:
        return build_expression_message(
            quick_reply.text,
            face_id=quick_reply.face_id if not quick_reply.image_path else None,
            image_path=quick_reply.image_path,
            parse_at=not self._is_private_event(event),
        )

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
