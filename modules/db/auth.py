"""用户注册、登录与会话令牌"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt

from modules.db.store import connect, db_lock, init_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("ascii"))
    except Exception:
        return False


def register_user(username: str, password: str) -> tuple[bool, str]:
    username = (username or "").strip()
    if len(username) < 2 or len(username) > 64:
        return False, "用户名长度应为 2–64 字符"
    if len(password) < 6:
        return False, "密码至少 6 位"
    init_db()
    ph = hash_password(password)
    with db_lock():
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
                (username, ph, _now_iso()),
            )
            conn.commit()
            return True, "注册成功"
        except Exception as e:
            if "UNIQUE" in str(e).upper():
                return False, "用户名已存在"
            return False, f"注册失败: {e}"
        finally:
            conn.close()


def authenticate(username: str, password: str) -> Optional[dict[str, Any]]:
    username = (username or "").strip()
    init_db()
    with db_lock():
        conn = connect()
        try:
            row = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if not row:
                return None
            if not verify_password(password, row["password_hash"]):
                return None
            return {"id": int(row["id"]), "username": row["username"]}
        finally:
            conn.close()


def create_session(user_id: int, days: int = 30) -> str:
    token = secrets.token_urlsafe(48)
    exp = datetime.now(timezone.utc) + timedelta(days=days)
    exp_s = exp.strftime("%Y-%m-%dT%H:%M:%S")
    init_db()
    with db_lock():
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO sessions (user_id, token, expires_at, created_at) VALUES (?,?,?,?)",
                (user_id, token, exp_s, _now_iso()),
            )
            conn.commit()
            return token
        finally:
            conn.close()


def validate_session_token(token: Optional[str]) -> Optional[dict[str, Any]]:
    if not token:
        return None
    init_db()
    now = _now_iso()
    with db_lock():
        conn = connect()
        try:
            row = conn.execute(
                """
                SELECT u.id AS user_id, u.username, s.expires_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
            if not row:
                return None
            if row["expires_at"] < now:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None
            return {"id": int(row["user_id"]), "username": row["username"]}
        finally:
            conn.close()


def delete_session_token(token: Optional[str]) -> None:
    if not token:
        return
    with db_lock():
        conn = connect()
        try:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()


def ensure_local_dev_user() -> int:
    """关闭认证时使用固定本地用户，便于论文与快照仍按 user_id 隔离"""
    init_db()
    uname = "_local_dev"
    with db_lock():
        conn = connect()
        try:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (uname,)
            ).fetchone()
            if row:
                return int(row["id"])
            ph = hash_password(secrets.token_urlsafe(16))
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
                (uname, ph, _now_iso()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (uname,)
            ).fetchone()
            return int(row["id"])
        finally:
            conn.close()
