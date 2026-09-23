"""SQLite 存储层：读写温湿度读数。

单表 readings(id, ts, temperature, humidity)，ts 为 ISO8601 字符串，
字符串比较与时间顺序一致，因此可直接用 WHERE ts >= ?。
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

# 支持的时间范围
RANGE_DELTAS = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def init_db(db_path: str) -> None:
    """创建数据库文件、表与索引（幂等）。"""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                temperature REAL NOT NULL,
                humidity REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(ts)")
        conn.commit()


@contextmanager
def _conn(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_reading(db_path: str, ts: str, temperature: float, humidity: float) -> int:
    with _conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO readings(ts, temperature, humidity) VALUES (?, ?, ?)",
            (ts, temperature, humidity),
        )
        return cur.lastrowid


def get_latest(db_path: str):
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT id, ts, temperature, humidity FROM readings "
            "ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_readings(db_path: str, since_iso: str, limit: int = 2000):
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, ts, temperature, humidity FROM readings "
            "WHERE ts >= ? ORDER BY ts ASC LIMIT ?",
            (since_iso, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats(db_path: str, since_iso: str):
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count, "
            "MIN(temperature) AS temp_min, MAX(temperature) AS temp_max, AVG(temperature) AS temp_avg, "
            "MIN(humidity) AS hum_min, MAX(humidity) AS hum_max, AVG(humidity) AS hum_avg "
            "FROM readings WHERE ts >= ?",
            (since_iso,),
        ).fetchone()
        return dict(row) if row else None


def parse_range(range_str: str) -> str:
    """把 '1h' / '6h' / '24h' / '7d' 转成 UTC ISO8601 截止时间。"""
    delta = RANGE_DELTAS.get(range_str, RANGE_DELTAS["24h"])
    return (datetime.now(timezone.utc) - delta).isoformat()
