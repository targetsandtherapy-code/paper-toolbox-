"""Streamlit 页面 - 论文参考文献智能生成"""
import sys
import os
import tempfile
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from modules.reference.main import process_paper

st.title("📚 论文参考文献智能生成")
st.markdown(r"上传含角标（如 \[1\], \[2,3\], \[4-6\]）的 Word 文档，自动匹配真实学术论文并生成 GB/T 7714 格式参考文献列表。")

if "stop_flag" not in st.session_state:
    st.session_state.stop_flag = False

col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("输入设置")

    upload_tab, text_tab = st.tabs(["上传文档", "粘贴文本"])

    with upload_tab:
        uploaded_files = st.file_uploader("上传 Word 文档 (.docx)", type=["docx"],
            accept_multiple_files=True, help="支持同时上传多个文档")

    with text_tab:
        text_input = st.text_area("粘贴包含角标的论文段落",
            placeholder="近年来，基于Transformer架构的大语言模型取得了显著突破[1]。...", height=200)

    st.divider()

    paper_title_input = st.text_input("论文题目",
        placeholder="例：正念训练对护理人员隐性缺勤影响机制研究",
        help="输入论文标题可大幅提升文献匹配的精准度")

    c1, c2 = st.columns(2)
    with c1:
        year_start = st.number_input("起始年份", value=2021, min_value=2000, max_value=2026)
    with c2:
        year_end = st.number_input("结束年份", value=2026, min_value=2000, max_value=2030)

    cn_ratio_pct = st.slider("中文文献占比 (%)", min_value=0, max_value=100, value=25, step=5,
        help="25% = 中英文 1:3 比例")
    results_per = st.slider("每源检索数", min_value=1, max_value=10, value=5,
        help="增加可提高匹配质量，但会变慢")

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        run_btn = st.button("🚀 生成", type="primary", use_container_width=True)
    with btn_col2:
        stop_btn = st.button("⏹ 停止", use_container_width=True)

    if stop_btn:
        st.session_state.stop_flag = True
        st.warning("已请求停止")

with col_right:
    if run_btn:
        st.session_state.stop_flag = False

        docx_list = []
        if uploaded_files:
            for uf in uploaded_files:
                tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
                tmp.write(uf.getvalue())
                tmp.close()
                docx_list.append((uf.name, tmp.name))
        elif text_input and text_input.strip():
            from docx import Document
            doc = Document()
            for para in text_input.strip().split("\n"):
                if para.strip():
                    doc.add_paragraph(para.strip())
            tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
            doc.save(tmp.name)
            tmp.close()
            docx_list.append(("粘贴文本", tmp.name))
        else:
            st.error("请上传 Word 文档或粘贴论文文本")
            st.stop()

        cn_ratio = cn_ratio_pct / 100.0

        for file_idx, (file_label, docx_path) in enumerate(docx_list):
            if st.session_state.stop_flag:
                st.warning("已停止处理。")
                break

            if len(docx_list) > 1:
                st.subheader(f"文件 {file_idx+1}/{len(docx_list)}: {file_label}")

            progress_bar = st.progress(0)
            status_text = st.empty()
            log_area = st.empty()
            log_lines = []

            status_text.info(f"正在处理: {file_label}...")

            def make_log_callback(lines_ref, log_widget):
                def cb(msg):
                    if st.session_state.stop_flag:
                        raise InterruptedError("用户停止")
                    lines_ref.append(msg)
                    log_widget.code("\n".join(lines_ref[-20:]), language=None)
                return cb

            def make_progress_callback(bar, status_widget):
                def cb(current, total, text):
                    pct = int(current / max(total, 1) * 100)
                    bar.progress(min(pct, 100))
                    status_widget.info(text)
                return cb

            log_cb = make_log_callback(log_lines, log_area)
            prog_cb = make_progress_callback(progress_bar, status_text)

            error = None
            refs, md_output, plain_output = {}, "", ""

            try:
                refs, md_output, plain_output = process_paper(
                    docx_path=docx_path, year_start=int(year_start), year_end=int(year_end),
                    results_per_source=int(results_per), cn_ratio=cn_ratio,
                    callback=log_cb, progress_callback=prog_cb,
                    paper_title=paper_title_input.strip(),
                )
            except InterruptedError:
                error = "stopped"
            except Exception as e:
                error = str(e)

            if error == "stopped":
                status_text.warning("处理已停止")
                break
            elif error:
                status_text.error(f"处理出错: {error}")
                continue

            progress_bar.progress(100)

            if not refs:
                status_text.warning("未找到任何角标或匹配结果")
            else:
                cn_count = sum(1 for p in refs.values()
                    if sum(1 for c in (p.title or "") if '\u4e00' <= c <= '\u9fff') / max(len(p.title or "x"), 1) > 0.3)
                en_count = len(refs) - cn_count
                status_text.success(f"{len(refs)} 条参考文献已生成 (中文 {cn_count} + 英文 {en_count})")

                st.markdown("### 参考文献列表")
                st.markdown(md_output)

                st.markdown("### 详细匹配")
                for idx in sorted(refs.keys()):
                    p = refs[idx]
                    with st.container(border=True):
                        doi_link = f"[{p.doi}](https://doi.org/{p.doi})" if p.doi else "无"
                        st.markdown(f"**[{idx}]** {p.title}")
                        st.markdown(f"{p.journal or 'N/A'} | {p.year or 'N/A'} | DOI: {doi_link} | 被引: {p.citation_count or 'N/A'} | 来源: {p.source}")

                st.divider()
                dl1, dl2 = st.columns(2)
                with dl1:
                    st.download_button(f"下载 Markdown", data=md_output,
                        file_name=f"{Path(file_label).stem}_references.md", mime="text/markdown",
                        use_container_width=True, key=f"md_{file_idx}")
                with dl2:
                    st.download_button(f"下载 TXT", data=plain_output,
                        file_name=f"{Path(file_label).stem}_references.txt", mime="text/plain",
                        use_container_width=True, key=f"txt_{file_idx}")

            if file_idx < len(docx_list) - 1:
                st.divider()
    else:
        st.info("👈 请在左侧上传文档或粘贴文本，然后点击「生成」")
