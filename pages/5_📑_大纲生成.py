"""Streamlit 页面 - 大纲生成"""
import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.title("📑 大纲生成")
st.markdown("输入研究题目，生成结构化论文大纲。")

col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("输入")

    paper_title = st.text_input("论文题目", placeholder="正念训练对护理人员隐性缺勤影响机制研究")
    keywords = st.text_input("关键词（可选）", placeholder="正念训练；护理人员；隐性缺勤；工作投入")
    paper_type = st.selectbox("论文类型", ["硕士论文", "博士论文", "本科毕业论文", "期刊论文", "会议论文"])
    extra_req = st.text_area("额外要求（可选）", height=100,
        placeholder="例：需要包含实证研究部分，使用问卷调查法和结构方程模型分析...")

    run_btn = st.button("📑 生成大纲", type="primary", use_container_width=True)

with col_right:
    if run_btn:
        if not paper_title.strip():
            st.error("请输入论文题目")
            st.stop()

        with st.spinner("AI 正在生成大纲..."):
            try:
                from modules.outline.generator import OutlineGenerator
                gen = OutlineGenerator()
                result = gen.generate(
                    title=paper_title.strip(), keywords=keywords.strip(),
                    paper_type=paper_type, extra_requirements=extra_req.strip(),
                )
            except Exception as e:
                st.error(f"生成失败: {e}")
                st.stop()

        st.success("生成完成!")

        st.markdown(f"### {result.get('title', paper_title)}")

        if result.get("estimated_word_count"):
            st.caption(f"预计字数: {result['estimated_word_count']}")

        outline_md = ""
        for ch in result.get("chapters", []):
            ch_title = f"{ch['number']} {ch['title']}"
            st.markdown(f"#### {ch_title}")
            outline_md += f"## {ch_title}\n\n"

            for sec in ch.get("sections", []):
                sec_title = f"{sec['number']} {sec['title']}"
                st.markdown(f"**{sec_title}**")
                st.markdown(f"<span style='color:gray'>{sec.get('description', '')}</span>", unsafe_allow_html=True)
                outline_md += f"### {sec_title}\n{sec.get('description', '')}\n\n"

            st.markdown("---")
            outline_md += "---\n\n"

        suggestions = result.get("suggestions", [])
        if suggestions:
            st.markdown("#### 写作建议")
            for s in suggestions:
                st.markdown(f"- {s}")
                outline_md += f"- {s}\n"

        st.divider()
        st.download_button("下载大纲 (.md)", data=outline_md,
            file_name="outline.md", mime="text/markdown", use_container_width=True)
    else:
        st.info("👈 输入论文题目和关键词，点击「生成大纲」")
