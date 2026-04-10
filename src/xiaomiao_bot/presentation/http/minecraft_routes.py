"""Minecraft notify routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...bootstrap.container import get_container

router = APIRouter()


class MinecraftNotifyPayload(BaseModel):
    message: str
    secret: str = ""
    group_ids: list[int] | None = None


@router.post("/minecraft/restart")
async def minecraft_restart_notify(data: MinecraftNotifyPayload) -> dict:
    try:
        return await get_container().minecraft_service.notify_restart(
            data.message,
            data.secret,
            group_ids=data.group_ids,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
