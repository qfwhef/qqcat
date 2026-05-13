"""Command service."""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import Event

from ..core.logging import get_logger
from ..infrastructure.session_store import SessionStore

logger = get_logger("命令服务")


class CommandService:
    """Parse and execute chat commands."""

    def __init__(self, session_store: SessionStore, default_reply_rate: int) -> None:
        self.session_store = session_store
        self.default_reply_rate = default_reply_rate

    def parse_command(self, msg: str) -> tuple[str | None, str | None]:
        if not msg.startswith("/"):
            return None, None
        command_text = msg[1:].strip()
        if not command_text:
            return None, None
        cmd, _, raw_args = command_text.partition(" ")
        cmd = cmd.lower()
        args = raw_args.strip() or None
        logger.info("⚙️ 收到命令: /%s %s", cmd, args or "")
        return cmd, args

    async def execute(self, event: Event, cmd: str, args: str | None) -> str | None:
        if cmd in {"sleep", "睡觉"}:
            self.session_store.set_sleeping(event, True)
            logger.info("😴 机器人进入睡眠模式")
            return "睡觉了喵~ (已停止自动回复)"
        if cmd in {"wakeup", "weakup", "起床"}:
            self.session_store.set_sleeping(event, False)
            logger.info("🌞 机器人已唤醒")
            return "我醒啦！开始工作喵！"
        if cmd == "rate":
            rate_arg = args.split()[0] if args else ""
            if rate_arg.isdigit():
                rate = max(0, min(100, int(rate_arg)))
                self.session_store.set_reply_rate(event, rate)
                logger.info("📊 回复率已设置为: %s%%", rate)
                return f"回复率已设为: {rate}%"
            return "请提供有效的回复率数值（0-100）"
        if cmd == "srate":
            rate = self.session_store.get_reply_rate(event, self.default_reply_rate)
            logger.info("📊 查询回复率: %s%%", rate)
            return f"当前回复率: {rate}%"
        if cmd == "clean":
            self.session_store.clear_history(event)
            logger.info("🗑️ 已清空聊天记忆")
            return "记忆已格式化，我现在是谁也不认识的猫娘了喵！"
        return None
