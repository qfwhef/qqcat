#!/usr/bin/env bash
set -e
printf '== files ==\n'
ls -l /root/mybot/xiaomiao_v2/admin_web/src/views/McpView.vue /root/mybot/xiaomiao_v2/src/xiaomiao_bot/tools/mcp_client.py
printf '== container tools before ==\n'
docker exec xiaomiao-bot bash -lc 'command -v node || true; command -v npm || true; command -v npx || true; command -v uvx || true; command -v git || true'
printf '== compile check ==\n'
docker exec xiaomiao-bot bash -lc 'cd /app && python -m compileall -q src && python -c "from mcp import ClientSession, StdioServerParameters; from mcp.client.stdio import stdio_client; from mcp.client.streamable_http import streamablehttp_client; print(\"mcp imports ok\")"'
printf '== install runtime tools if missing ==\n'
docker exec xiaomiao-bot bash -lc 'set -e; if ! command -v npx >/dev/null 2>&1; then apt-get update && apt-get install -y nodejs npm; fi; if ! command -v git >/dev/null 2>&1; then apt-get update && apt-get install -y git; fi; if ! command -v uvx >/dev/null 2>&1; then python -m pip install uv; fi'
printf '== container tools after ==\n'
docker exec xiaomiao-bot bash -lc 'node --version 2>/dev/null || true; npm --version 2>/dev/null || true; npx --version 2>/dev/null || true; uvx --version 2>/dev/null || true; git --version 2>/dev/null || true'
printf '== restart ==\n'
docker restart xiaomiao-bot
sleep 8
printf '== ps ==\n'
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'NAMES|xiaomiao-bot|napcat|mysql'
printf '== logs ==\n'
docker logs --tail=120 xiaomiao-bot
printf '== http smoke ==\n'
curl -I --max-time 8 http://127.0.0.1:8080/admin-ui/login || true
