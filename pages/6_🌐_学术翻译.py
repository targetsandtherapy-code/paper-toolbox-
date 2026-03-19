"""Streamlit 页面 - 学术翻译"""
import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.title("🌐 学术翻译")
st.markdown("学术风格的中英互译，保持术语准确性和引用格式。")

col_left, col_right = st.columns([1, 3])

with col_left:
    direction = st.radio("翻译方向", ["中文 → 英文", "英文 → 中文"], horizontal=True)
    field = st.text_input("学科领域（可选）", placeholder="例：护理学、心理学、计算机科学")
    glossary = st.text_area("自定义术语表（可选）", height=100,
        placeholder="每行一个，格式：中文术语 = English Term\n例：隐性缺勤 = presenteeism")

with col_right:
    text_input = st.text_area("输入原文", height=250,
        placeholder="粘贴需要翻译的学术段落...")

    if st.button("🌐 翻译", type="primary", use_container_width=True):
        if not text_input.strip():
            st.error("请输入待翻译的文本")
            st.stop()

        dir_code = "cn_to_en" if "→ 英" in direction else "en_to_cn"

        with st.spinner("AI 正在翻译..."):
            try:
                from modules.translator.engine import AcademicTranslator
                translator = AcademicTranslator()
                result = translator.translate(
                    text=text_input.strip(), direction=dir_code,
                    field=field.strip(), glossary=glossary.strip(),
                )
            except Exception as e:
                st.error(f"翻译失败: {e}")
                st.stop()

        st.success("翻译完成!")

        st.markdown("### 译文")
        translation = result.get("translation", "")
        st.markdown(translation)

        terms = result.get("terminology", [])
        if terms:
            st.markdown("### 术语对照")
            for t in terms:
                st.markdown(f"- **{t.get('source', '')}** → {t.get('target', '')}")

        st.divider()
        st.download_button("下载译文 (.txt)", data=translation,
            file_name="translation.txt", mime="text/plain", use_container_width=True)
