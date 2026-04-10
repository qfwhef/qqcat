"""AI chat plugin."""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.exception import FinishedException

from xiaomiao_bot.bootstrap.container import get_container
from xiaomiao_bot.presentation.permissions import permission_checker

container = get_container()
chat = on_message(rule=permission_checker, priority=99, block=False)


@chat.handle()
async def handle_chat(bot: Bot, event: Event) -> None:
    try:
        result = await container.chat_service.handle_event(bot, event)
        if result.should_finish:
            await chat.finish(result.finish_text)
        if result.should_send and result.send_message is not None:
            await chat.send(result.send_message)
    except FinishedException:
        raise

