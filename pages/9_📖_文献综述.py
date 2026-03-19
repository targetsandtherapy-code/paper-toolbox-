"""Streamlit 页面 - 文献综述生成"""
import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.title("📖 文献综述生成")
st.markdown("输入研究主题和关键词，自动检索文献并生成结构化的文献综述。")

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("输入")
    topic = st.text_input("研究主题", placeholder="正念训练对职业倦怠的干预效果")

    keywords = st.text_area("搜索关键词（每行一个）", height=120,
        placeholder="mindfulness intervention burnout\n正念训练 职业倦怠\nmindfulness workplace well-being")

    c1, c2 = st.columns(2)
    with c1:
        year_start = st.number_input("起始年份", value=2019, min_value=2000, max_value=2026)
    with c2:
        year_end = st.number_input("结束年份", value=2026, min_value=2000, max_value=2030)

    per_query = st.slider("每条关键词检索数", 5, 20, 10)

    run_btn = st.button("📖 生成文献综述", type="primary", use_container_width=True)

with col_right:
    if run_btn:
        if not topic.strip():
            st.error("请输入研究主题")
            st.stop()

        queries = [q.strip() for q in keywords.strip().split("\n") if q.strip()]
        if not queries:
            queries = [topic.strip()]

        log_area = st.empty()
        log_lines = []

        def log_cb(msg):
            log_lines.append(msg)
            log_area.code("\n".join(log_lines[-15:]), language=None)

        with st.spinner("检索文献中..."):
            from modules.literature_review.generator import LiteratureReviewGenerator
            gen = LiteratureReviewGenerator()

            papers = gen.search_papers(queries, year_start, year_end, per_query, callback=log_cb)

        if not papers:
            st.error("未检索到相关文献，请调整关键词")
            st.stop()

        with st.spinner("AI 正在分析和撰写综述（可能需要 30-60 秒）..."):
            try:
                result = gen.cluster_and_summarize(papers, topic.strip(), callback=log_cb)
            except Exception as e:
                st.error(f"生成失败: {e}")
                st.stop()

        st.success(f"文献综述生成完成! 基于 {len(papers)} 篇文献")

        md_output = f"# {result.get('title', topic)}\n\n"

        intro = result.get("introduction", "")
        if intro:
            st.markdown("### 引言")
            st.markdown(intro)
            md_output += f"## 引言\n\n{intro}\n\n"

        for cluster in result.get("clusters", []):
            theme = cluster.get("theme", "")
            summary = cluster.get("summary", "")
            count = cluster.get("paper_count", 0)

            st.markdown(f"### {theme}")
            st.caption(f"涉及 {count} 篇文献")
            st.markdown(summary)
            md_output += f"## {theme}\n\n{summary}\n\n"

        trends = result.get("trends", "")
        if trends:
            st.markdown("### 研究趋势")
            st.markdown(trends)
            md_output += f"## 研究趋势\n\n{trends}\n\n"

        gaps = result.get("gaps", "")
        if gaps:
            st.markdown("### 研究空白与不足")
            st.markdown(gaps)
            md_output += f"## 研究空白与不足\n\n{gaps}\n\n"

        future = result.get("future_directions", [])
        if future:
            st.markdown("### 未来研究方向")
            md_output += "## 未来研究方向\n\n"
            for f_item in future:
                st.markdown(f"- {f_item}")
                md_output += f"- {f_item}\n"
            md_output += "\n"

        conclusion = result.get("conclusion", "")
        if conclusion:
            st.markdown("### 结论")
            st.markdown(conclusion)
            md_output += f"## 结论\n\n{conclusion}\n\n"

        st.divider()
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button("下载综述 (.md)", data=md_output,
                file_name="literature_review.md", mime="text/markdown", use_container_width=True)
        with dl2:
            bib_text = "\n".join(f"[{i+1}] {', '.join(p.authors[:3])}. {p.title}. {p.journal or 'N/A'}, {p.year}. DOI: {p.doi or 'N/A'}"
                for i, p in enumerate(papers[:50]))
            st.download_button("下载文献列表 (.txt)", data=bib_text,
                file_name="references.txt", mime="text/plain", use_container_width=True)
    else:
        st.info("👈 输入研究主题和关键词，点击「生成文献综述」")
