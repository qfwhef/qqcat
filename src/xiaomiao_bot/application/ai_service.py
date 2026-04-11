"""AI chat service with tools and summarization."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import MutableMapping
from datetime import datetime
from typing import Any

from nonebot.adapters.onebot.v11 import Event, GroupMessageEvent, PrivateMessageEvent
from openai import APIStatusError, AsyncOpenAI, RateLimitError

from ..adapters.onebot import MessageParser
from ..application.secret_service import SecretService, secret_service
from ..application.prompt_defaults import (
    DEFAULT_PROMPT_BASE,
    DEFAULT_PROMPT_LOGIC_AT_ME,
    DEFAULT_PROMPT_LOGIC_GROUP,
    DEFAULT_PROMPT_LOGIC_POKE,
    DEFAULT_PROMPT_LOGIC_PRIVATE,
    DEFAULT_PROMPT_SUMMARY_SYSTEM,
)
from ..core.config import settings
from ..core.constants import (
    CFG_DEFAULT_REPLY_RATE,
    CFG_ENABLE_SUMMARY_MEMORY,
    CFG_ENABLE_TOOLS,
    CFG_PROMPT_BASE,
    CFG_PROMPT_LOGIC_AT_ME,
    CFG_PROMPT_LOGIC_GROUP,
    CFG_PROMPT_LOGIC_POKE,
    CFG_PROMPT_LOGIC_PRIVATE,
    CFG_PROMPT_SUMMARY_SYSTEM,
    CFG_SUMMARY_COOLDOWN_SECONDS,
    CFG_SUMMARY_KEEP_RECENT_MESSAGES,
    CFG_SUMMARY_MIN_NEW_MESSAGES,
    CFG_SUMMARY_ONLY_GROUP,
    CFG_SUMMARY_TRIGGER_ROUNDS,
)
from ..core.logging import get_logger
from ..infrastructure.runtime_config_store import RuntimeConfigStore
from ..infrastructure.session_store import SessionStore
from ..tools import ToolRegistry

logger = get_logger("AI服务")


class ToolArgsNotSupportedError(RuntimeError):
    """Raised when upstream provider rejects tools parameters."""


class EmptyModelResponseError(RuntimeError):
    """Raised when model returns empty content."""


class AIService:
    """AI pipeline."""

    def __init__(
        self,
        session_store: SessionStore,
        runtime_config_store: RuntimeConfigStore,
        parser: MessageParser,
        tools: ToolRegistry,
        secret_service_instance: SecretService | None = None,
    ) -> None:
        self.session_store = session_store
        self.runtime_config_store = runtime_config_store
        self.parser = parser
        self.tools = tools
        self.secret_service = secret_service_instance or secret_service
        self._client_cache: dict[tuple[str, str], AsyncOpenAI] = {}
        self.max_completion_tokens = 1024
        self.max_tool_payload_chars = 2200
        self.tool_retry_interval_seconds = 5
        self.tools_disabled_at: float | None = None
        self.enable_tools = True
        self._summary_locks: MutableMapping[str, asyncio.Lock] = {}

    def get_default_reply_rate(self) -> int:
        return self.runtime_config_store.get_int(CFG_DEFAULT_REPLY_RATE, settings.default_reply_rate)

    def get_max_history(self) -> int:
        return int(self.runtime_config_store.get_runtime_snapshot().get("max_history", settings.max_history))

    def is_summary_enabled(self) -> bool:
        return self.runtime_config_store.get_bool(CFG_ENABLE_SUMMARY_MEMORY, True)

    def summary_only_group(self) -> bool:
        return self.runtime_config_store.get_bool(CFG_SUMMARY_ONLY_GROUP, True)

    def get_summary_trigger_rounds(self) -> int:
        return self.runtime_config_store.get_int(CFG_SUMMARY_TRIGGER_ROUNDS, 150)

    def get_summary_keep_recent_messages(self) -> int:
        return self.runtime_config_store.get_int(CFG_SUMMARY_KEEP_RECENT_MESSAGES, 16)

    def get_summary_cooldown_seconds(self) -> int:
        return self.runtime_config_store.get_int(CFG_SUMMARY_COOLDOWN_SECONDS, 90)

    def get_summary_min_new_messages(self) -> int:
        return self.runtime_config_store.get_int(CFG_SUMMARY_MIN_NEW_MESSAGES, 12)

    def _sync_tool_flag(self) -> None:
        self.enable_tools = self.runtime_config_store.get_bool(CFG_ENABLE_TOOLS, True)

    def get_base_prompt(self) -> str:
        return str(self.runtime_config_store.get(CFG_PROMPT_BASE, DEFAULT_PROMPT_BASE))

    def get_logic_prompt(self, is_private: bool, is_at_me: bool, is_poke: bool = False) -> str:
        if is_poke:
            return str(self.runtime_config_store.get(CFG_PROMPT_LOGIC_POKE, DEFAULT_PROMPT_LOGIC_POKE))
        if is_private:
            return str(
                self.runtime_config_store.get(CFG_PROMPT_LOGIC_PRIVATE, DEFAULT_PROMPT_LOGIC_PRIVATE)
            )
        if is_at_me:
            return str(self.runtime_config_store.get(CFG_PROMPT_LOGIC_AT_ME, DEFAULT_PROMPT_LOGIC_AT_ME))
        return str(self.runtime_config_store.get(CFG_PROMPT_LOGIC_GROUP, DEFAULT_PROMPT_LOGIC_GROUP))

    def get_summary_prompt(self) -> str:
        return str(
            self.runtime_config_store.get(CFG_PROMPT_SUMMARY_SYSTEM, DEFAULT_PROMPT_SUMMARY_SYSTEM)
        )

    @staticmethod
    def _is_group_event(event: Event) -> bool:
        return isinstance(event, GroupMessageEvent) or getattr(event, "group_id", None) not in {None, ""}

    def _is_private_event(self, event: Event) -> bool:
        return not self._is_group_event(event)

    @staticmethod
    def clean_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        while history and history[0].get("role") == "assistant":
            history.pop(0)
        return history

    def maybe_reenable_tools(self) -> None:
        if self.enable_tools or self.tools_disabled_at is None:
            return
        if time.time() - self.tools_disabled_at >= self.tool_retry_interval_seconds:
            self.enable_tools = True
            self.tools_disabled_at = None
            logger.info("工具能力冷却结束，已自动重新开启")

    def format_tool_list(self) -> str:
        lines: list[str] = []
        for tool in self.tools.get_openai_tools():
            function = tool.get("function", {})
            name = function.get("name", "")
            description = function.get("description", "")
            if name:
                lines.append(f"- {name}: {description}")
        return "\n".join(lines) if lines else "无可用工具"

    @staticmethod
    def format_summary_memory(summary: str) -> str:
        return summary.strip() if summary.strip() else "无长期摘要记忆"

    @staticmethod
    def format_for_summary(messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for item in messages:
            content = str(item.get("content", "")).strip()
            if content:
                lines.append(f"[{item.get('role', 'unknown')}] {content}")
        return "\n".join(lines)

    async def maybe_summarize_memory(self, event: Event) -> None:
        history = self.session_store.get_history(event)
        is_private = self._is_private_event(event)
        await self._summarize_if_needed(event, history, is_private)

    async def _summarize_if_needed(
        self,
        event: Event,
        history: list[dict[str, Any]],
        is_private: bool,
    ) -> list[dict[str, Any]]:
        if not self.is_summary_enabled():
            return history
        if self.summary_only_group() and is_private:
            return history
        summary_trigger_rounds = self.get_summary_trigger_rounds()
        summary_keep_recent_messages = self.get_summary_keep_recent_messages()
        summary_min_new_messages = self.get_summary_min_new_messages()
        summary_cooldown_seconds = self.get_summary_cooldown_seconds()
        if len(history) <= summary_trigger_rounds or len(history) <= summary_keep_recent_messages:
            return history

        scope = self.session_store.get_scope(event)
        lock_key = f"{scope.session_type}:{scope.session_id}"
        summary_lock = self._summary_locks.setdefault(lock_key, asyncio.Lock())
        async with summary_lock:
            refreshed_history = self.session_store.get_history(event)
            if (
                len(refreshed_history) <= summary_trigger_rounds
                or len(refreshed_history) <= summary_keep_recent_messages
            ):
                return refreshed_history

            now_ts = int(time.time())
            state = self.session_store.get_summary_state(event)
            if now_ts < state.cooldown_until:
                return refreshed_history

            history_entries = self.session_store.get_history_entries(event)
            if len(history_entries) < summary_min_new_messages:
                return refreshed_history

            latest_history = [
                {"role": str(row["role"]), "content": str(row["content_text"])}
                for row in history_entries
            ]
            if len(latest_history) <= summary_trigger_rounds:
                return latest_history

            to_summarize_entries = history_entries[: -summary_keep_recent_messages]
            to_summarize = latest_history[: -summary_keep_recent_messages]
            recent_history = latest_history[-summary_keep_recent_messages :]
            summary_input = self.format_for_summary(to_summarize)
            if not summary_input or not to_summarize_entries:
                return latest_history

            source_start_message_id = state.last_summary_message_id + 1
            source_end_message_id = int(to_summarize_entries[-1]["id"])
            if source_start_message_id > source_end_message_id:
                logger.warning(
                    "摘要范围异常，已跳过: session=%s:%s start=%s end=%s",
                    scope.session_type,
                    scope.session_id,
                    source_start_message_id,
                    source_end_message_id,
                )
                return latest_history

            summary_messages = [
                {"role": "system", "content": self.get_summary_prompt()},
                {
                    "role": "user",
                    "content": f"待压缩对话：\n{summary_input}\n\n请输出融合后的新摘要。",
                },
            ]
            new_summary = await self._create_summary_with_fallback(
                event,
                summary_messages,
                message_row_id=source_end_message_id,
                request_excerpt=summary_input[:500],
            )
            if not new_summary:
                return latest_history

            summary_version = self.session_store.save_summary(
                event,
                new_summary,
                source_start_message_id=source_start_message_id,
                source_end_message_id=source_end_message_id,
                source_message_count=len(to_summarize_entries),
            )
            self.session_store.save_summary_state(
                event,
                summary_version=summary_version,
                last_summary_message_id=source_end_message_id,
                cooldown_until=now_ts + summary_cooldown_seconds,
            )
            return recent_history

    async def _create_summary_with_fallback(
        self,
        event: Event,
        summary_messages: list[dict[str, Any]],
        *,
        message_row_id: int | None,
        request_excerpt: str,
    ) -> str:
        models = [self.runtime_config_store.get_text_model(), *self.runtime_config_store.get_text_model_fallback()]
        last_exc: Exception | None = None
        for index, model in enumerate(models):
            try:
                response = await self._create_completion_with_audit(
                    event,
                    summary_messages,
                    stage="summary",
                    model=model,
                    allow_tools=False,
                    fallback_index=index,
                    message_row_id=message_row_id,
                    request_excerpt=request_excerpt,
                    max_retries=1,
                )
                summary = self._extract_content(response.choices[0].message).strip()
                if summary:
                    return summary
                raise EmptyModelResponseError("summary model returned empty content")
            except Exception as exc:
                last_exc = exc
                reason = self._classify_failure(exc)
                logger.warning("摘要模型回滚: model=%s reason=%s detail=%s", model, reason, exc)
        if last_exc is not None:
            raise last_exc
        return ""

    async def process_message(
        self,
        event: Event,
        msg: str,
        user_name: str,
        is_at_me: bool,
        is_poke: bool = False,
    ) -> tuple[bool, str]:
        is_private = self._is_private_event(event)
        history = self.session_store.get_history(event)
        image_urls = self.parser.extract_image_urls(event)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self._is_group_event(event):
            user_id = int(getattr(event, "user_id", 0) or 0)
            identity = f"{user_name}|{user_id}" if user_id > 0 else user_name
            context_msg = f"[{timestamp}][{identity}]: {msg}"
        else:
            context_msg = f"[{timestamp}][{user_name}]: {msg}"
        context_msg = await self._describe_images_in_context(context_msg, skip_urls=image_urls)
        user_message_row_id = self.session_store.append_user_message(event, context_msg, is_at_bot=is_at_me)
        history = self.session_store.get_history(event)
        history = await self._summarize_if_needed(event, history, is_private)
        summary = self.session_store.get_summary(event)

        cleaned_history = self.clean_history(history[:])
        request_messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self._build_system_prompt(
                    base_prompt=self.get_base_prompt(),
                    logic_prompt=self.get_logic_prompt(is_private, is_at_me, is_poke=is_poke),
                    summary=summary,
                    context_msg=context_msg,
                ),
            }
        ]
        request_messages.extend(cleaned_history[:-1])
        request_messages.append({"role": "user", "content": self._build_user_content(context_msg, image_urls)})

        self._sync_tool_flag()
        self.maybe_reenable_tools()
        text_model = self.runtime_config_store.get_text_model()
        vision_model = self.runtime_config_store.get_vision_model()
        use_model = vision_model if image_urls else text_model
        active_model = use_model
        allow_tools = self.enable_tools
        logger.info("正在请求AI...")
        logger.info("工具能力开关状态: %s", "开启" if allow_tools else "关闭")
        logger.info("动态选模: %s", f"vision ({use_model})" if image_urls else f"text ({use_model})")

        try:
            try:
                response = await self._create_completion_with_audit(
                    event,
                    request_messages,
                    stage="chat",
                    model=use_model,
                    allow_tools=allow_tools,
                    fallback_index=0,
                    message_row_id=user_message_row_id,
                    request_excerpt=context_msg[:500],
                )
            except Exception as exc:
                response, active_model, allow_tools = await self._retry_with_fallback(
                    event,
                    request_messages,
                    image_urls,
                    use_model,
                    allow_tools,
                    exc,
                    message_row_id=user_message_row_id,
                    request_excerpt=context_msg[:500],
                )

            for _ in range(2):
                executed = await self._run_tool_calls(response, request_messages, event)
                if not executed:
                    break
                try:
                    response = await self._create_completion_with_audit(
                        event,
                        request_messages,
                        stage="chat-tool-round",
                        model=active_model,
                        allow_tools=allow_tools,
                        fallback_index=0,
                        message_row_id=user_message_row_id,
                        request_excerpt=context_msg[:500],
                    )
                except Exception as exc:
                    response, active_model, allow_tools = await self._retry_with_fallback(
                        event,
                        request_messages,
                        image_urls,
                        active_model,
                        allow_tools,
                        exc,
                        message_row_id=user_message_row_id,
                        request_excerpt=context_msg[:500],
                    )

            reply_content = self._extract_content(response.choices[0].message)
            if not reply_content:
                response, active_model, allow_tools = await self._retry_with_fallback(
                    event,
                    request_messages,
                    image_urls,
                    active_model,
                    allow_tools,
                    EmptyModelResponseError("chat model returned empty content"),
                    message_row_id=user_message_row_id,
                    request_excerpt=context_msg[:500],
                )
                reply_content = self._extract_content(response.choices[0].message)
                if not reply_content:
                    request_messages.append(
                        {"role": "user", "content": "请基于上面的工具结果，直接给出简洁明确的最终答复。"}
                    )
                    fallback_response = await self._create_completion_with_audit(
                        event,
                        request_messages,
                        stage="chat-finalize",
                        model=active_model,
                        allow_tools=False,
                        fallback_index=0,
                        message_row_id=user_message_row_id,
                        request_excerpt=context_msg[:500],
                    )
                    reply_content = self._extract_content(fallback_response.choices[0].message)
                    if not reply_content:
                        return False, ""

            pseudo_tool_call = self._extract_pseudo_tool_call(reply_content) or self._extract_json_tool_call(reply_content)
            if pseudo_tool_call:
                tool_name, params = pseudo_tool_call
                tool_result = await self.tools.execute(
                    tool_name=tool_name,
                    arguments_json=json.dumps(params, ensure_ascii=False),
                    event=event,
                )
                self.session_store.append_tool_message(
                    event,
                    tool_name=tool_name,
                    tool_args=params,
                    tool_result=tool_result,
                )
                if tool_result.get("ok"):
                    reply_content = self._render_tool_result(tool_name, tool_result.get("result", {}))
                else:
                    reply_content = f"工具调用失败：{tool_result.get('error', 'unknown error')}"

            self.session_store.append_assistant_message(
                event,
                reply_content,
                model_name=active_model,
            )
            logger.info("本次AI回复完成: active_model=%s allow_tools=%s", active_model, allow_tools)
            return True, reply_content
        except Exception as exc:
            logger.error("AI处理失败: %s", exc)
            raise

    async def _retry_with_fallback(
        self,
        event: Event,
        request_messages: list[dict[str, Any]],
        image_urls: list[str],
        use_model: str,
        allow_tools: bool,
        original_exc: Exception,
        *,
        message_row_id: int | None,
        request_excerpt: str,
    ) -> tuple[Any, str, bool]:
        reason = self._classify_failure(original_exc)
        logger.warning("触发模型回滚: from=%s reason=%s allow_tools=%s detail=%s", use_model, reason, allow_tools, original_exc)

        if reason == "image_unsupported" and image_urls:
            raw_content = request_messages[-1]["content"]
            if isinstance(raw_content, list):
                text_parts = [
                    str(block.get("text", ""))
                    for block in raw_content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                downgraded_content = "\n".join(part for part in text_parts if part).strip()
            else:
                downgraded_content = str(raw_content)
            request_messages[-1] = {"role": "user", "content": downgraded_content}
            text_model = self.runtime_config_store.get_text_model()
            logger.warning("回滚策略: 图片输入不受支持，降级为纯文本模型 from=%s to=%s", use_model, text_model)
            response = await self._create_completion_with_audit(
                event,
                request_messages,
                stage="chat-fallback",
                model=text_model,
                allow_tools=allow_tools,
                fallback_index=1,
                message_row_id=message_row_id,
                request_excerpt=request_excerpt,
            )
            return response, text_model, allow_tools

        if reason == "tools_unsupported" and allow_tools:
            logger.warning("回滚策略: 当前模型不支持 tools，关闭工具后重试 model=%s", use_model)
            self.tools_disabled_at = time.time()
            try:
                response = await self._create_completion_with_audit(
                    event,
                    request_messages,
                    stage="chat-fallback",
                    model=use_model,
                    allow_tools=False,
                    fallback_index=0,
                    message_row_id=message_row_id,
                    request_excerpt=request_excerpt,
                )
                return response, use_model, False
            except Exception as exc:
                original_exc = exc
                reason = self._classify_failure(exc)
                logger.warning("关闭 tools 后重试失败: model=%s reason=%s detail=%s", use_model, reason, exc)

        fallback_models = (
            self.runtime_config_store.get_vision_model_fallback()
            if image_urls
            else self.runtime_config_store.get_text_model_fallback()
        )
        last_exc = original_exc
        for index, fallback_model in enumerate(fallback_models, start=1):
            if fallback_model == use_model:
                continue
            try:
                response = await self._create_completion_with_audit(
                    event,
                    request_messages,
                    stage="chat-fallback",
                    model=fallback_model,
                    allow_tools=allow_tools,
                    fallback_index=index,
                    message_row_id=message_row_id,
                    request_excerpt=request_excerpt,
                )
                return response, fallback_model, allow_tools
            except Exception as exc:
                last_exc = exc
                logger.warning("备用模型调用失败: model=%s reason=%s detail=%s", fallback_model, self._classify_failure(exc), exc)
        raise last_exc

    async def _create_completion_with_audit(
        self,
        event: Event,
        messages: list[dict[str, Any]],
        *,
        stage: str,
        model: str,
        allow_tools: bool,
        fallback_index: int,
        message_row_id: int | None,
        request_excerpt: str,
        max_retries: int = 3,
    ) -> Any:
        self._log_active_model(stage, model, allow_tools=allow_tools, fallback_index=fallback_index)
        started_at = time.perf_counter()
        try:
            response = await self._create_completion(
                messages,
                allow_tools=allow_tools,
                model=model,
                max_retries=max_retries,
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            self.session_store.log_ai_call(
                event,
                stage=stage,
                model_name=model,
                fallback_index=fallback_index,
                allow_tools=allow_tools,
                is_success=True,
                latency_ms=latency_ms,
                request_excerpt=request_excerpt or self._build_request_excerpt(messages),
                message_row_id=message_row_id,
            )
            return response
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            self.session_store.log_ai_call(
                event,
                stage=stage,
                model_name=model,
                fallback_index=fallback_index,
                allow_tools=allow_tools,
                is_success=False,
                failure_reason=self._classify_failure(exc),
                latency_ms=latency_ms,
                request_excerpt=request_excerpt or self._build_request_excerpt(messages),
                message_row_id=message_row_id,
            )
            raise

    def _build_system_prompt(
        self,
        *,
        base_prompt: str,
        logic_prompt: str,
        summary: str,
        context_msg: str,
    ) -> str:
        return (
            f"【长期记忆摘要】\n{self.format_summary_memory(summary)}\n\n"
            f"【会话场景】\n{logic_prompt}\n\n"
            f"【你的性格】\n{base_prompt}\n\n"
            f"【你能干什么】\n{self.format_tool_list()}\n\n"
            f"【此次用户消息】\n{context_msg}"
        )

    @staticmethod
    def _build_user_content(context_msg: str, image_urls: list[str]) -> str | list[dict[str, Any]]:
        if not image_urls:
            return context_msg
        blocks: list[dict[str, Any]] = [{"type": "text", "text": context_msg}]
        for url in image_urls:
            blocks.append({"type": "image_url", "image_url": {"url": url}})
        return blocks

    @staticmethod
    def _build_request_excerpt(messages: list[dict[str, Any]]) -> str:
        for item in reversed(messages):
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                return content[:500]
            if isinstance(content, list):
                text_parts: list[str] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(str(block.get("text", "")))
                excerpt = "\n".join(part for part in text_parts if part).strip()
                if excerpt:
                    return excerpt[:500]
        return ""

    async def _create_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        allow_tools: bool,
        model: str,
        max_retries: int = 3,
    ) -> Any:
        retry_count = 0
        while retry_count <= max_retries:
            try:
                client = self._get_openai_client()
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": self.max_completion_tokens,
                }
                if allow_tools and self.enable_tools:
                    kwargs["tools"] = self.tools.get_openai_tools()
                    kwargs["tool_choice"] = "auto"
                try:
                    return await client.chat.completions.create(**kwargs)
                except TypeError as exc:
                    err_text = str(exc).lower()
                    if "unexpected keyword argument" in err_text and ("tools" in err_text or "tool_choice" in err_text):
                        raise ToolArgsNotSupportedError(str(exc)) from exc
                    if "unexpected keyword argument" in err_text:
                        kwargs.pop("include_reasoning", None)
                        return await client.chat.completions.create(**kwargs)
                    raise
            except (RateLimitError, APIStatusError) as exc:
                err_text = str(exc).lower()
                if "429" in err_text or "thrott" in err_text:
                    retry_count += 1
                    if retry_count > max_retries:
                        raise
                    await asyncio.sleep(1.2**retry_count)
                    continue
                if allow_tools and self.enable_tools and any(
                    token in err_text
                    for token in ("tools", "tool_choice", "function call", "function_call", "unexpected keyword argument")
                ):
                    raise ToolArgsNotSupportedError(str(exc)) from exc
                raise

    async def _run_tool_calls(
        self,
        response: Any,
        request_messages: list[dict[str, Any]],
        event: Event,
    ) -> bool:
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return False
        logger.info("检测到原生工具调用，数量: %s", len(tool_calls))

        request_messages.append(
            {
                "role": "assistant",
                "content": self._extract_content(message),
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments or "{}",
                        },
                    }
                    for tool_call in tool_calls
                ],
            }
        )
        for tool_call in tool_calls:
            logger.info("执行原生工具调用: %s, 参数: %s", tool_call.function.name, tool_call.function.arguments or "{}")
            tool_args = self._safe_load_json_object(tool_call.function.arguments)
            result = await self.tools.execute(
                tool_name=tool_call.function.name,
                arguments_json=tool_call.function.arguments,
                event=event,
            )
            logger.info("原生工具调用结果: %s", json.dumps(result, ensure_ascii=False))
            self.session_store.append_tool_message(
                event,
                tool_name=tool_call.function.name,
                tool_args=tool_args,
                tool_result=result,
            )
            tool_content = json.dumps(result, ensure_ascii=False)
            if len(tool_content) > self.max_tool_payload_chars:
                tool_content = f"{tool_content[: self.max_tool_payload_chars]}\n...[tool result truncated]..."
            request_messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": tool_content}
            )
        return True

    async def _describe_images_in_context(
        self,
        context_msg: str,
        *,
        skip_urls: list[str] | None = None,
    ) -> str:
        urls = re.findall(r"\[图片:([^\]]+)\]", context_msg)
        if not urls:
            return context_msg
        skip_set = set(skip_urls or [])
        for url in urls:
            if url in skip_set:
                continue
            replacement = "[图片]"
            vision_messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": url}},
                        {"type": "text", "text": "用不超过50字简洁描述这张图片的内容或主题"},
                    ],
                }
            ]
            for vision_model in [
                self.runtime_config_store.get_vision_model(),
                *self.runtime_config_store.get_vision_model_fallback(),
            ]:
                try:
                    response = await self._get_openai_client().chat.completions.create(
                        model=vision_model,
                        messages=vision_messages,
                        max_tokens=120,
                    )
                    description = self._extract_content(response.choices[0].message).strip()
                    if description:
                        replacement = f"[图片：{description}]"
                        logger.info("视觉模型 [%s] 描述成功: %s", vision_model, description[:30])
                    break
                except Exception as exc:
                    logger.warning("视觉模型 [%s] 描述失败，尝试下一个: %s", vision_model, exc)
                    continue
            context_msg = context_msg.replace(f"[图片:{url}]", replacement, 1)
        return context_msg

    @staticmethod
    def _extract_content(message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    parts.append(str(block["text"]))
            raw = "\n".join(parts).strip()
        else:
            raw = str(content or "").strip()
        return AIService._clean_model_output(raw)

    @staticmethod
    def _clean_model_output(text: str) -> str:
        llama_marker = "<|start_header_id|>assistant<|end_header_id|>"
        if llama_marker in text:
            text = text.split(llama_marker)[-1].strip()
        text = re.sub(r"<\|[^|>]*\|>", "", text).strip()
        for pattern in (r"^Draft:\s*\n(.+)", r"\nDraft:\s*\n(.+)", r"Ready\.\s*\n+(.+)"):
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if not re.search(
                    r"^(Response plan|Length:|Tone:|Format:|Draft:)",
                    candidate,
                    re.MULTILINE | re.IGNORECASE,
                ):
                    text = candidate
                    break
        return text.strip()

    @staticmethod
    def _extract_pseudo_tool_call(reply_content: str) -> tuple[str, dict[str, str]] | None:
        function_match = re.search(r"<function=([a-zA-Z0-9_]+)>", reply_content)
        if not function_match:
            return None
        params: dict[str, str] = {}
        for key, value in re.findall(
            r"<parameter=([a-zA-Z0-9_]+)>(.*?)</parameter>",
            reply_content,
            flags=re.DOTALL,
        ):
            params[key.strip()] = value.strip()
        return function_match.group(1).strip(), params

    @staticmethod
    def _extract_json_tool_call(reply_content: str) -> tuple[str, dict[str, Any]] | None:
        text = reply_content.strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except Exception:
            return None
        if isinstance(data, list) and data and isinstance(data[0], dict):
            first = data[0]
            name = str(first.get("name", "")).strip()
            params = first.get("parameters", {})
            return (name, params) if name and isinstance(params, dict) else None
        if isinstance(data, dict):
            name = str(data.get("name", "")).strip()
            params = data.get("parameters", {})
            return (name, params) if name and isinstance(params, dict) else None
        return None

    @staticmethod
    def _safe_load_json_object(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _render_tool_result(tool_name: str, payload: dict[str, Any]) -> str:
        if tool_name == "get_current_time":
            return f"现在时间是：{payload.get('human', '')}"
        if tool_name == "get_weather":
            city = payload.get("resolved_city") or payload.get("city") or ""
            province = payload.get("province") or ""
            location = f"{province}{city}" if province and province not in city else city
            if payload.get("mode") == "daily":
                rows = payload.get("daily", []) or []
                if not rows:
                    return f"{location}未来天气预报为空。"
                lines = [f"{location}未来{len(rows)}天天气预报："]
                week_map = {
                    "1": "周一",
                    "2": "周二",
                    "3": "周三",
                    "4": "周四",
                    "5": "周五",
                    "6": "周六",
                    "7": "周日",
                }
                for row in rows:
                    lines.append(
                        f"{row.get('date')} {week_map.get(str(row.get('week', '')), '')}："
                        f"白天{row.get('day_weather')} {row.get('temp_max_c')}°C，"
                        f"夜间{row.get('night_weather')} {row.get('temp_min_c')}°C，"
                        f"{row.get('day_wind')}{row.get('day_wind_power')}级"
                    )
                return "\n".join(lines)
            return (
                f"{location}当前天气：{payload.get('weather', '未知天气')}，"
                f"气温{payload.get('temperature_c')}°C，湿度{payload.get('humidity_percent')}%，"
                f"{payload.get('wind_direction', '')}风{payload.get('wind_power', '')}级。"
                f"（数据更新时间：{payload.get('report_time', '')}）"
            )
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _classify_failure(exc: Exception) -> str:
        if isinstance(exc, EmptyModelResponseError):
            return "empty_response"
        if isinstance(exc, ToolArgsNotSupportedError):
            return "tools_unsupported"
        err_text = str(exc).lower()
        if "429" in err_text or "thrott" in err_text:
            return "rate_limit"
        if "support image input" in err_text or "image" in err_text and "unsupported" in err_text:
            return "image_unsupported"
        if any(token in err_text for token in ("tools", "tool_choice", "function call", "function_call")):
            return "tools_unsupported"
        return "other"

    @staticmethod
    def _log_active_model(stage: str, model: str, *, allow_tools: bool, fallback_index: int) -> None:
        logger.info(
            "当前活跃模型: stage=%s model=%s allow_tools=%s fallback_index=%s",
            stage,
            model,
            allow_tools,
            fallback_index,
        )

    def _get_openai_client(self) -> AsyncOpenAI:
        runtime_snapshot = self.runtime_config_store.get_runtime_snapshot()
        api_key = self.secret_service.get_secret("AI_API_KEY", settings.api_key)
        base_url = str(runtime_snapshot.get("ai_base_url") or settings.base_url)
        cache_key = (api_key, base_url)
        client = self._client_cache.get(cache_key)
        if client is None:
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            self._client_cache[cache_key] = client
        return client
