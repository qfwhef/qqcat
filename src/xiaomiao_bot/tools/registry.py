"""Function calling tool registry."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from nonebot.adapters.onebot.v11 import Event

from ..application.secret_service import SecretService, secret_service
from ..core.config import settings
from ..core.logging import get_logger
from ..core.ttl_cache import TimedValueCache
from ..infrastructure.database import database, dumps_json, loads_json
from .mcp_client import McpClientManager
from .mcp_descriptions import localize_mcp_tool

logger = get_logger("ToolRegistry")
ToolHandler = Callable[[dict[str, Any], Event], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    tool_type: str = "builtin"
    display_name: str | None = None
    admin_only: bool = False


class ToolRegistry:
    """Built-in and runtime-configured tools for function calling."""

    BUILTIN_DISPLAY_NAMES = {
        "get_current_time": "当前时间",
        "web_search": "网页搜索",
        "web_fetch": "网页抓取",
        "get_weather": "天气查询",
    }
    PYTHON_TOOL_RUNNER = r"""
import inspect
import json
import sys
import traceback

payload = json.loads(sys.stdin.read() or "{}")
code = str(payload.get("code", ""))
entry = str(payload.get("entry", "main"))
arguments = payload.get("arguments", {})
allow_import = bool(payload.get("allow_import", False))

safe_builtins = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}
if allow_import:
    safe_builtins["__import__"] = __import__

namespace = {
    "__builtins__": safe_builtins,
    "json": json,
}

try:
    exec(code, namespace, namespace)
    func = namespace.get(entry)
    if not callable(func):
        raise ValueError(f"入口函数不存在或不可调用: {entry}")
    result = func(arguments)
    if inspect.iscoroutine(result):
        raise ValueError("Python 工具不支持 async 入口函数")
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, default=str))
except Exception as exc:  # noqa: BLE001
    print(json.dumps({"ok": False, "error": str(exc), "trace": traceback.format_exc(limit=2)}, ensure_ascii=False))
