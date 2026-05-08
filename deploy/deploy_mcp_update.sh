#!/usr/bin/env bash
set -e
PROJECT=/root/mybot/xiaomiao_v2
ZIP=/root/qqcat-mcp-update-with-dist.zip
TS=$(date +%Y%m%d_%H%M%S)
BACKUP=/root/qqcat_backup_$TS
mkdir -p "$BACKUP"
cd "$PROJECT"
for p in README.md pyproject.toml sql/schema.sql admin_web/src/api/admin.ts admin_web/src/layouts/AdminLayout.vue admin_web/src/router/index.ts admin_web/src/views/McpView.vue src/xiaomiao_bot/application/admin_service.py src/xiaomiao_bot/bootstrap/container.py src/xiaomiao_bot/presentation/http/admin_routes.py src/xiaomiao_bot/tools/registry.py src/xiaomiao_bot/tools/mcp_client.py admin_web/dist; do
  if [ -e "$p" ]; then
    mkdir -p "$BACKUP/$(dirname "$p")"
    cp -a "$p" "$BACKUP/$p"
  fi
done
python3 -m zipfile -e "$ZIP" "$PROJECT"
echo "backup=$BACKUP"
echo "extracted"
docker exec xiaomiao-bot bash -lc 'cd /app && python -m pip install -U pip && pip install -e .'
echo "python deps installed"
