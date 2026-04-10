"""Migrate shared bot message tables into per-session dynamic tables.

Usage:
    cd /root/mybot/xiaomiao_v2
    source .venv/bin/activate
    python scripts/migrate_shared_messages_to_partitioned_tables.py

This script:
1. Creates the message session registry table when missing
2. Creates per-group / per-private dynamic message tables
3. Copies rows from bot_group_message / bot_private_message while preserving original ids
4. Rebuilds bot_message_session_registry
5. Rewrites bot_ai_call_log.message_table to the dynamic table name

The old shared tables are kept as backup and are not dropped.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from xiaomiao_bot.core.config import settings  # noqa: E402


REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS bot_message_session_registry (
    session_type VARCHAR(16) NOT NULL COMMENT '会话类型：group/private',
    session_id BIGINT NOT NULL COMMENT '群号或QQ号',
    table_name VARCHAR(64) NOT NULL COMMENT '动态消息表名',
    display_name VARCHAR(255) NULL COMMENT '会话展示名',
    total_messages BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '累计消息数',
    last_message_id BIGINT NULL COMMENT '最新消息主键',
    last_message_at DATETIME NULL COMMENT '最新消息时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (session_type, session_id),
    UNIQUE KEY uk_message_session_table (table_name),
    KEY idx_message_session_last_time (session_type, last_message_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息分表注册表'
"""

GROUP_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS `{table_name}` (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    platform_message_id VARCHAR(64) NULL COMMENT '平台原始消息ID',
    group_name VARCHAR(255) NULL COMMENT '群昵称',
    sender_user_id BIGINT NULL COMMENT '发送者QQ',
    sender_nickname VARCHAR(255) NULL COMMENT '发送者昵称',
    sender_card VARCHAR(255) NULL COMMENT '发送者群昵称',
    role VARCHAR(16) NOT NULL COMMENT '消息角色：user/assistant/system/tool',
    message_type VARCHAR(32) NOT NULL DEFAULT 'text' COMMENT '消息类型：text/image/mixed/tool',
    content_text LONGTEXT NOT NULL COMMENT '标准化后的消息文本',
    raw_message_json LONGTEXT NULL COMMENT '原始消息 JSON',
    is_at_bot TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否@机器人',
    is_reply TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为引用消息',
    quoted_platform_message_id VARCHAR(64) NULL COMMENT '被引用的平台消息ID',
    quoted_role VARCHAR(16) NULL COMMENT '被引用消息角色',
    quoted_sender_user_id BIGINT NULL COMMENT '被引用消息发送者QQ',
    quoted_sender_nickname VARCHAR(255) NULL COMMENT '被引用消息发送者昵称',
    quoted_text LONGTEXT NULL COMMENT '被引用消息文本',
    tool_name VARCHAR(64) NULL COMMENT '工具名称',
    tool_args_json JSON NULL COMMENT '工具参数',
    model_name VARCHAR(128) NULL COMMENT '本条消息使用的模型',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '消息时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_platform_message (platform_message_id),
    KEY idx_message_time (created_at),
    KEY idx_sender_time (sender_user_id, created_at),
    KEY idx_role_time (role, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='群聊动态消息表'
"""

PRIVATE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS `{table_name}` (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    platform_message_id VARCHAR(64) NULL COMMENT '平台原始消息ID',
    peer_nickname VARCHAR(255) NULL COMMENT '私聊对端昵称',
    sender_user_id BIGINT NULL COMMENT '发送方QQ',
    sender_nickname VARCHAR(255) NULL COMMENT '发送方昵称',
    role VARCHAR(16) NOT NULL COMMENT '消息角色：user/assistant/system/tool',
    message_type VARCHAR(32) NOT NULL DEFAULT 'text' COMMENT '消息类型：text/image/mixed/tool',
    content_text LONGTEXT NOT NULL COMMENT '标准化后的消息文本',
    raw_message_json LONGTEXT NULL COMMENT '原始消息 JSON',
    is_reply TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为引用消息',
    quoted_platform_message_id VARCHAR(64) NULL COMMENT '被引用的平台消息ID',
    quoted_role VARCHAR(16) NULL COMMENT '被引用消息角色',
    quoted_sender_user_id BIGINT NULL COMMENT '被引用消息发送者QQ',
    quoted_sender_nickname VARCHAR(255) NULL COMMENT '被引用消息发送者昵称',
    quoted_text LONGTEXT NULL COMMENT '被引用消息文本',
    tool_name VARCHAR(64) NULL COMMENT '工具名称',
    tool_args_json JSON NULL COMMENT '工具参数',
    model_name VARCHAR(128) NULL COMMENT '本条消息使用的模型',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '消息时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_platform_message (platform_message_id),
    KEY idx_message_time (created_at),
    KEY idx_sender_time (sender_user_id, created_at),
    KEY idx_role_time (role, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='私聊动态消息表'
"""


@dataclass(slots=True)
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate shared bot message tables into per-session dynamic tables.")
    parser.add_argument("--host", default=settings.mysql_host)
    parser.add_argument("--port", type=int, default=settings.mysql_port)
    parser.add_argument("--user", default=settings.mysql_user)
    parser.add_argument("--password", default=settings.mysql_password)
    parser.add_argument("--database", default=settings.mysql_db)
    parser.add_argument("--skip-group", action="store_true", help="Skip migrating bot_group_message")
    parser.add_argument("--skip-private", action="store_true", help="Skip migrating bot_private_message")
    parser.add_argument("--skip-ai-log-update", action="store_true", help="Skip rewriting bot_ai_call_log.message_table")
    return parser.parse_args()


def connect_db(cfg: DBConfig) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=DictCursor,
    )


def table_exists(cursor: pymysql.cursors.Cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table_name,),
    )
    row = cursor.fetchone() or {}
    return bool(row.get("total"))


