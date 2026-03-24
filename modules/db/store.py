"""SQLite 连接与表结构初始化（本地 data/app.sqlite3，不随代码推送服务器）"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_lock = threading.RLock()
_DB_PATH: Path | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS paper_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_papers_user ON paper_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_papers_category ON paper_projects(user_id, category);

CREATE TABLE IF NOT EXISTS ui_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    page_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, page_key),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS claim_reference_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT UNIQUE NOT NULL,
    paper_title_norm TEXT NOT NULL,
    key_claim_preview TEXT NOT NULL,
    status TEXT NOT NULL,
    claim_type TEXT,
    paper_json TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claim_cache_sig ON claim_reference_cache(signature);
"""


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        root = Path(__file__).resolve().parent.parent.parent
        data = root / "data"
        data.mkdir(parents=True, exist_ok=True)
        _DB_PATH = data / "app.sqlite3"
    return _DB_PATH


def connect() -> sqlite3.Connection:
    path = get_db_path()
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=60.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock:
        conn = connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()


def db_lock():
    return _lock
