"""Minecraft notify plugin."""

from nonebot import get_driver

from xiaomiao_bot.presentation.http.minecraft_routes import router

driver = get_driver()
driver.server_app.include_router(router)

