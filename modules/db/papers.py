"""用户论文项目（分类、标题）"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from modules.db.store import connect, db_lock, init_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def list_projects(user_id: int) -> list[dict[str, Any]]:
    init_db()
    with db_lock():
        conn = connect()
        try:
            rows = conn.execute(
                """
                SELECT id, title, category, notes, created_at, updated_at
                FROM paper_projects
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def create_project(user_id: int, title: str, category: str = "", notes: str = "") -> int:
    init_db()
    t = _now_iso()
    with db_lock():
        conn = connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO paper_projects (user_id, title, category, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?)
                """,
                (user_id, title.strip() or "未命名论文", (category or "").strip(), (notes or "").strip(), t, t),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def update_project(
    user_id: int,
    project_id: int,
    *,
    title: Optional[str] = None,
    category: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    init_db()
    fields = []
    vals: list[Any] = []
    if title is not None:
        fields.append("title = ?")
        vals.append(title.strip())
    if category is not None:
        fields.append("category = ?")
        vals.append(category.strip())
    if notes is not None:
        fields.append("notes = ?")
        vals.append(notes.strip())
    if not fields:
        return
    fields.append("updated_at = ?")
    vals.append(_now_iso())
    vals.extend([project_id, user_id])
    with db_lock():
        conn = connect()
        try:
            conn.execute(
                f"UPDATE paper_projects SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
                vals,
            )
            conn.commit()
        finally:
            conn.close()


def get_project(user_id: int, project_id: int) -> Optional[dict[str, Any]]:
    init_db()
    with db_lock():
        conn = connect()
        try:
            row = conn.execute(
                """
                SELECT id, title, category, notes, created_at, updated_at
                FROM paper_projects WHERE id = ? AND user_id = ?
                """,
                (project_id, user_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def list_categories(user_id: int) -> list[str]:
    init_db()
    with db_lock():
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT category FROM paper_projects WHERE user_id = ? AND category != '' ORDER BY category",
                (user_id,),
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()
