"""Streamlit 登录态：Cookie + URL 参数 session，关闭页签后重新打开仍可恢复（在有效期内）"""
from __future__ import annotations

import os

import streamlit as st

from modules.db import auth as auth_db
from modules.db.store import init_db

AUTH_DISABLED = os.environ.get("PAPER_TOOLBOX_AUTH", "").strip().lower() in (
    "0",
    "false",
    "off",
    "disabled",
)


def _get_cookie_token() -> str | None:
    try:
        from extra_streamlit_components import CookieManager

        cm = CookieManager(key="paper_toolbox_session_v1")
        # 部分版本 get 可能返回 bytes
        v = cm.get("pt_session")
        if v is None:
            return None
        if isinstance(v, bytes):
            return v.decode("utf-8", errors="ignore")
        return str(v)
    except Exception:
        return None


def _set_cookie_token(token: str, max_age_days: int = 30) -> None:
    try:
        from extra_streamlit_components import CookieManager

        cm = CookieManager(key="paper_toolbox_session_v1")
        max_age = max_age_days * 86400
        cm.set("pt_session", token, max_age=max_age)
    except Exception:
        pass


def _clear_cookie_token() -> None:
    try:
        from extra_streamlit_components import CookieManager

        cm = CookieManager(key="paper_toolbox_session_v1")
        cm.delete("pt_session")
    except Exception:
        pass


def _sync_query_token(token: str | None) -> None:
    try:
        if token:
            st.query_params["session"] = token
        elif "session" in st.query_params:
            del st.query_params["session"]
    except Exception:
        pass


def ensure_authenticated() -> None:
    """
    在 app 入口调用：未登录则展示登录/注册并 st.stop()。
    登录后 session_state: user_id, username, _auth_token
    """
    init_db()

    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "_auth_token" not in st.session_state:
        st.session_state._auth_token = None

    if AUTH_DISABLED:
        st.session_state.user_id = auth_db.ensure_local_dev_user()
        st.session_state.username = "本地用户（已关闭登录）"
        st.session_state._auth_token = None
        return

    token = st.session_state._auth_token
    if not token:
        token = _get_cookie_token()
    if not token:
        token = st.query_params.get("session")

    if st.session_state.user_id is None and token:
        user = auth_db.validate_session_token(token)
        if user:
            st.session_state.user_id = user["id"]
            st.session_state.username = user["username"]
            st.session_state._auth_token = token
            _set_cookie_token(token)
            _sync_query_token(token)
        else:
            st.session_state._auth_token = None
            _clear_cookie_token()
            _sync_query_token(None)

    if st.session_state.user_id is not None:
        with st.sidebar:
            st.caption(f"已登录：**{st.session_state.username}**")
            if st.button("退出登录", use_container_width=True):
                auth_db.delete_session_token(st.session_state._auth_token)
                _clear_cookie_token()
                st.session_state.user_id = None
                st.session_state.username = None
                st.session_state._auth_token = None
                _sync_query_token(None)
                st.rerun()
        return

    st.title("🎓 论文工具箱")
    st.info("请先登录或注册。登录状态会写入浏览器 Cookie，并在地址栏附带 `session` 参数，便于关闭页面后恢复。")

    tab_login, tab_reg = st.tabs(["登录", "注册"])

    with tab_login:
        u1 = st.text_input("用户名", key="login_user")
        p1 = st.text_input("密码", type="password", key="login_pass")
        if st.button("登录", type="primary", key="login_btn"):
            user = auth_db.authenticate(u1, p1)
            if not user:
                st.error("用户名或密码错误")
            else:
                tok = auth_db.create_session(user["id"])
                st.session_state.user_id = user["id"]
                st.session_state.username = user["username"]
                st.session_state._auth_token = tok
                _set_cookie_token(tok)
                _sync_query_token(tok)
                st.success("登录成功")
                st.rerun()

    with tab_reg:
        u2 = st.text_input("新用户名", key="reg_user")
        p2 = st.text_input("新密码（≥6位）", type="password", key="reg_pass")
        p2b = st.text_input("确认密码", type="password", key="reg_pass2")
        if st.button("注册", key="reg_btn"):
            if p2 != p2b:
                st.error("两次密码不一致")
            else:
                ok, msg = auth_db.register_user(u2, p2)
                if ok:
                    st.success(msg + "，请切换到「登录」。")
                else:
                    st.error(msg)

    st.stop()
