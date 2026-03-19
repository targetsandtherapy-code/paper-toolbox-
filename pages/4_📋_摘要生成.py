"""Streamlit 页面 - 摘要生成"""
import sys
import os
import tempfile
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.title("📋 摘要生成")
st.markdown("输入论文内容，生成符合学术规范的中英文摘要及关键词。")

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("输入")

    paper_title = st.text_input("论文标题", placeholder="正念训练对护理人员隐性缺勤影响机制研究")

    upload_tab, text_tab = st.tabs(["上传文档", "粘贴文本"])
    with upload_tab:
        uploaded_file = st.file_uploader("上传论文 (.docx)", type=["docx"], key="abs_upload")
    with text_tab:
        text_input = st.text_area("粘贴论文核心内容", height=300, key="abs_text",
            placeholder="粘贴论文的绪论、方法、结果、结论等核心章节内容...")

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        max_cn = st.number_input("中文摘要字数上限", value=300, min_value=100, max_value=800, step=50)
    with c2:
        max_en = st.number_input("英文摘要词数上限", value=250, min_value=80, max_value=500, step=50)

    run_btn = st.button("📋 生成摘要", type="primary", use_container_width=True)

with col_right:
    if run_btn:
        content = ""
        if uploaded_file:
            from docx import Document
            tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
            tmp.write(uploaded_file.getvalue())
            tmp.close()
            doc = Document(tmp.name)
            content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif text_input and text_input.strip():
            content = text_input.strip()

        if not content:
            st.error("请上传文档或粘贴文本")
            st.stop()

        with st.spinner("AI 正在生成摘要..."):
            try:
                from modules.abstract_gen.generator import AbstractGenerator
                gen = AbstractGenerator()
                result = gen.generate(content=content, title=paper_title, max_words_cn=max_cn, max_words_en=max_en)
            except Exception as e:
                st.error(f"生成失败: {e}")
                st.stop()

        st.success("生成完成!")

        st.markdown("### 中文摘要")
        abstract_cn = result.get("abstract_cn", "")
        st.markdown(abstract_cn)
        st.caption(f"字数: {len(abstract_cn)}")

        keywords_cn = result.get("keywords_cn", [])
        if keywords_cn:
            st.markdown(f"**关键词：** {'；'.join(keywords_cn)}")

        st.divider()

        st.markdown("### Abstract")
        abstract_en = result.get("abstract_en", "")
        st.markdown(abstract_en)
        st.caption(f"词数: {len(abstract_en.split())}")

        keywords_en = result.get("keywords_en", [])
        if keywords_en:
            st.markdown(f"**Keywords:** {'; '.join(keywords_en)}")

        st.divider()

        full_output = f"""中文摘要：
{abstract_cn}

关键词：{'；'.join(keywords_cn)}

Abstract:
{abstract_en}

Keywords: {'; '.join(keywords_en)}"""

        st.download_button("下载摘要 (.txt)", data=full_output,
            file_name="abstract.txt", mime="text/plain", use_container_width=True)
    else:
        st.info("👈 输入论文标题和内容，点击「生成摘要」")
