"""Streamlit 页面 - 降重改写助手"""
import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.title("✏️ 降重改写助手")
st.markdown("在保持语义不变的前提下改写段落，降低与原文的文字重复率。")

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("设置")
    style = st.selectbox("改写风格", ["学术改写", "精简压缩", "扩展丰富"],
        help="学术改写：同义替换+句式调整；精简压缩：去冗余；扩展丰富：补充论述")
    field = st.text_input("学科领域（可选）", placeholder="护理学 / 管理学")

    st.divider()
    st.markdown("**使用建议：**")
    st.markdown("1. 先用「查重预检」找到高风险段落")
    st.markdown("2. 将高风险段落粘贴到这里改写")
    st.markdown("3. 改写后替换回论文，再次自查")

with col_right:
    text_input = st.text_area("输入需要改写的段落", height=200,
        placeholder="粘贴需要降重的段落，可以一次粘贴多个段落（用空行分隔）...")

    if st.button("✏️ 开始改写", type="primary", use_container_width=True):
        if not text_input.strip():
            st.error("请输入需要改写的文本")
            st.stop()

        paragraphs = [p.strip() for p in text_input.strip().split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text_input.strip()]

        total = len(paragraphs)
        progress = st.progress(0)
        status = st.empty()

        all_results = []
        for i, para in enumerate(paragraphs):
            status.info(f"正在改写第 {i+1}/{total} 段...")
            progress.progress((i + 1) / total)

            try:
                from modules.rewriter.engine import Rewriter
                rw = Rewriter()
                result = rw.rewrite(para, style=style, field=field.strip())
                all_results.append((para, result))
            except Exception as e:
                all_results.append((para, {"rewritten": para, "changes": [f"失败: {e}"], "estimated_similarity": "N/A"}))

        progress.progress(100)
        status.success(f"改写完成! 共 {total} 段")

        full_rewritten = ""
        for i, (original, result) in enumerate(all_results):
            rewritten = result.get("rewritten", "")
            sim = result.get("estimated_similarity", "N/A")
            changes = result.get("changes", [])

            with st.container(border=True):
                st.markdown(f"**段落 {i+1}** — 预估相似度: {sim}")

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**原文：**")
                    st.text(original[:300])
                with c2:
                    st.markdown("**改写后：**")
                    st.text(rewritten[:300])

                if changes:
                    with st.expander("修改说明"):
                        for c in changes:
                            st.markdown(f"- {c}")

            full_rewritten += rewritten + "\n\n"

        st.divider()
        st.download_button("下载改写结果 (.txt)", data=full_rewritten.strip(),
            file_name="rewritten.txt", mime="text/plain", use_container_width=True)