"""

    def __init__(self, secret_service_instance: SecretService | None = None) -> None:
        self._builtin_tools: dict[str, ToolDefinition] = {}
        self.secret_service = secret_service_instance or secret_service
        self.mcp_client = McpClientManager()
        self._runtime_tools_cache: TimedValueCache[dict[str, ToolDefinition]] = TimedValueCache(
            ttl_seconds=5.0
        )
        self._ensure_tool_table()
        self._ensure_mcp_tables()
        self._register_builtin_tools()
        self._seed_builtin_rows()

    def _ensure_tool_table(self) -> None:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_tool_config (
                id BIGINT NOT NULL AUTO_INCREMENT,
                tool_name VARCHAR(64) NOT NULL,
                display_name VARCHAR(128) NULL,
                description TEXT NOT NULL,
                parameters_json JSON NULL,
                tool_type VARCHAR(16) NOT NULL DEFAULT 'builtin',
                method VARCHAR(16) NULL,
                url TEXT NULL,
                headers_json JSON NULL,
                body_template TEXT NULL,
                python_code LONGTEXT NULL,
                python_entry VARCHAR(64) NULL,
                python_allow_network TINYINT(1) NOT NULL DEFAULT 0,
                python_timeout_seconds INT UNSIGNED NOT NULL DEFAULT 8,
                timeout_seconds INT UNSIGNED NOT NULL DEFAULT 15,
                is_enabled TINYINT(1) NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uk_tool_name (tool_name),
                KEY idx_tool_type_enabled (tool_type, is_enabled)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工具配置表'
            """,
            (),
        )
        self._ensure_python_tool_columns()

    def _ensure_python_tool_columns(self) -> None:
        # 旧版本数据库没有 python 工具字段，这里做无感补列升级。
        column_defs: dict[str, str] = {
            "python_code": "ADD COLUMN python_code LONGTEXT NULL AFTER body_template",
            "python_entry": "ADD COLUMN python_entry VARCHAR(64) NULL AFTER python_code",
            "python_allow_network": "ADD COLUMN python_allow_network TINYINT(1) NOT NULL DEFAULT 0 AFTER python_entry",
            "python_timeout_seconds": (
                "ADD COLUMN python_timeout_seconds INT UNSIGNED NOT NULL DEFAULT 8 "
                "AFTER python_allow_network"
            ),
        }
        for column_name, ddl in column_defs.items():
            row = database.fetch_one(
                """
                SELECT COUNT(1) AS cnt
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'bot_tool_config'
                  AND COLUMN_NAME = %s
                """,
                (column_name,),
            )
            if int((row or {}).get("cnt") or 0) > 0:
                continue
            database.execute(f"ALTER TABLE bot_tool_config {ddl}", ())
            logger.info("已补齐工具表字段: %s", column_name)

    def _ensure_mcp_tables(self) -> None:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_mcp_server_config (
                id BIGINT NOT NULL AUTO_INCREMENT,
                server_name VARCHAR(64) NOT NULL,
                display_name VARCHAR(128) NULL,
                transport VARCHAR(32) NOT NULL,
                command TEXT NULL,
                args_json JSON NULL,
                env_json JSON NULL,
                url TEXT NULL,
                headers_json JSON NULL,
                timeout_seconds INT UNSIGNED NOT NULL DEFAULT 15,
                is_enabled TINYINT(1) NOT NULL DEFAULT 1,
                admin_only TINYINT(1) NOT NULL DEFAULT 1,
                last_status VARCHAR(32) NULL,
                last_error TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uk_mcp_server_name (server_name),
                KEY idx_mcp_server_enabled (is_enabled)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='MCP 服务配置表'
            """,
            (),
        )
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_mcp_tool_cache (
                id BIGINT NOT NULL AUTO_INCREMENT,
                server_name VARCHAR(64) NOT NULL,
                exposed_tool_name VARCHAR(64) NOT NULL,
                original_tool_name VARCHAR(128) NOT NULL,
                display_name VARCHAR(128) NULL,
                description TEXT NOT NULL,
                parameters_json JSON NULL,
                is_enabled TINYINT(1) NOT NULL DEFAULT 1,
                admin_only TINYINT(1) NOT NULL DEFAULT 1,
                last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uk_mcp_exposed_tool_name (exposed_tool_name),
                UNIQUE KEY uk_mcp_server_original_tool (server_name, original_tool_name),
                KEY idx_mcp_tool_enabled (is_enabled),
                KEY idx_mcp_tool_server (server_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='MCP 工具缓存表'
            """,
            (),
        )
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_mcp_tool_call_log (
                id BIGINT NOT NULL AUTO_INCREMENT,
                session_type VARCHAR(16) NOT NULL,
                session_id BIGINT NOT NULL,
                user_id BIGINT NULL,
                server_name VARCHAR(64) NOT NULL,
                exposed_tool_name VARCHAR(64) NOT NULL,
                original_tool_name VARCHAR(128) NOT NULL,
                arguments_json JSON NULL,
                result_excerpt MEDIUMTEXT NULL,
                error_text TEXT NULL,
                is_success TINYINT(1) NOT NULL DEFAULT 1,
                latency_ms INT UNSIGNED NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY idx_mcp_call_time (created_at),
                KEY idx_mcp_call_server_time (server_name, created_at),
                KEY idx_mcp_call_tool_time (exposed_tool_name, created_at),
                KEY idx_mcp_call_session_time (session_type, session_id, created_at),
                KEY idx_mcp_call_success_time (is_success, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='MCP 工具调用日志表'
            """,
            (),
        )

    def _seed_builtin_rows(self) -> None:
        for definition in self._builtin_tools.values():
            database.execute(
                """
                INSERT INTO bot_tool_config(
                    tool_name, display_name, description, parameters_json, tool_type, is_enabled
                ) VALUES(%s, %s, %s, %s, 'builtin', 1)
                ON DUPLICATE KEY UPDATE
                    display_name=COALESCE(display_name, VALUES(display_name)),
                    description=COALESCE(NULLIF(description, ''), VALUES(description)),
                    parameters_json=COALESCE(parameters_json, VALUES(parameters_json))
                """,
                (
                    definition.name,
                    definition.display_name or self.BUILTIN_DISPLAY_NAMES.get(definition.name, definition.name),
                    definition.description,
                    dumps_json(definition.parameters),
                ),
            )

    def _register_builtin_tools(self) -> None:
        self.register(
            ToolDefinition(
                name="get_current_time",
                display_name="当前时间",
                description="获取当前服务器时间，返回 ISO 格式和可读时间。",
                parameters={
                    "type": "object",
                    "properties": {
                        "timezone": {"type": "string", "description": "IANA 时区名称，默认 Asia/Shanghai"}
                    },
                    "additionalProperties": False,
                },
                handler=self._get_current_time,
            )
        )
        self.register(
            ToolDefinition(
                name="web_search",
                display_name="网页搜索",
                description="联网搜索资料，返回前几条搜索结果标题、摘要和链接。",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "搜索关键词。"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=self._web_search,
            )
        )
        self.register(
            ToolDefinition(
                name="web_fetch",
                display_name="网页抓取",
                description="抓取指定网页正文内容，返回标题、链接和正文摘要。",
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "要抓取的网页链接。"}},
                    "required": ["url"],
                    "additionalProperties": False,
                },
                handler=self._web_fetch,
            )
        )
        self.register(
            ToolDefinition(
                name="get_weather",
                display_name="天气查询",
                description="查询指定城市天气，支持实况天气和未来三天预报。",
                parameters={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名称，例如北京、上海。"},
                        "mode": {
                            "type": "string",
                            "description": "查询模式：current 或 daily。",
                            "enum": ["current", "daily"],
                        },
                    },
                    "required": ["city"],
                    "additionalProperties": False,
                },
                handler=self._get_weather,
            )
        )

    def register(self, definition: ToolDefinition) -> None:
        self._builtin_tools[definition.name] = definition

    def get_openai_tools(self, allowed_tool_names: set[str] | None = None) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                },
            }
            for definition in self._get_runtime_tools().values()
            if allowed_tool_names is None or definition.name in allowed_tool_names
        ]

    def get_runtime_tool_names(self, tool_type: str | None = None) -> set[str]:
        return {
            definition.name
            for definition in self._get_runtime_tools().values()
            if tool_type is None or definition.tool_type == tool_type
        }

    async def execute(self, tool_name: str, arguments_json: str | None, event: Event) -> dict[str, Any]:
        definition = self._get_runtime_tools().get(tool_name)
        if not definition:
            return {"ok": False, "error": f"Unknown or disabled tool: {tool_name}"}
        if definition.admin_only and not self._is_admin_event(event):
            return {"ok": False, "tool": tool_name, "error": "该工具仅管理员可用"}

        try:
            arguments = json.loads(arguments_json) if arguments_json else {}
            if not isinstance(arguments, dict):
                return {"ok": False, "error": "Tool arguments must be an object"}
        except json.JSONDecodeError:
            return {"ok": False, "error": "Tool arguments are not valid JSON"}

        try:
            result = await definition.handler(arguments, event)
            return {"ok": True, "tool": tool_name, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": tool_name, "error": str(exc)}

    def _get_runtime_tools(self) -> dict[str, ToolDefinition]:
        return self._runtime_tools_cache.get(self._build_runtime_tools)

    def clear_runtime_tool_cache(self) -> None:
        self._runtime_tools_cache.clear()

    def _build_runtime_tools(self) -> dict[str, ToolDefinition]:
        rows = self._load_tool_rows()
        runtime_tools: dict[str, ToolDefinition] = {}

        for name, builtin in self._builtin_tools.items():
            row = rows.get(name)
            is_enabled = True if row is None else bool(row.get("is_enabled"))
            if not is_enabled:
                continue
            runtime_tools[name] = ToolDefinition(
                name=name,
                display_name=str(row.get("display_name") or builtin.display_name or name) if row else builtin.display_name,
                description=str(row.get("description") or builtin.description) if row else builtin.description,
                parameters=self._tool_parameters(row, builtin.parameters),
                handler=builtin.handler,
                tool_type="builtin",
            )

        for row in rows.values():
            if str(row.get("tool_type") or "") != "http":
                continue
            if not bool(row.get("is_enabled")):
                continue
            tool_name = str(row["tool_name"])
            runtime_tools[tool_name] = ToolDefinition(
                name=tool_name,
                display_name=str(row.get("display_name") or tool_name),
                description=str(row.get("description") or ""),
                parameters=self._tool_parameters(row, {"type": "object", "properties": {}, "additionalProperties": True}),
                handler=self._make_http_handler(dict(row)),
                tool_type="http",
            )

        for row in rows.values():
            if str(row.get("tool_type") or "") != "python":
                continue
            if not bool(row.get("is_enabled")):
                continue
            tool_name = str(row["tool_name"])
            runtime_tools[tool_name] = ToolDefinition(
                name=tool_name,
                display_name=str(row.get("display_name") or tool_name),
                description=str(row.get("description") or ""),
                parameters=self._tool_parameters(
                    row,
                    {"type": "object", "properties": {}, "additionalProperties": True},
                ),
                handler=self._make_python_handler(dict(row)),
                tool_type="python",
            )
        for row in self._load_enabled_mcp_tool_rows():
            tool_name = str(row["exposed_tool_name"])
            localized = localize_mcp_tool(
                str(row.get("server_name") or ""),
                str(row.get("original_tool_name") or ""),
                str(row.get("description") or ""),
            )
            runtime_tools[tool_name] = ToolDefinition(
                name=tool_name,
                display_name=str(localized["display_name"] or row.get("display_name") or tool_name),
                description=str(localized["description"] or row.get("description") or ""),
                parameters=self._tool_parameters(
                    {"parameters_json": row.get("parameters_json")},
                    {"type": "object", "properties": {}, "additionalProperties": True},
                ),
                handler=self._make_mcp_handler(dict(row)),
                tool_type="mcp",
                admin_only=bool(row.get("admin_only")) or bool(row.get("server_admin_only")),
            )
        return runtime_tools

    def _load_tool_rows(self) -> dict[str, dict[str, Any]]:
        rows = database.fetch_all(
            """
            SELECT id, tool_name, display_name, description, parameters_json, tool_type,
                   method, url, headers_json, body_template,
                   python_code, python_entry, python_allow_network, python_timeout_seconds,
                   timeout_seconds, is_enabled,
                   created_at, updated_at
            FROM bot_tool_config
            ORDER BY id ASC
            """,
            (),
        )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            result[str(row["tool_name"])] = row
        return result

    def _load_enabled_mcp_tool_rows(self) -> list[dict[str, Any]]:
        rows = database.fetch_all(
            """
            SELECT
                t.id, t.server_name, t.exposed_tool_name, t.original_tool_name,
                t.display_name, t.description, t.parameters_json,
                t.is_enabled, t.admin_only, t.last_seen_at, t.created_at, t.updated_at,
                s.transport, s.command, s.args_json, s.env_json, s.url, s.headers_json,
                s.timeout_seconds, s.is_enabled AS server_enabled, s.admin_only AS server_admin_only
            FROM bot_mcp_tool_cache t
            INNER JOIN bot_mcp_server_config s ON t.server_name=s.server_name
            WHERE t.is_enabled=1 AND s.is_enabled=1
            ORDER BY t.server_name ASC, t.original_tool_name ASC
            """,
            (),
        )
        for row in rows:
            self._parse_mcp_config_json_fields(row)
        return rows

    @staticmethod
    def _tool_parameters(row: dict[str, Any] | None, fallback: dict[str, Any]) -> dict[str, Any]:
        if not row:
            return fallback
        raw = row.get("parameters_json")
        if isinstance(raw, dict):
            return raw
        parsed = loads_json(str(raw) if raw is not None else None, fallback)
        return parsed if isinstance(parsed, dict) else fallback

    def _make_http_handler(self, row: dict[str, Any]) -> ToolHandler:
        async def handler(arguments: dict[str, Any], event: Event) -> dict[str, Any]:
            _ = event
            return self._execute_http_tool(row, arguments)

        return handler

    def _make_python_handler(self, row: dict[str, Any]) -> ToolHandler:
        async def handler(arguments: dict[str, Any], event: Event) -> dict[str, Any]:
            _ = event
            return await asyncio.to_thread(self._execute_python_tool, row, arguments)

        return handler

    def _make_mcp_handler(self, row: dict[str, Any]) -> ToolHandler:
        async def handler(arguments: dict[str, Any], event: Event) -> dict[str, Any]:
            return await self._execute_mcp_tool(row, arguments, event)

        return handler

    def _execute_http_tool(self, row: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
        method = str(row.get("method") or "GET").upper()
        url = self._render_string_template(str(row.get("url") or ""), arguments).strip()
        if not url:
            raise ValueError("HTTP 工具未配置 URL")
        headers = loads_json(str(row.get("headers_json")) if row.get("headers_json") is not None else None, {})
        if not isinstance(headers, dict):
            headers = {}
        rendered_headers = {
            str(key): self._render_string_template(str(value), arguments)
            for key, value in headers.items()
        }
        timeout_seconds = int(row.get("timeout_seconds") or 15)

        body_data: bytes | None = None
        final_url = url
        if method in {"GET", "DELETE"}:
            final_url = self._append_query_params(url, arguments)
        else:
            body_value = self._render_body_template(str(row.get("body_template") or ""), arguments)
            if isinstance(body_value, (dict, list)):
                body_data = json.dumps(body_value, ensure_ascii=False).encode("utf-8")
                rendered_headers.setdefault("Content-Type", "application/json")
            elif body_value is None:
                body_data = None
            else:
                body_data = str(body_value).encode("utf-8")

        request = Request(
            final_url,
            data=body_data,
            headers=rendered_headers,
            method=method,
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="ignore")
            status = int(getattr(response, "status", 200))
            response_headers = dict(response.headers.items())
        parsed_body = loads_json(body, body)
        return {
            "status": status,
            "url": final_url,
            "headers": response_headers,
            "body": parsed_body,
        }

    def _execute_python_tool(self, row: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
        code = str(row.get("python_code") or "").strip()
        if not code:
            raise ValueError("Python 工具未配置代码")
        if len(code) > 60000:
            raise ValueError("Python 工具代码过长，最大 60000 字符")

        entry = str(row.get("python_entry") or "main").strip() or "main"
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", entry):
            raise ValueError("python_entry 非法，仅允许字母数字下划线且不能数字开头")

        timeout_seconds = int(row.get("python_timeout_seconds") or 8)
        timeout_seconds = min(60, max(1, timeout_seconds))
        allow_network = bool(row.get("python_allow_network"))
        started_at = time.perf_counter()
        payload = {
            "code": code,
            "entry": entry,
            "arguments": arguments,
            # 只放开 import，不直接注入网络库，依旧由代码显式导入。
            "allow_import": allow_network,
        }
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", self.PYTHON_TOOL_RUNNER],
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"Python 工具执行超时（>{timeout_seconds}s）") from exc

        stderr_text = proc.stderr.decode("utf-8", errors="ignore").strip()
        stdout_text = proc.stdout.decode("utf-8", errors="ignore").strip()
        if proc.returncode != 0:
            raise ValueError(stderr_text[:300] or f"Python 子进程退出码异常: {proc.returncode}")
        if not stdout_text:
            raise ValueError("Python 工具无输出")

        wrapper = loads_json(stdout_text, {})
        if not isinstance(wrapper, dict):
            raise ValueError("Python 工具输出格式非法")
        if not bool(wrapper.get("ok")):
            error_text = str(wrapper.get("error") or "Python 工具执行失败")
            raise ValueError(error_text[:300])

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return {
            "entry": entry,
            "runtime_ms": elapsed_ms,
            "allow_network": allow_network,
            "data": wrapper.get("result"),
        }

    async def _execute_mcp_tool(self, row: dict[str, Any], arguments: dict[str, Any], event: Event) -> dict[str, Any]:
        config = self._mcp_config_from_tool_row(row)
        started_at = time.perf_counter()
        server_name = str(row.get("server_name") or "")
        original_tool_name = str(row.get("original_tool_name") or "")
        exposed_tool_name = str(row.get("exposed_tool_name") or "")
        try:
            result = await self.mcp_client.call_tool(
                config,
                tool_name=original_tool_name,
                arguments=arguments,
            )
            runtime_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_mcp_tool_call(
                event=event,
                server_name=server_name,
                exposed_tool_name=exposed_tool_name,
                original_tool_name=original_tool_name,
                arguments=arguments,
                is_success=True,
                latency_ms=runtime_ms,
                result=result,
                error_text=None,
            )
            return {
                "server_name": server_name,
                "original_tool_name": original_tool_name,
                "runtime_ms": runtime_ms,
                "data": result,
            }
        except Exception as exc:
            runtime_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_mcp_tool_call(
                event=event,
                server_name=server_name,
                exposed_tool_name=exposed_tool_name,
                original_tool_name=original_tool_name,
                arguments=arguments,
                is_success=False,
                latency_ms=runtime_ms,
                result=None,
                error_text=str(exc),
            )
            raise

    async def test_mcp_server(self, server_name: str) -> dict[str, Any]:
        config = self._load_mcp_server_config(server_name)
        if not config:
            raise ValueError("MCP 服务不存在")
        started_at = time.perf_counter()
        try:
            tools = await self.mcp_client.list_tools(config)
            self._update_mcp_server_status(server_name, "ok", None)
            return {
                "ok": True,
                "server_name": server_name,
                "tool_count": len(tools),
                "tools": tools,
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
            }
        except Exception as exc:
            self._update_mcp_server_status(server_name, "error", str(exc)[:500])
            raise

    async def refresh_mcp_tools(self, server_name: str) -> dict[str, Any]:
        result = await self.test_mcp_server(server_name)
        tools = result.get("tools") or []
        if not isinstance(tools, list):
            tools = []
        seen_names: set[str] = set()
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            original_name = str(tool.get("name") or "").strip()
            if not original_name:
                continue
            exposed_name = self._make_mcp_exposed_tool_name(server_name, original_name)
            seen_names.add(original_name)
            localized = localize_mcp_tool(server_name, original_name, str(tool.get("description") or ""))
            display_name = localized["display_name"] or original_name
            description = localized["description"]
            parameters = tool.get("input_schema") or {"type": "object", "properties": {}, "additionalProperties": True}
            if not isinstance(parameters, dict):
                parameters = {"type": "object", "properties": {}, "additionalProperties": True}
            database.execute(
                """
                INSERT INTO bot_mcp_tool_cache(
                    server_name, exposed_tool_name, original_tool_name, display_name,
                    description, parameters_json, is_enabled, admin_only, last_seen_at
                ) VALUES(%s, %s, %s, %s, %s, %s, 1, 1, NOW())
                ON DUPLICATE KEY UPDATE
                    exposed_tool_name=VALUES(exposed_tool_name),
                    display_name=VALUES(display_name),
                    description=VALUES(description),
                    parameters_json=VALUES(parameters_json),
                    last_seen_at=VALUES(last_seen_at)
                """,
                (
                    server_name,
                    exposed_name,
                    original_name,
                    display_name,
                    description,
                    dumps_json(parameters),
                ),
            )
        self.clear_runtime_tool_cache()
        return {
            **result,
            "refreshed_count": len(seen_names),
        }

    def _load_mcp_server_config(self, server_name: str) -> dict[str, Any] | None:
        row = database.fetch_one(
            """
            SELECT
                server_name, display_name, transport, command, args_json, env_json,
                url, headers_json, timeout_seconds, is_enabled, admin_only,
                last_status, last_error, created_at, updated_at
            FROM bot_mcp_server_config
            WHERE server_name=%s
            LIMIT 1
            """,
            (server_name,),
        )
        if not row:
            return None
        self._parse_mcp_config_json_fields(row)
        return row

    @staticmethod
    def _parse_mcp_config_json_fields(row: dict[str, Any]) -> None:
        for field, fallback in {
            "args_json": [],
            "env_json": {},
            "headers_json": {},
            "parameters_json": {},
        }.items():
            if field not in row:
                continue
            value = row.get(field)
            if isinstance(value, (dict, list)):
                continue
            row[field] = loads_json(str(value) if value is not None else None, fallback)

    @staticmethod
    def _mcp_config_from_tool_row(row: dict[str, Any]) -> dict[str, Any]:
        config = dict(row)
        ToolRegistry._parse_mcp_config_json_fields(config)
        return config

    @staticmethod
    def _make_mcp_exposed_tool_name(server_name: str, original_name: str) -> str:
        def slug(value: str) -> str:
            normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
            normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
            return normalized or "tool"

        base = f"mcp_{slug(server_name)}_{slug(original_name)}"
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", base):
            return base
        digest = hashlib.sha1(f"{server_name}:{original_name}".encode("utf-8")).hexdigest()[:8]
        trimmed = base[: 64 - 9].rstrip("_")
        if not trimmed or trimmed[0].isdigit():
            trimmed = f"mcp_{trimmed}"[: 64 - 9].rstrip("_")
        return f"{trimmed}_{digest}"

    @staticmethod
    def _update_mcp_server_status(server_name: str, status_text: str, error_text: str | None) -> None:
        database.execute(
            """
            UPDATE bot_mcp_server_config
            SET last_status=%s, last_error=%s
            WHERE server_name=%s
            """,
            (status_text, error_text, server_name),
        )

    @staticmethod
    def _log_mcp_tool_call(
        *,
        event: Event,
        server_name: str,
        exposed_tool_name: str,
        original_tool_name: str,
        arguments: dict[str, Any],
        is_success: bool,
        latency_ms: int,
        result: Any,
        error_text: str | None,
    ) -> None:
        try:
            group_id = getattr(event, "group_id", None)
            user_id = int(getattr(event, "user_id", 0) or 0)
            session_type = "group" if group_id not in {None, ""} else "private"
            session_id = int(group_id or user_id or 0)
            result_excerpt = ToolRegistry._truncate_debug_json(result, 4000) if result is not None else None
            database.execute(
                """
                INSERT INTO bot_mcp_tool_call_log(
                    session_type, session_id, user_id, server_name, exposed_tool_name,
                    original_tool_name, arguments_json, result_excerpt, error_text,
                    is_success, latency_ms
                ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_type,
                    session_id,
                    user_id,
                    server_name,
                    exposed_tool_name,
                    original_tool_name,
                    ToolRegistry._truncate_debug_json(arguments, 8000),
                    result_excerpt,
                    str(error_text or "")[:2000] if error_text else None,
                    1 if is_success else 0,
                    latency_ms,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP 工具调用日志写入失败: %s", exc)

    @staticmethod
    def _truncate_debug_json(value: Any, limit: int) -> str:
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return text
        return json.dumps({"_truncated": True, "excerpt": text[:limit]}, ensure_ascii=False)

    @staticmethod
    def _is_admin_event(event: Event) -> bool:
        user_id = int(getattr(event, "user_id", 0) or 0)
        if user_id <= 0:
            return False
        if user_id == int(settings.admin_uid or 0):
            return True
        row = database.fetch_one(
            "SELECT user_id FROM bot_admin_user WHERE user_id=%s AND is_active=1 LIMIT 1",
            (user_id,),
        )
        return bool(row)

    @staticmethod
    def _append_query_params(url: str, arguments: dict[str, Any]) -> str:
        parsed = urlparse(url)
        current = dict(parse_qsl(parsed.query, keep_blank_values=True))
        for key, value in arguments.items():
            if value is None:
                continue
            current[str(key)] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        new_query = urlencode(current, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    def _render_body_template(self, template: str, arguments: dict[str, Any]) -> Any:
        if not template.strip():
            return arguments
        try:
            parsed = json.loads(template)
            return self._render_template_value(parsed, arguments)
        except Exception:
            return self._render_string_template(template, arguments)

    def _render_template_value(self, value: Any, arguments: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {str(key): self._render_template_value(item, arguments) for key, item in value.items()}
        if isinstance(value, list):
            return [self._render_template_value(item, arguments) for item in value]
        if isinstance(value, str):
            match = re.fullmatch(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", value)
            if match:
                return arguments.get(match.group(1))
            return self._render_string_template(value, arguments)
        return value

    @staticmethod
    def _render_string_template(template: str, arguments: dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            value = arguments.get(key, "")
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            return "" if value is None else str(value)

        return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace, template)

    async def _get_current_time(self, arguments: dict[str, Any], event: Event) -> dict[str, Any]:
        _ = arguments
        _ = event
        now = datetime.now()
        return {"iso": now.isoformat(timespec="seconds"), "human": now.strftime("%Y-%m-%d %H:%M:%S")}

    async def _web_search(self, arguments: dict[str, Any], event: Event) -> dict[str, Any]:
        _ = event
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        tavily_api_key = self.secret_service.get_secret("TAVILY_API_KEY", settings.tavily_api_key)
        if tavily_api_key:
            try:
                return self._search_tavily(query, tavily_api_key)
            except Exception as exc:
                logger.warning("Tavily search failed, fallback to Serper: %s", exc)
        return self._search_serper(query, self.secret_service.get_secret("SERPER_API_KEY", settings.serper_api_key))

    def _search_tavily(self, query: str, api_key: str) -> dict[str, Any]:
        payload = json.dumps(
            {
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": True,
            }
        ).encode("utf-8")
        request = Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "xiaomiao-refactor/1.0"},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body)
        results: list[dict[str, str]] = []
        for item in data.get("results", []):
            title = str(item.get("title", "")).strip()
            href = str(item.get("url", "")).strip()
            content = str(item.get("content", "")).strip()[:600]
            if title and href:
                results.append({"title": title, "url": href, "content": content})
        return {
            "query": query,
            "answer": str(data.get("answer") or "").strip(),
            "results": results[:5],
            "source": "tavily",
        }

    def _search_serper(self, query: str, api_key: str) -> dict[str, Any]:
        payload = json.dumps({"q": query}).encode("utf-8")
        request = Request(
            "https://google.serper.dev/search",
            data=payload,
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
                "User-Agent": "xiaomiao-refactor/1.0",
            },
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body)
        results: list[dict[str, str]] = []
        for item in data.get("organic", []):
            title = str(item.get("title", "")).strip()
            href = str(item.get("link", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            if title and href:
                results.append({"title": title, "url": href, "snippet": snippet})
        return {"query": query, "results": results[:5], "source": "serper"}

    async def _web_fetch(self, arguments: dict[str, Any], event: Event) -> dict[str, Any]:
        _ = event
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ValueError("url is required")
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=15) as response:
            html = response.read().decode("utf-8", errors="ignore")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
        title = self._strip_html(title_match.group(1)) if title_match else ""
        body = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        body = re.sub(r"(?is)<style.*?>.*?</style>", " ", body)
        body = self._strip_html(body)
        body = re.sub(r"\s+", " ", body).strip()
        return {"url": url, "title": title, "content": body[:4000]}

    async def _get_weather(self, arguments: dict[str, Any], event: Event) -> dict[str, Any]:
        _ = event
        city = str(arguments.get("city", "")).strip()
        if not city:
            raise ValueError("city is required")
        mode = str(arguments.get("mode", "current")).strip().lower() or "current"
        if mode not in {"current", "daily"}:
            mode = "current"
        amap_api_key = self.secret_service.get_secret("AMAP_API_KEY", settings.amap_api_key)
        if not amap_api_key:
            raise ValueError("AMAP_API_KEY is not configured")

        geo_url = (
            f"https://restapi.amap.com/v3/geocode/geo?address={quote(city)}"
            f"&key={amap_api_key}&output=json"
        )
        with urlopen(Request(geo_url, headers={"User-Agent": "xiaomiao-refactor/1.0"}), timeout=15) as response:
            geo_body = response.read().decode("utf-8", errors="ignore")
        geo_data = json.loads(geo_body)
        if geo_data.get("status") != "1" or not geo_data.get("geocodes"):
            raise ValueError(f"未找到城市: {city}")

        geocode = geo_data["geocodes"][0]
        adcode = str(geocode.get("adcode", "")).strip()
        resolved_city = geocode.get("city") or geocode.get("province") or city
        province = geocode.get("province") or ""

        extensions = "all" if mode == "daily" else "base"
        weather_url = (
            f"https://restapi.amap.com/v3/weather/weatherInfo?city={adcode}"
            f"&key={amap_api_key}&extensions={extensions}&output=json"
        )
        with urlopen(Request(weather_url, headers={"User-Agent": "xiaomiao-refactor/1.0"}), timeout=15) as response:
            weather_body = response.read().decode("utf-8", errors="ignore")
        weather_data = json.loads(weather_body)
        if weather_data.get("status") != "1":
            raise ValueError(f"天气查询失败: {weather_data.get('info', '未知错误')}")

        if mode == "current":
            live = (weather_data.get("lives") or [None])[0]
            if not live:
                raise ValueError("未获取到实况天气数据")
            return {
                "city": city,
                "resolved_city": str(resolved_city),
                "province": str(province),
                "mode": "current",
                "weather": live.get("weather", ""),
                "temperature_c": live.get("temperature", ""),
                "humidity_percent": live.get("humidity", ""),
                "wind_direction": live.get("winddirection", ""),
                "wind_power": live.get("windpower", ""),
                "report_time": live.get("reporttime", ""),
            }

        forecasts = weather_data.get("forecasts") or []
        if not forecasts:
            raise ValueError("未获取到预报天气数据")
        rows: list[dict[str, Any]] = []
        for cast in forecasts[0].get("casts") or []:
            rows.append(
                {
                    "date": cast.get("date", ""),
                    "week": cast.get("week", ""),
                    "day_weather": cast.get("dayweather", ""),
                    "night_weather": cast.get("nightweather", ""),
                    "temp_max_c": cast.get("daytemp", ""),
                    "temp_min_c": cast.get("nighttemp", ""),
                    "day_wind": cast.get("daywind", ""),
                    "day_wind_power": cast.get("daypower", ""),
                }
            )
        return {
            "city": city,
            "resolved_city": str(resolved_city),
            "province": str(province),
            "mode": "daily",
            "daily": rows,
        }

    @staticmethod
    def _strip_html(text: str) -> str:
        text = re.sub(r"(?is)<.*?>", " ", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
        text = text.replace("&quot;", '"')
        return re.sub(r"\s+", " ", text).strip()
