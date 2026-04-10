"""MySQL access helpers."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Generator

import pymysql

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger("数据库")


class MySQLDatabase:
    """Thin synchronous MySQL wrapper."""

    @contextmanager
    def connection(self) -> Generator[pymysql.connections.Connection, None, None]:
        try:
            conn = pymysql.connect(
                host=settings.mysql_host,
                port=settings.mysql_port,
                user=settings.mysql_user,
                password=settings.mysql_password,
                database=settings.mysql_db,
                charset="utf8mb4",
                autocommit=True,
                cursorclass=pymysql.cursors.DictCursor,
            )
        except Exception as exc:
            logger.error(
                "MySQL连接失败: host=%s port=%s user=%s db=%s error=%s",
                settings.mysql_host,
                settings.mysql_port,
                settings.mysql_user,
                settings.mysql_db,
                exc,
            )
            raise
        try:
            yield conn
        finally:
            conn.close()

    def fetch_one(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall() or []
                return [dict(row) for row in rows]

    def execute(self, sql: str, params: tuple[Any, ...]) -> int:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, params)
                return int(affected)

    def insert(self, sql: str, params: tuple[Any, ...]) -> int:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return int(cursor.lastrowid or 0)

    def execute_many(self, sql: str, params_list: list[tuple[Any, ...]]) -> int:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                affected = cursor.executemany(sql, params_list)
                return int(affected)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def loads_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


database = MySQLDatabase()
