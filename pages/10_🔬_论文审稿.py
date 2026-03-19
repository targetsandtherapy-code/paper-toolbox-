"""Streamlit 页面 - 论文审稿助手"""
import sys
import os
import tempfile
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.title("🔬 论文审稿助手")
st.markdown("AI 逐段审阅论文，检查逻辑、论述、学术规范、引用和语言表达。")

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("输入")
    paper_title = st.text_input("论文标题", placeholder="正念训练对护理人员隐性缺勤影响机制研究")

    upload_tab, text_tab = st.tabs(["上传文档", "粘贴文本"])
    with upload_tab:
        uploaded_file = st.file_uploader("上传论文 (.docx)", type=["docx"], key="review_upload")
    with text_tab:
        text_input = st.text_area("粘贴论文内容", height=250, key="review_text")

    review_mode = st.selectbox("审阅模式", ["逐段审阅", "结构审查", "全面审阅（逐段+结构）"])
    max_paragraphs = st.slider("最大审阅段落数", 5, 30, 15, help="段落越多，耗时越长")

    run_btn = st.button("🔬 开始审稿", type="primary", use_container_width=True)

with col_right:
    if run_btn:
        full_text = ""
        if uploaded_file:
            from docx import Document
            tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
            tmp.write(uploaded_file.getvalue())
            tmp.close()
            doc = Document(tmp.name)
            full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif text_input and text_input.strip():
            full_text = text_input.strip()

        if not full_text:
            st.error("请上传文档或粘贴文本")
            st.stop()

        paragraphs = [p.strip() for p in full_text.split("\n") if p.strip() and len(p.strip()) >= 20]

        from modules.reviewer.engine import PaperReviewer
        reviewer = PaperReviewer()

        if review_mode in ["结构审查", "全面审阅（逐段+结构）"]:
            with st.spinner("AI 正在审查论文结构..."):
                try:
                    struct_result = reviewer.review_structure(paragraphs, paper_title.strip())
                except Exception as e:
                    st.error(f"结构审查失败: {e}")
                    struct_result = None

            if struct_result:
                st.markdown("### 📊 结构审查")
                score = struct_result.get("structure_score", "N/A")
                st.metric("结构评分", f"{score}/10")

                detected = struct_result.get("detected_sections", [])
                if detected:
                    st.markdown(f"**已识别章节：** {' → '.join(detected)}")

                missing = struct_result.get("missing_sections", [])
                if missing:
                    st.warning(f"可能缺少：{', '.join(missing)}")

                for issue in struct_result.get("structure_issues", []):
                    with st.container(border=True):
                        st.markdown(f"⚠️ {issue.get('issue', '')}")
                        st.markdown(f"💡 {issue.get('suggestion', '')}")

                st.markdown(f"**总体评价：** {struct_result.get('overall_assessment', '')}")
                st.divider()

        if review_mode in ["逐段审阅", "全面审阅（逐段+结构）"]:
            review_paras = paragraphs[:max_paragraphs]
            total = len(review_paras)
            progress = st.progress(0)
            status = st.empty()

            all_issues = 0
            for i, para in enumerate(review_paras):
                status.info(f"审阅第 {i+1}/{total} 段...")
                progress.progress((i + 1) / total)

                context = paragraphs[max(0, i-1)] if i > 0 else ""
                try:
                    result = reviewer.review_paragraph(para, context=context, paper_title=paper_title.strip())
                except Exception:
                    continue

                issues = result.get("issues", [])
                score = result.get("overall_score", "N/A")
                all_issues += len(issues)

                if issues:
                    with st.container(border=True):
                        st.markdown(f"**段落 {i+1}** — 评分: {score}/10")
                        st.text(para[:150] + ("..." if len(para) > 150 else ""))

                        for issue in issues:
                            severity = issue.get("severity", "")
                            icon = "🔴" if severity == "严重" else "🟡" if severity == "中等" else "🟢"
                            st.markdown(f"{icon} **[{issue.get('type', '')}]** {issue.get('description', '')}")
                            st.markdown(f"  💡 {issue.get('suggestion', '')}")

            progress.progress(100)
            status.success(f"审阅完成! 共审阅 {total} 段，发现 {all_issues} 个问题")
    else:
        st.info("👈 上传论文或粘贴文本，点击「开始审稿」")