def safe_table_name(prefix: str, session_id: int) -> str:
    return f"{prefix}_{int(session_id)}"


def migrate_group_messages(cursor: pymysql.cursors.Cursor) -> dict[str, Any]:
    summary = {"sessions": 0, "rows_inserted": 0}
    if not table_exists(cursor, "bot_group_message"):
        return summary
    cursor.execute("SELECT DISTINCT group_id FROM bot_group_message ORDER BY group_id")
    group_ids = [int(row["group_id"]) for row in cursor.fetchall()]
    for group_id in group_ids:
        table_name = safe_table_name("bot_group_message", group_id)
        cursor.execute(GROUP_TABLE_DDL.format(table_name=table_name))
        inserted = cursor.execute(
            f"""
            INSERT IGNORE INTO `{table_name}` (
                id, platform_message_id, group_name, sender_user_id, sender_nickname, sender_card,
                role, message_type, content_text, raw_message_json, is_at_bot, is_reply,
                quoted_platform_message_id, quoted_role, quoted_sender_user_id, quoted_sender_nickname,
                quoted_text, tool_name, tool_args_json, model_name, created_at
            )
            SELECT
                id, platform_message_id, group_name, sender_user_id, sender_nickname, sender_card,
                role, message_type, content_text, raw_message_json, is_at_bot, is_reply,
                quoted_platform_message_id, quoted_role, quoted_sender_user_id, quoted_sender_nickname,
                quoted_text, tool_name, tool_args_json, model_name, created_at
            FROM bot_group_message
            WHERE group_id=%s
            ORDER BY id
            """,
            (group_id,),
        )
        summary["sessions"] += 1
        summary["rows_inserted"] += int(inserted or 0)
        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total_messages,
                MAX(id) AS last_message_id,
                MAX(created_at) AS last_message_at,
                MAX(NULLIF(group_name, '')) AS display_name
            FROM `{table_name}`
            """
        )
        stats = cursor.fetchone() or {}
        cursor.execute(
            """
            INSERT INTO bot_message_session_registry(
                session_type, session_id, table_name, display_name, total_messages, last_message_id, last_message_at
            ) VALUES(%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                table_name=VALUES(table_name),
                display_name=VALUES(display_name),
                total_messages=VALUES(total_messages),
                last_message_id=VALUES(last_message_id),
                last_message_at=VALUES(last_message_at)
            """,
            (
                "group",
                group_id,
                table_name,
                stats.get("display_name") or f"群聊 {group_id}",
                int(stats.get("total_messages") or 0),
                stats.get("last_message_id"),
                stats.get("last_message_at"),
            ),
        )
        print(f"[群聊迁移] group_id={group_id} table={table_name} inserted={int(inserted or 0)}")
    return summary


def migrate_private_messages(cursor: pymysql.cursors.Cursor) -> dict[str, Any]:
    summary = {"sessions": 0, "rows_inserted": 0}
    if not table_exists(cursor, "bot_private_message"):
        return summary
    cursor.execute("SELECT DISTINCT peer_user_id FROM bot_private_message ORDER BY peer_user_id")
    user_ids = [int(row["peer_user_id"]) for row in cursor.fetchall()]
    for user_id in user_ids:
        table_name = safe_table_name("bot_private_message", user_id)
        cursor.execute(PRIVATE_TABLE_DDL.format(table_name=table_name))
        inserted = cursor.execute(
            f"""
            INSERT IGNORE INTO `{table_name}` (
                id, platform_message_id, peer_nickname, sender_user_id, sender_nickname,
                role, message_type, content_text, raw_message_json, is_reply,
                quoted_platform_message_id, quoted_role, quoted_sender_user_id, quoted_sender_nickname,
                quoted_text, tool_name, tool_args_json, model_name, created_at
            )
            SELECT
                id, platform_message_id, peer_nickname, sender_user_id, sender_nickname,
                role, message_type, content_text, raw_message_json, is_reply,
                quoted_platform_message_id, quoted_role, quoted_sender_user_id, quoted_sender_nickname,
                quoted_text, tool_name, tool_args_json, model_name, created_at
            FROM bot_private_message
            WHERE peer_user_id=%s
            ORDER BY id
            """,
            (user_id,),
        )
        summary["sessions"] += 1
        summary["rows_inserted"] += int(inserted or 0)
        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total_messages,
                MAX(id) AS last_message_id,
                MAX(created_at) AS last_message_at,
                MAX(NULLIF(peer_nickname, '')) AS display_name
            FROM `{table_name}`
            """
        )
        stats = cursor.fetchone() or {}
        cursor.execute(
            """
            INSERT INTO bot_message_session_registry(
                session_type, session_id, table_name, display_name, total_messages, last_message_id, last_message_at
            ) VALUES(%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                table_name=VALUES(table_name),
                display_name=VALUES(display_name),
                total_messages=VALUES(total_messages),
                last_message_id=VALUES(last_message_id),
                last_message_at=VALUES(last_message_at)
            """,
            (
                "private",
                user_id,
                table_name,
                stats.get("display_name") or f"QQ {user_id}",
                int(stats.get("total_messages") or 0),
                stats.get("last_message_id"),
                stats.get("last_message_at"),
            ),
        )
        print(f"[私聊迁移] user_id={user_id} table={table_name} inserted={int(inserted or 0)}")
    return summary


