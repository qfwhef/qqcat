"""MCP client helpers for one-shot tool discovery and execution."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


class McpClientError(RuntimeError):
    """Raised when an MCP server cannot be reached or used."""


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump(mode="json"))
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    return str(value)


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    raw = _to_jsonable(tool)
    if isinstance(raw, dict):
        return raw
    return {"name": str(getattr(tool, "name", "")), "description": str(getattr(tool, "description", ""))}


class McpClientManager:
    """Connects to configured MCP servers and exposes their tools."""

    @asynccontextmanager
    async def _session(self, config: dict[str, Any]) -> AsyncIterator[Any]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            from mcp.client.streamable_http import streamablehttp_client
        except Exception as exc:  # noqa: BLE001
            raise McpClientError("未安装 MCP SDK，请先安装项目依赖") from exc

        transport = str(config.get("transport") or "").strip().lower()
        timeout_seconds = int(config.get("timeout_seconds") or 15)
        if transport == "stdio":
            command = str(config.get("command") or "").strip()
            if not command:
                raise McpClientError("stdio MCP 服务未配置 command")
            args = config.get("args_json") or []
            env = config.get("env_json") or None
            if not isinstance(args, list):
                raise McpClientError("args_json 必须是数组")
            if env is not None and not isinstance(env, dict):
                raise McpClientError("env_json 必须是对象")
            params = StdioServerParameters(
                command=command,
                args=[str(item) for item in args],
                env={str(key): str(value) for key, value in env.items()} if env else None,
            )
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await asyncio.wait_for(session.initialize(), timeout=timeout_seconds)
                    yield session
            return

        if transport == "streamable_http":
            url = str(config.get("url") or "").strip()
            if not url:
                raise McpClientError("streamable_http MCP 服务未配置 URL")
            headers = config.get("headers_json") or None
            if headers is not None and not isinstance(headers, dict):
                raise McpClientError("headers_json 必须是对象")
            rendered_headers = {str(key): str(value) for key, value in headers.items()} if headers else None
            async with streamablehttp_client(url, headers=rendered_headers) as (
                read_stream,
                write_stream,
                _get_session_id,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await asyncio.wait_for(session.initialize(), timeout=timeout_seconds)
                    yield session
            return

        raise McpClientError("MCP transport 仅支持 stdio 或 streamable_http")

    async def list_tools(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        timeout_seconds = int(config.get("timeout_seconds") or 15)
        async with self._session(config) as session:
            response = await asyncio.wait_for(session.list_tools(), timeout=timeout_seconds)
        tools = getattr(response, "tools", None)
        if tools is None and isinstance(response, dict):
            tools = response.get("tools")
        result: list[dict[str, Any]] = []
        for tool in tools or []:
            item = _tool_to_dict(tool)
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            result.append(
                {
                    "name": name,
                    "description": str(item.get("description") or ""),
                    "input_schema": item.get("inputSchema") or item.get("input_schema") or {},
                }
            )
        return result

    async def call_tool(
        self,
        config: dict[str, Any],
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        timeout_seconds = int(config.get("timeout_seconds") or 15)
        async with self._session(config) as session:
            response = await asyncio.wait_for(
                session.call_tool(tool_name, arguments=arguments),
                timeout=timeout_seconds,
            )
        return _to_jsonable(response)
