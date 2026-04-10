"""Dependency container."""

from __future__ import annotations

from dataclasses import dataclass

from ..adapters.onebot import MessageParser
from ..application.admin_auth_service import AdminAuthService
from ..application.admin_service import AdminService
from ..application.ai_service import AIService
from ..application.chat_service import ChatService
from ..application.command_service import CommandService
from ..application.config_service import ConfigService
from ..application.minecraft_service import MinecraftService
from ..application.secret_service import SecretService, secret_service
from ..core.config import settings
from ..infrastructure.runtime_config_store import RuntimeConfigStore, runtime_config_store
from ..infrastructure.session_store import SessionStore, session_store
from ..tools import ToolRegistry


@dataclass(slots=True)
class AppContainer:
    parser: MessageParser
    session_store: SessionStore
    runtime_config_store: RuntimeConfigStore
    secret_service: SecretService
    tools: ToolRegistry
    command_service: CommandService
    ai_service: AIService
    chat_service: ChatService
    config_service: ConfigService
    minecraft_service: MinecraftService
    admin_auth_service: AdminAuthService
    admin_service: AdminService


_container: AppContainer | None = None


def get_container() -> AppContainer:
    global _container
    if _container is not None:
        return _container

    parser = MessageParser()
    admin_auth_service = AdminAuthService(secret_service)
    admin_auth_service.bootstrap()
    tools = ToolRegistry(secret_service)
    command_service = CommandService(
        session_store=session_store,
        default_reply_rate=settings.default_reply_rate,
    )
    ai_service = AIService(
        session_store=session_store,
        runtime_config_store=runtime_config_store,
        parser=parser,
        tools=tools,
        secret_service_instance=secret_service,
    )
    chat_service = ChatService(
        parser=parser,
        session_store=session_store,
        command_service=command_service,
        ai_service=ai_service,
    )
    config_service = ConfigService(runtime_config_store=runtime_config_store)
    minecraft_service = MinecraftService(secret_service)
    admin_service = AdminService(
        runtime_config_store=runtime_config_store,
        secret_service=secret_service,
        admin_auth_service=admin_auth_service,
        minecraft_service=minecraft_service,
    )

    _container = AppContainer(
        parser=parser,
        session_store=session_store,
        runtime_config_store=runtime_config_store,
        secret_service=secret_service,
        tools=tools,
        command_service=command_service,
        ai_service=ai_service,
        chat_service=chat_service,
        config_service=config_service,
        minecraft_service=minecraft_service,
        admin_auth_service=admin_auth_service,
        admin_service=admin_service,
    )
    return _container
