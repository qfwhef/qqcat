"""Function calling tool registry."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from nonebot.adapters.onebot.v11 import Event

from ..application.secret_service import SecretService, secret_service
from ..core.config import settings
from ..core.logging import get_logger
from ..infrastructure.database import database, dumps_json, loads_json

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


class ToolRegistry:
    """Built-in and runtime-configured tools for function calling."""

    BUILTIN_DISPLAY_NAMES = {
        "get_current_time": "当前时间",
        "web_search": "网页搜索",
        "web_fetch": "网页抓取",
        "get_weather": "天气查询",
    }

    def __init__(self, secret_service_instance: SecretService | None = None) -> None:
        self._builtin_tools: dict[str, ToolDefinition] = {}
        self.secret_service = secret_service_instance or secret_service
        self._ensure_tool_table()
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

    def get_openai_tools(self) -> list[dict[str, Any]]:
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
        ]

    async def execute(self, tool_name: str, arguments_json: str | None, event: Event) -> dict[str, Any]:
        definition = self._get_runtime_tools().get(tool_name)
        if not definition:
            return {"ok": False, "error": f"Unknown or disabled tool: {tool_name}"}

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
        return runtime_tools

    def _load_tool_rows(self) -> dict[str, dict[str, Any]]:
        rows = database.fetch_all(
            """
            SELECT id, tool_name, display_name, description, parameters_json, tool_type,
                   method, url, headers_json, body_template, timeout_seconds, is_enabled,
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
