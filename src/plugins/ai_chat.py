"""AI chat plugin."""

from nonebot import on_message, on_notice
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.exception import FinishedException

from xiaomiao_bot.bootstrap.container import get_container
from xiaomiao_bot.domain.models import ChatHandleResult
from xiaomiao_bot.presentation.permissions import permission_checker

container = get_container()
chat = on_message(rule=permission_checker, priority=99, block=False)
poke = on_notice(rule=permission_checker, priority=99, block=False)


@chat.handle()
async def handle_chat(bot: Bot, event: Event) -> None:
    async def process() -> ChatHandleResult:
        return await container.chat_service.handle_event(bot, event)

    async def send_result(result: ChatHandleResult) -> None:
        if result.should_finish:
            await chat.finish(result.finish_text)
        if result.should_send and result.send_message is not None:
            await chat.send(result.send_message)

    try:
        if container.chat_service.should_queue_event(bot, event):
            is_command = await container.chat_service.is_command_event(bot, event)
            result = await container.chat_service.run_in_session_queue(
                event,
                process,
                coalesce=not is_command,
                stale_result_factory=ChatHandleResult,
            )
            await send_result(result)
        else:
            await send_result(await process())
    except FinishedException:
        raise


@poke.handle()
async def handle_poke(bot: Bot, event: Event) -> None:
    async def process() -> ChatHandleResult:
        return await container.chat_service.handle_poke_event(bot, event)

    async def send_result(result: ChatHandleResult) -> None:
        if result.should_finish:
            await poke.finish(result.finish_text)
        if result.should_send and result.send_message is not None:
            await poke.send(result.send_message)

    try:
        if container.chat_service.should_queue_poke_event(bot, event):
            result = await container.chat_service.run_in_session_queue(
                event,
                process,
                stale_result_factory=ChatHandleResult,
            )
            await send_result(result)
        else:
            await send_result(await process())
    except FinishedException:
        raise
