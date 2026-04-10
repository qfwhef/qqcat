"""Admin API plugin."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from nonebot import get_driver

from xiaomiao_bot.presentation.http.admin_routes import router


def _register_admin_ui() -> None:
    driver = get_driver()
    app = driver.server_app
    if getattr(app.state, "xiaomiao_admin_ui_registered", False):
        return

    project_root = Path(__file__).resolve().parents[2]
    dist_dir = project_root / "admin_web" / "dist"
    assets_dir = dist_dir / "assets"

    app.include_router(router)
    app.mount(
        "/admin-ui/assets",
        StaticFiles(directory=str(assets_dir), check_dir=False),
        name="xiaomiao-admin-ui-assets",
    )

    ui_router = APIRouter(include_in_schema=False)

    def _resolve_ui_file(path: str = "") -> Path | None:
        if path:
            target = (dist_dir / path).resolve()
            try:
                target.relative_to(dist_dir.resolve())
            except ValueError:
                return None
            if target.is_file():
                return target
        index_file = dist_dir / "index.html"
        if index_file.is_file():
            return index_file
        return None

    @ui_router.get("/admin-ui", response_model=None)
    @ui_router.get("/admin-ui/", response_model=None)
    async def serve_admin_ui_root():
        target = _resolve_ui_file()
        if target is None:
            return HTMLResponse(
                "<h1>管理后台前端尚未构建</h1><p>请先在项目根目录执行前端构建。</p>",
                status_code=503,
            )
        return FileResponse(target)

    @ui_router.get("/admin-ui/{path:path}", response_model=None)
    async def serve_admin_ui_path(path: str):
        target = _resolve_ui_file(path)
        if target is None:
            return HTMLResponse(
                "<h1>管理后台前端尚未构建</h1><p>请先在项目根目录执行前端构建。</p>",
                status_code=503,
            )
        return FileResponse(target)

    app.include_router(ui_router)
    app.state.xiaomiao_admin_ui_registered = True


_register_admin_ui()
