"""Admin routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from ...application.prompt_defaults import (
    DEFAULT_PROMPT_BASE,
    DEFAULT_PROMPT_LOGIC_AT_ME,
    DEFAULT_PROMPT_LOGIC_GROUP,
    DEFAULT_PROMPT_LOGIC_PRIVATE,
    DEFAULT_PROMPT_SUMMARY_SYSTEM,
)
from ...bootstrap.container import get_container

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_MENUS = [
    {"key": "overview", "label": "概览", "path": "/admin-ui/overview"},
    {"key": "runtime", "label": "AI 运行配置", "path": "/admin-ui/runtime"},
    {"key": "tools", "label": "工具管理", "path": "/admin-ui/tools"},
    {"key": "prompts", "label": "提示词", "path": "/admin-ui/prompts"},
    {"key": "access", "label": "访问控制", "path": "/admin-ui/access"},
    {"key": "session-configs", "label": "会话配置", "path": "/admin-ui/session-configs"},
    {"key": "messages", "label": "消息查询", "path": "/admin-ui/messages"},
    {"key": "summaries", "label": "摘要查询", "path": "/admin-ui/summaries"},
    {"key": "ai-calls", "label": "AI 调用日志", "path": "/admin-ui/ai-calls"},
]


class AdminLoginPayload(BaseModel):
    qq: int
    token: str = ""


class ReplyRatePayload(BaseModel):
    default_reply_rate: int = Field(ge=0, le=100)


class RuntimeConfigPayload(BaseModel):
    ai_base_url: str | None = None
    text_model: str | None = None
    vision_model: str | None = None
    text_model_fallback: list[str] | None = None
    vision_model_fallback: list[str] | None = None
    default_reply_rate: int | None = Field(default=None, ge=0, le=100)
    enable_tools: bool | None = None
    enable_summary_memory: bool | None = None
    summary_only_group: bool | None = None
    summary_trigger_rounds: int | None = Field(default=None, ge=1, le=2000)
    summary_keep_recent_messages: int | None = Field(default=None, ge=1, le=500)
    summary_cooldown_seconds: int | None = Field(default=None, ge=0, le=86400)
    summary_min_new_messages: int | None = Field(default=None, ge=1, le=500)
    max_history: int | None = Field(default=None, ge=1, le=500)
    log_level: str | None = None


class BlocklistPayload(BaseModel):
    blocked_groups: list[int] | None = None
    blocked_users: list[int] | None = None


class FeaturePayload(BaseModel):
    enable_summary_memory: bool | None = None
    summary_only_group: bool | None = None
    enable_tools: bool | None = None


class PromptPayload(BaseModel):
    prompt_base: str | None = None
    prompt_logic_private: str | None = None
    prompt_logic_at_me: str | None = None
    prompt_logic_group: str | None = None
    prompt_summary_system: str | None = None


class SecretUpdatePayload(BaseModel):
    secret_value: str
    value_hint: str | None = None


class HttpToolCreatePayload(BaseModel):
    tool_name: str
    display_name: str | None = None
    description: str
    parameters_json: dict[str, Any] | None = None
    method: str = "GET"
    url: str
    headers_json: dict[str, Any] | None = None
    body_template: str | None = None
    timeout_seconds: int = Field(default=15, ge=1, le=300)
    is_enabled: bool = True


class ToolUpdatePayload(BaseModel):
    display_name: str | None = None
    description: str | None = None
    parameters_json: dict[str, Any] | None = None
    method: str | None = None
    url: str | None = None
    headers_json: dict[str, Any] | None = None
    body_template: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    is_enabled: bool | None = None


class AdminUserCreatePayload(BaseModel):
    user_id: int
    nickname: str | None = None
    is_active: bool = True


class AdminUserUpdatePayload(BaseModel):
    nickname: str | None = None
    is_active: bool | None = None


class GroupConfigPayload(BaseModel):
    group_name: str | None = None
    reply_rate: int | None = Field(default=None, ge=0, le=100)
    is_sleeping: bool | None = None
    enable_ai: bool | None = None
    enable_summary: bool | None = None


class PrivateConfigPayload(BaseModel):
    user_nickname: str | None = None
    reply_rate: int | None = Field(default=None, ge=0, le=100)
    is_sleeping: bool | None = None
    enable_ai: bool | None = None
    enable_summary: bool | None = None


class MessageUpdatePayload(BaseModel):
    sender_user_id: int | None = None
    sender_nickname: str | None = None
    sender_card: str | None = None
    group_name: str | None = None
    peer_nickname: str | None = None
    role: str | None = None
    message_type: str | None = None
    content_text: str | None = None
    tool_name: str | None = None
    tool_args_json: dict[str, Any] | None = None
    model_name: str | None = None
    quoted_text: str | None = None
    is_reply: bool | None = None
    is_at_bot: bool | None = None


class MessageBatchDeletePayload(BaseModel):
    message_ids: list[int] = Field(default_factory=list)


def _model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return dict(model.model_dump(exclude_none=True))
    return dict(model.dict(exclude_none=True))


def _get_current_admin(request: Request, x_admin_token: str | None) -> dict[str, Any]:
    container = get_container()
    try:
        return container.admin_auth_service.get_current_admin(
            session_cookie=request.cookies.get(container.admin_auth_service.session_cookie_name),
            x_admin_token=x_admin_token,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def _changed_by(admin: dict[str, Any]) -> str:
    user_id = admin.get("user_id")
    nickname = str(admin.get("nickname") or "admin")
    return f"{nickname}({user_id})" if user_id is not None else nickname


def _page_result(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": items,
        "page": 1,
        "page_size": len(items),
        "total": len(items),
    }


def _legacy_config() -> dict[str, Any]:
    container = get_container()
    runtime_config = container.admin_service.get_runtime_config()
    prompts = container.admin_service.get_prompts()
    blocklist = container.admin_service.get_blocklist()
    return {
        **runtime_config,
        **prompts,
        **blocklist,
    }


@router.post("/auth/login")
async def admin_login(payload: AdminLoginPayload, response: Response) -> dict[str, Any]:
    container = get_container()
    try:
        admin_user = container.admin_auth_service.login(payload.qq, payload.token)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    session_cookie = container.admin_auth_service.create_session_cookie(
        admin_user["user_id"],
        admin_user["nickname"],
    )
    response.set_cookie(
        key=container.admin_auth_service.session_cookie_name,
        value=session_cookie,
        httponly=True,
        samesite="lax",
        max_age=container.admin_auth_service.session_max_age_seconds,
        path="/",
    )
    return {
        "user": {
            **admin_user,
            "auth_mode": "cookie",
        },
        "menus": ADMIN_MENUS,
    }


@router.post("/auth/logout")
async def admin_logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(key=get_container().admin_auth_service.session_cookie_name, path="/")
    return {"status": "ok"}


@router.get("/auth/me")
async def admin_me(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return {
        "user": admin,
        "menus": ADMIN_MENUS,
    }


@router.get("/overview")
async def get_overview(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.get_overview()


@router.get("/runtime-config")
async def get_runtime_config(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.get_runtime_config()


@router.put("/runtime-config")
async def update_runtime_config(
    payload: RuntimeConfigPayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return get_container().admin_service.update_runtime_config(
        _model_dump(payload),
        changed_by=_changed_by(admin),
    )


@router.get("/prompts")
async def get_prompts(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.get_prompts()


@router.get("/prompts/defaults")
async def get_prompt_defaults(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return {
        "prompt_base": DEFAULT_PROMPT_BASE,
        "prompt_logic_private": DEFAULT_PROMPT_LOGIC_PRIVATE,
        "prompt_logic_at_me": DEFAULT_PROMPT_LOGIC_AT_ME,
        "prompt_logic_group": DEFAULT_PROMPT_LOGIC_GROUP,
        "prompt_summary_system": DEFAULT_PROMPT_SUMMARY_SYSTEM,
    }


@router.put("/prompts")
async def update_prompts(
    payload: PromptPayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return get_container().admin_service.update_prompts(
        _model_dump(payload),
        changed_by=_changed_by(admin),
    )


@router.get("/secrets")
async def list_secrets(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return _page_result(get_container().admin_service.list_secrets())


@router.put("/secrets/{secret_key}")
async def update_secret(
    secret_key: str,
    payload: SecretUpdatePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return get_container().admin_service.update_secret(
        secret_key=secret_key,
        secret_value=payload.secret_value,
        value_hint=payload.value_hint,
        changed_by=_changed_by(admin),
    )


@router.get("/tools")
async def list_tools(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return _page_result(get_container().admin_service.list_tools())


@router.post("/tools/http")
async def create_http_tool(
    payload: HttpToolCreatePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    try:
        return get_container().admin_service.create_http_tool(
            _model_dump(payload),
            changed_by=_changed_by(admin),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/tools/{tool_name}")
async def update_tool(
    tool_name: str,
    payload: ToolUpdatePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    try:
        return get_container().admin_service.update_tool(
            tool_name,
            _model_dump(payload),
            changed_by=_changed_by(admin),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/tools/{tool_name}")
async def delete_tool(
    tool_name: str,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    try:
        return get_container().admin_service.delete_tool(
            tool_name,
            changed_by=_changed_by(admin),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/admin-users")
async def list_admin_users(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return _page_result(get_container().admin_service.list_admin_users())


@router.post("/admin-users")
async def create_admin_user(
    payload: AdminUserCreatePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return get_container().admin_service.create_admin_user(
        user_id=payload.user_id,
        nickname=payload.nickname,
        is_active=payload.is_active,
        changed_by=_changed_by(admin),
    )


@router.put("/admin-users/{user_id}")
async def update_admin_user(
    user_id: int,
    payload: AdminUserUpdatePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    try:
        return get_container().admin_service.update_admin_user(
            user_id=user_id,
            nickname=payload.nickname,
            is_active=payload.is_active,
            changed_by=_changed_by(admin),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/blocklist")
async def get_blocklist(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.get_blocklist()


@router.put("/blocklist")
async def update_blocklist(
    payload: BlocklistPayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return get_container().admin_service.update_blocklist(
        blocked_groups=payload.blocked_groups,
        blocked_users=payload.blocked_users,
        changed_by=_changed_by(admin),
    )


@router.get("/group-configs")
async def list_group_configs(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=""),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.list_group_configs(
        page=page,
        page_size=page_size,
        keyword=keyword,
    )


@router.put("/group-configs/{group_id}")
async def update_group_config(
    group_id: int,
    payload: GroupConfigPayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return get_container().admin_service.update_group_config(
        group_id,
        _model_dump(payload),
        changed_by=_changed_by(admin),
    )


@router.get("/private-configs")
async def list_private_configs(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=""),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.list_private_configs(
        page=page,
        page_size=page_size,
        keyword=keyword,
    )


@router.put("/private-configs/{user_id}")
async def update_private_config(
    user_id: int,
    payload: PrivateConfigPayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return get_container().admin_service.update_private_config(
        user_id,
        _model_dump(payload),
        changed_by=_changed_by(admin),
    )


@router.get("/messages/group")
async def list_group_messages(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session_id: int | None = Query(default=None),
    sender_user_id: int | None = Query(default=None),
    role: str = Query(default=""),
    keyword: str = Query(default=""),
    start_at: str = Query(default=""),
    end_at: str = Query(default=""),
    is_reply: bool | None = Query(default=None),
    is_tool: bool | None = Query(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.list_messages(
        session_type="group",
        page=page,
        page_size=page_size,
        session_id=session_id,
        sender_user_id=sender_user_id,
        role=role,
        keyword=keyword,
        start_at=start_at,
        end_at=end_at,
        is_reply=is_reply,
        is_tool=is_tool,
    )


@router.get("/messages/group/{session_id}/{message_id}")
async def get_group_message_detail(
    session_id: int,
    message_id: int,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    try:
        return get_container().admin_service.get_message_detail(
            session_type="group",
            session_id=session_id,
            message_id=message_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/messages/group/{session_id}/{message_id}")
async def update_group_message(
    session_id: int,
    message_id: int,
    payload: MessageUpdatePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    try:
        return get_container().admin_service.update_message(
            session_type="group",
            session_id=session_id,
            message_id=message_id,
            payload=_model_dump(payload),
            changed_by=_changed_by(admin),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/messages/group/{session_id}/batch-delete")
async def delete_group_messages(
    session_id: int,
    payload: MessageBatchDeletePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return get_container().admin_service.delete_messages(
        session_type="group",
        session_id=session_id,
        message_ids=payload.message_ids,
        changed_by=_changed_by(admin),
    )


@router.get("/message-sessions/group")
async def list_group_message_sessions(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    keyword: str = Query(default=""),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return _page_result(
        get_container().admin_service.list_message_sessions(
            session_type="group",
            keyword=keyword,
        )
    )


@router.get("/messages/private")
async def list_private_messages(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session_id: int | None = Query(default=None),
    sender_user_id: int | None = Query(default=None),
    role: str = Query(default=""),
    keyword: str = Query(default=""),
    start_at: str = Query(default=""),
    end_at: str = Query(default=""),
    is_reply: bool | None = Query(default=None),
    is_tool: bool | None = Query(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.list_messages(
        session_type="private",
        page=page,
        page_size=page_size,
        session_id=session_id,
        sender_user_id=sender_user_id,
        role=role,
        keyword=keyword,
        start_at=start_at,
        end_at=end_at,
        is_reply=is_reply,
        is_tool=is_tool,
    )


@router.get("/messages/private/{session_id}/{message_id}")
async def get_private_message_detail(
    session_id: int,
    message_id: int,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    try:
        return get_container().admin_service.get_message_detail(
            session_type="private",
            session_id=session_id,
            message_id=message_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/messages/private/{session_id}/{message_id}")
async def update_private_message(
    session_id: int,
    message_id: int,
    payload: MessageUpdatePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    try:
        return get_container().admin_service.update_message(
            session_type="private",
            session_id=session_id,
            message_id=message_id,
            payload=_model_dump(payload),
            changed_by=_changed_by(admin),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/messages/private/{session_id}/batch-delete")
async def delete_private_messages(
    session_id: int,
    payload: MessageBatchDeletePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    return get_container().admin_service.delete_messages(
        session_type="private",
        session_id=session_id,
        message_ids=payload.message_ids,
        changed_by=_changed_by(admin),
    )


@router.get("/message-sessions/private")
async def list_private_message_sessions(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    keyword: str = Query(default=""),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return _page_result(
        get_container().admin_service.list_message_sessions(
            session_type="private",
            keyword=keyword,
        )
    )


@router.get("/summaries/group")
async def list_group_summaries(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.list_summaries(
        session_type="group",
        page=page,
        page_size=page_size,
        session_id=session_id,
        is_active=is_active,
    )


@router.get("/summaries/private")
async def list_private_summaries(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.list_summaries(
        session_type="private",
        page=page,
        page_size=page_size,
        session_id=session_id,
        is_active=is_active,
    )


@router.get("/ai-call-logs")
async def list_ai_call_logs(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session_type: str = Query(default=""),
    session_id: int | None = Query(default=None),
    stage: str = Query(default=""),
    model_name: str = Query(default=""),
    failure_reason: str = Query(default=""),
    is_success: bool | None = Query(default=None),
    start_at: str = Query(default=""),
    end_at: str = Query(default=""),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return get_container().admin_service.list_ai_call_logs(
        page=page,
        page_size=page_size,
        session_type=session_type,
        session_id=session_id,
        stage=stage,
        model_name=model_name,
        failure_reason=failure_reason,
        is_success=is_success,
        start_at=start_at,
        end_at=end_at,
    )


@router.get("/config")
async def get_legacy_runtime_config(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _get_current_admin(request, x_admin_token)
    return _legacy_config()


@router.put("/config/reply-rate")
async def update_legacy_reply_rate(
    payload: ReplyRatePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    get_container().admin_service.update_runtime_config(
        {"default_reply_rate": payload.default_reply_rate},
        changed_by=_changed_by(admin),
    )
    return _legacy_config()


@router.put("/config/blocklist")
async def update_legacy_blocklist(
    payload: BlocklistPayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    get_container().admin_service.update_blocklist(
        blocked_groups=payload.blocked_groups,
        blocked_users=payload.blocked_users,
        changed_by=_changed_by(admin),
    )
    return _legacy_config()


@router.put("/config/features")
async def update_legacy_features(
    payload: FeaturePayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    get_container().admin_service.update_runtime_config(
        _model_dump(payload),
        changed_by=_changed_by(admin),
    )
    return _legacy_config()


@router.put("/config/prompts")
async def update_legacy_prompts(
    payload: PromptPayload,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = _get_current_admin(request, x_admin_token)
    get_container().admin_service.update_prompts(
        _model_dump(payload),
        changed_by=_changed_by(admin),
    )
    return _legacy_config()
