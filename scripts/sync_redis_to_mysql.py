"""Migrate legacy Redis bot data into MySQL tables used by the refactored app.

Supported legacy key mappings:
- runtime:bot:config -> bot_ai_config
- config:{group|private}:{id}:{config_key} -> bot_chat_config
- chat_history:{group|private}:{id} -> bot_chat_history
- chat_summary:{group|private}:{id} -> bot_chat_summary
- chat_history_version:{group|private}:{id} -> bot_chat_config(history_version)
- chat_summary_state:{group|private}:{id} -> bot_chat_config(last_summary_version / summary_cooldown_until)

This script is idempotent because it uses UPSERT semantics.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

import pymysql
import redis


@dataclass(slots=True)
class SyncStats:
    scanned: int = 0
    synced: int = 0
    skipped: int = 0
    failed: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync legacy Redis bot data into MySQL")
    parser.add_argument("--redis-host", default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--redis-db", type=int, default=2)
    parser.add_argument("--redis-password", default="")
    parser.add_argument("--mysql-host", default="127.0.0.1")
    parser.add_argument("--mysql-port", type=int, default=3306)
    parser.add_argument("--mysql-user", default="root")
    parser.add_argument("--mysql-password", default="")
    parser.add_argument("--mysql-db", default="xiaomiao")
    parser.add_argument("--scan-count", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def mysql_connect(args: argparse.Namespace) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=args.mysql_host,
        port=args.mysql_port,
        user=args.mysql_user,
        password=args.mysql_password,
        database=args.mysql_db,
        charset="utf8mb4",
        autocommit=True,
    )


def redis_connect(args: argparse.Namespace) -> redis.Redis:
    return redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        db=args.redis_db,
        password=args.redis_password or None,
        decode_responses=True,
    )


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def upsert_runtime_config(cursor: pymysql.cursors.Cursor, key: str, value: Any) -> None:
    cursor.execute(
        """
        INSERT INTO bot_ai_config(config_key, config_value)
        VALUES(%s, %s)
        ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)
        """,
        (key, json_dump(value)),
    )


def upsert_session_config(
    cursor: pymysql.cursors.Cursor,
    session_type: str,
    session_id: int,
    config_key: str,
    config_value: str,
) -> None:
    cursor.execute(
        """
        INSERT INTO bot_chat_config(session_type, session_id, config_key, config_value)
        VALUES(%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)
        """,
        (session_type, session_id, config_key, config_value),
    )


def upsert_history(
    cursor: pymysql.cursors.Cursor,
    session_type: str,
    session_id: int,
    history_json: str,
) -> None:
    cursor.execute(
        """
        INSERT INTO bot_chat_history(session_type, session_id, history_json)
        VALUES(%s, %s, %s)
        ON DUPLICATE KEY UPDATE history_json=VALUES(history_json)
        """,
        (session_type, session_id, history_json),
    )


def upsert_summary(
    cursor: pymysql.cursors.Cursor,
    session_type: str,
    session_id: int,
    summary_text: str,
) -> None:
    cursor.execute(
        """
        INSERT INTO bot_chat_summary(session_type, session_id, summary_text)
        VALUES(%s, %s, %s)
        ON DUPLICATE KEY UPDATE summary_text=VALUES(summary_text)
        """,
        (session_type, session_id, summary_text),
    )


def normalize_session(parts: list[str]) -> tuple[str, int]:
    return parts[1], int(parts[2])


def sync_key(
    cursor: pymysql.cursors.Cursor,
    redis_client: redis.Redis,
    key: str,
) -> bool:
    raw = redis_client.get(key)
    if raw is None:
        return False

    if key == "runtime:bot:config":
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return False
        for cfg_key, cfg_value in payload.items():
            upsert_runtime_config(cursor, str(cfg_key), cfg_value)
        return True

    if key.startswith("config:"):
        parts = key.split(":", 3)
        if len(parts) != 4:
            return False
        session_type = parts[1]
        session_id = int(parts[2])
        config_key = parts[3]
        upsert_session_config(cursor, session_type, session_id, config_key, raw)
        return True

    if key.startswith("chat_history:"):
        parts = key.split(":", 2)
        if len(parts) != 3:
            return False
        session_type, session_id = normalize_session(parts)
        upsert_history(cursor, session_type, session_id, raw)
        return True

    if key.startswith("chat_summary:"):
        parts = key.split(":", 2)
        if len(parts) != 3:
            return False
        session_type, session_id = normalize_session(parts)
        upsert_summary(cursor, session_type, session_id, raw)
        return True

    if key.startswith("chat_history_version:"):
        parts = key.split(":", 2)
        if len(parts) != 3:
            return False
        session_type, session_id = normalize_session(parts)
        upsert_session_config(cursor, session_type, session_id, "history_version", raw)
        return True

    if key.startswith("chat_summary_state:"):
        parts = key.split(":", 2)
        if len(parts) != 3:
            return False
        session_type, session_id = normalize_session(parts)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return False
        last_summary_version = int(payload.get("last_summary_version", 0) or 0)
        cooldown_until = int(payload.get("cooldown_until", 0) or 0)
        upsert_session_config(
            cursor,
            session_type,
            session_id,
            "last_summary_version",
            json_dump(last_summary_version),
        )
        upsert_session_config(
            cursor,
            session_type,
            session_id,
            "summary_cooldown_until",
            json_dump(cooldown_until),
        )
        return True

    return False


def main() -> None:
    args = parse_args()
    redis_client = redis_connect(args)
    conn = mysql_connect(args)
    stats = SyncStats()

    try:
        with conn.cursor() as cursor:
            for key in redis_client.scan_iter(match="*", count=args.scan_count):
                stats.scanned += 1
                redis_key = str(key)
                if redis_key.startswith("lock:"):
                    stats.skipped += 1
                    continue
                try:
                    changed = sync_key(cursor, redis_client, redis_key)
                    if changed:
                        stats.synced += 1
                        print(f"[SYNC] {redis_key}")
                    else:
                        stats.skipped += 1
                        print(f"[SKIP] {redis_key}")
                except Exception as exc:
                    stats.failed += 1
                    print(f"[FAIL] {redis_key}: {exc}")
                    if not args.dry_run:
                        continue
    finally:
        conn.close()

    print(
        f"done: scanned={stats.scanned} synced={stats.synced} "
        f"skipped={stats.skipped} failed={stats.failed}"
    )


if __name__ == "__main__":
    main()