def update_ai_call_log(cursor: pymysql.cursors.Cursor) -> dict[str, int]:
    group_updated = 0
    private_updated = 0
    if table_exists(cursor, "bot_ai_call_log"):
        group_updated = int(
            cursor.execute(
                """
                UPDATE bot_ai_call_log
                SET message_table = CONCAT('bot_group_message_', session_id)
                WHERE session_type='group' AND (message_table='bot_group_message' OR message_table IS NULL)
                """
            )
            or 0
        )
        private_updated = int(
            cursor.execute(
                """
                UPDATE bot_ai_call_log
                SET message_table = CONCAT('bot_private_message_', session_id)
                WHERE session_type='private' AND (message_table='bot_private_message' OR message_table IS NULL)
                """
            )
            or 0
        )
    return {"group": group_updated, "private": private_updated}


def main() -> int:
    args = parse_args()
    cfg = DBConfig(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
    )
    conn = connect_db(cfg)
    try:
        with conn.cursor() as cursor:
            cursor.execute(REGISTRY_DDL)
            group_summary = {"sessions": 0, "rows_inserted": 0}
            private_summary = {"sessions": 0, "rows_inserted": 0}
            if not args.skip_group:
                group_summary = migrate_group_messages(cursor)
            if not args.skip_private:
                private_summary = migrate_private_messages(cursor)
            ai_log_summary = {"group": 0, "private": 0}
            if not args.skip_ai_log_update:
                ai_log_summary = update_ai_call_log(cursor)
    finally:
        conn.close()

    print()
    print("迁移完成")
    print(
        f"群聊会话: {group_summary['sessions']} 个, 新插入消息: {group_summary['rows_inserted']} 条"
    )
    print(
        f"私聊会话: {private_summary['sessions']} 个, 新插入消息: {private_summary['rows_inserted']} 条"
    )
    print(
        f"AI调用日志更新: group={ai_log_summary['group']} private={ai_log_summary['private']}"
    )
    print("旧共享表 bot_group_message / bot_private_message 未删除，可作为备份保留。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
