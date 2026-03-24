"""Streamlit 页面表单状态持久化（关闭页签后可通过同一账号恢复）"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from modules.db.store import connect, db_lock, init_db

PAGE_REF_GEN = "ref_gen"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def save_snapshot(user_id: int, page_key: str, payload: dict[str, Any]) -> None:
    init_db()
    raw = json.dumps(payload, ensure_ascii=False)
    t = _now_iso()
    with db_lock():
        conn = connect()
        try:
            conn.execute(
                """
                INSERT INTO ui_snapshots (user_id, page_key, payload_json, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(user_id, page_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, page_key, raw, t),
            )
            conn.commit()
        finally:
            conn.close()


def load_snapshot(user_id: int, page_key: str) -> Optional[dict[str, Any]]:
    init_db()
    with db_lock():
        conn = connect()
        try:
            row = conn.execute(
                "SELECT payload_json FROM ui_snapshots WHERE user_id = ? AND page_key = ?",
                (user_id, page_key),
            ).fetchone()
            if not row:
                return None
            return json.loads(row["payload_json"])
        except Exception:
            return None
        finally:
            conn.close()
