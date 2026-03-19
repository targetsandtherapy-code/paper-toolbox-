"""Streamlit 页面 - 开题报告生成"""
import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.title("📄 开题报告生成")
st.markdown("输入研究题目，生成包含选题背景、研究现状、研究方法、进度安排等完整开题报告。")

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("输入")
    paper_title = st.text_input("论文题目", placeholder="正念训练对护理人员隐性缺勤影响机制研究")
    paper_type = st.selectbox("论文类型", ["硕士论文", "博士论文", "本科毕业论文"])
    field = st.text_input("学科领域（可选）", placeholder="护理学 / 管理学 / 心理学")
    method = st.text_input("研究方法（可选）", placeholder="问卷调查、结构方程模型、中介效应分析")
    extra = st.text_area("额外要求（可选）", height=80, placeholder="例：需要包含工作要求-资源模型的理论框架")

    run_btn = st.button("📄 生成开题报告", type="primary", use_container_width=True)

with col_right:
    if run_btn:
        if not paper_title.strip():
            st.error("请输入论文题目")
            st.stop()

        with st.spinner("AI 正在生成开题报告（可能需要 20-30 秒）..."):
            try:
                from modules.proposal.generator import ProposalGenerator
                gen = ProposalGenerator()
                result = gen.generate(
                    title=paper_title.strip(), field=field.strip(),
                    method=method.strip(), paper_type=paper_type, extra=extra.strip(),
                )
            except Exception as e:
                st.error(f"生成失败: {e}")
                st.stop()

        st.success("生成完成!")

        md_output = f"# {result.get('title', paper_title)}\n\n"

        for section in result.get("sections", []):
            st.markdown(f"### {section['heading']}")
            md_output += f"## {section['heading']}\n\n"

            for sub in section.get("subsections", []):
                st.markdown(f"**{sub['subheading']}**")
                st.markdown(sub.get("content", ""))
                md_output += f"### {sub['subheading']}\n\n{sub.get('content', '')}\n\n"
            st.markdown("---")

        innovations = result.get("innovations", [])
        if innovations:
            st.markdown("### 研究创新点")
            md_output += "## 研究创新点\n\n"
            for inn in innovations:
                st.markdown(f"- {inn}")
                md_output += f"- {inn}\n"
            md_output += "\n"

        timeline = result.get("timeline", [])
        if timeline:
            st.markdown("### 研究进度安排")
            md_output += "## 研究进度安排\n\n"
            for t in timeline:
                st.markdown(f"- **{t['period']}**：{t['task']}")
                md_output += f"- **{t['period']}**：{t['task']}\n"
            md_output += "\n"

        ref_dirs = result.get("reference_directions", [])
        if ref_dirs:
            st.markdown("### 推荐文献检索方向")
            md_output += "## 推荐文献检索方向\n\n"
            for r in ref_dirs:
                st.markdown(f"- {r}")
                md_output += f"- {r}\n"

        st.divider()
        st.download_button("下载开题报告 (.md)", data=md_output,
            file_name="proposal.md", mime="text/markdown", use_container_width=True)
    else:
        st.info("👈 输入论文题目和相关信息，点击「生成开题报告」")
