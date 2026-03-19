"""Streamlit 页面 - 论文格式调整工具"""
import sys
import os
import tempfile
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from modules.formatter.main import format_paper
from modules.formatter.template_parser import parse_template, TemplateConfig, PageSpec, ParagraphSpec, FontSpec

st.title("📝 论文格式调整工具")
st.markdown("上传论文和学校模板，一键统一格式。")

if "template_config" not in st.session_state:
    st.session_state.template_config = None

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("文件上传")
    paper_file = st.file_uploader("上传论文 (.docx)", type=["docx"], key="paper")
    template_file = st.file_uploader("上传学校模板 (.docx)", type=["docx"], key="template",
                                      help="上传后自动读取默认参数")

    if template_file:
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.write(template_file.getvalue())
        tmp.close()
        try:
            st.session_state.template_config = parse_template(tmp.name)
            st.session_state.template_path = tmp.name
        except Exception as e:
            st.warning(f"模板解析失败: {e}")

    tc = st.session_state.template_config

    st.divider()

    with st.expander("页面设置", expanded=True):
        opt_margins = st.checkbox("设置页边距", value=True)
        if opt_margins:
            mc1, mc2 = st.columns(2)
            with mc1:
                margin_top = st.number_input("上边距(cm)", value=tc.pages[0].top_cm if tc and tc.pages else 2.5, step=0.1, format="%.1f")
                margin_left = st.number_input("左边距(cm)", value=tc.pages[0].left_cm if tc and tc.pages else 3.0, step=0.1, format="%.1f")
            with mc2:
                margin_bottom = st.number_input("下边距(cm)", value=tc.pages[0].bottom_cm if tc and tc.pages else 2.5, step=0.1, format="%.1f")
                margin_right = st.number_input("右边距(cm)", value=tc.pages[0].right_cm if tc and tc.pages else 2.0, step=0.1, format="%.1f")
        else:
            margin_top = margin_bottom = margin_left = margin_right = 0
        opt_header = st.text_input("页眉文字", value="", placeholder="留空不设置")

    with st.expander("字体字号", expanded=True):
        opt_fonts = st.checkbox("统一字体字号", value=True)
        if opt_fonts:
            fc1, fc2 = st.columns(2)
            with fc1:
                cn_body_font = st.selectbox("正文中文字体", ["宋体", "楷体", "黑体", "仿宋"], index=0)
                body_size = st.number_input("正文字号(pt)", value=tc.body_text.font.size_pt if tc and tc.body_text and tc.body_text.font.size_pt else 12.0, step=0.5, format="%.1f")
                h1_size = st.number_input("一级标题字号(pt)", value=tc.heading1.font.size_pt if tc and tc.heading1 and tc.heading1.font.size_pt else 15.0, step=0.5, format="%.1f")
            with fc2:
                en_font = st.selectbox("英文/数字字体", ["Times New Roman", "Arial", "Calibri"], index=0)
                h2_size = st.number_input("二级标题字号(pt)", value=tc.heading2.font.size_pt if tc and tc.heading2 and tc.heading2.font.size_pt else 14.0, step=0.5, format="%.1f")
                h3_size = st.number_input("三级标题字号(pt)", value=tc.heading3.font.size_pt if tc and tc.heading3 and tc.heading3.font.size_pt else 12.0, step=0.5, format="%.1f")
        else:
            cn_body_font, en_font = "宋体", "Times New Roman"
            body_size, h1_size, h2_size, h3_size = 12.0, 15.0, 14.0, 12.0
        opt_en = st.checkbox("英文统一 Times New Roman", value=True)

    with st.expander("段落格式", expanded=True):
        opt_para = st.checkbox("格式化段落", value=True)
        if opt_para:
            pc1, pc2 = st.columns(2)
            with pc1:
                line_spacing_val = st.number_input("正文行距(磅)", value=tc.body_text.line_spacing_pt if tc and tc.body_text and tc.body_text.line_spacing_pt else 20.0, step=1.0, format="%.0f")
                indent_chars = st.number_input("首行缩进(字符)", value=2.0, step=0.5, format="%.1f")
            with pc2:
                h1_before = st.number_input("一级标题段前(pt)", value=24.0, step=1.0, format="%.0f")
                h1_after = st.number_input("一级标题段后(pt)", value=18.0, step=1.0, format="%.0f")
        else:
            line_spacing_val, indent_chars, h1_before, h1_after = 20.0, 2.0, 24.0, 18.0
        opt_indent = st.checkbox("首行缩进", value=True)

    with st.expander("字符替换与清理", expanded=False):
        opt_punct = st.checkbox("标点符号替换", value=False)
        punct_dir = st.radio("方向", ["中文->英文", "英文->中文"], horizontal=True) if opt_punct else "中文->英文"
        opt_spaces = st.checkbox("清理多余空格", value=True)
        opt_empty = st.checkbox("清理所有空行", value=True)
        opt_cn_en = st.checkbox("中英文间加空格", value=False)
        opt_num_unit = st.checkbox("数字与单位间加空格", value=False)

    with st.expander("表格格式", expanded=False):
        opt_table3 = st.checkbox("三线表格式", value=True)
        opt_table_font = st.checkbox("统一表格字体", value=True)
        table_size = st.number_input("表格字号(pt)", value=10.5, step=0.5, format="%.1f") if opt_table_font else 10.5
        opt_shading = st.checkbox("清除表格底纹", value=True)
        opt_repeat = st.checkbox("跨页表头重复", value=True)

    with st.expander("引用与参考文献", expanded=False):
        opt_cite = st.checkbox("角标设为上标", value=True)
        cite_size = st.number_input("角标字号(pt)", value=9.0, step=0.5, format="%.1f") if opt_cite else 9.0
        opt_ref = st.checkbox("参考文献格式化", value=True)

    run_btn = st.button("🚀 开始格式化", type="primary", use_container_width=True)

with col_right:
    if run_btn:
        if not paper_file:
            st.error("请上传论文文件")
            st.stop()

        paper_tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        paper_tmp.write(paper_file.getvalue())
        paper_tmp.close()

        template_tmp_path = st.session_state.get("template_path")
        output_tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        output_tmp.close()

        custom_config = TemplateConfig(
            pages=[PageSpec(top_cm=margin_top, bottom_cm=margin_bottom, left_cm=margin_left, right_cm=margin_right)],
            heading1=ParagraphSpec(font=FontSpec(cn_name="黑体", en_name=en_font, size_pt=h1_size, bold=True), space_before_pt=h1_before, space_after_pt=h1_after),
            heading2=ParagraphSpec(font=FontSpec(cn_name="黑体", en_name=en_font, size_pt=h2_size, bold=True), space_before_pt=h1_before, space_after_pt=6),
            heading3=ParagraphSpec(font=FontSpec(cn_name="黑体", en_name=en_font, size_pt=h3_size, bold=True)),
            body_text=ParagraphSpec(font=FontSpec(cn_name=cn_body_font, en_name=en_font, size_pt=body_size), line_spacing_pt=line_spacing_val, first_indent_pt=indent_chars * body_size),
            abstract_title=ParagraphSpec(font=FontSpec(cn_name="黑体", size_pt=16), line_spacing=1.5, space_before_pt=18, space_after_pt=18, alignment="CENTER"),
        )

        options = {
            "punctuation": opt_punct,
            "punctuation_direction": "cn_to_en" if "->" in punct_dir and "英" in punct_dir.split("->")[1] else "en_to_cn",
            "clean_spaces": opt_spaces, "clean_empty_lines": opt_empty,
            "cn_en_space": opt_cn_en, "number_unit_space": opt_num_unit,
            "fonts": opt_fonts, "en_font": opt_en,
            "paragraphs": opt_para, "first_indent": opt_indent,
            "margins": opt_margins, "header_text": opt_header if opt_header.strip() else None,
            "three_line_table": opt_table3, "table_font": opt_table_font,
            "clear_shading": opt_shading, "repeat_header": opt_repeat,
            "citation_superscript": opt_cite, "reference_format": opt_ref,
            "_custom_config": custom_config,
        }

        progress = st.progress(0)
        status = st.empty()
        log_area = st.empty()
        log_lines = []

        def log_cb(msg):
            log_lines.append(msg)
            log_area.code("\n".join(log_lines[-15:]), language=None)

        status.info("正在格式化...")
        try:
            stats = format_paper(
                paper_path=paper_tmp.name, output_path=output_tmp.name,
                template_path=template_tmp_path, options=options, callback=log_cb,
            )
            progress.progress(100)
            status.success("格式化完成!")

            with open(output_tmp.name, "rb") as f:
                st.download_button("下载格式化后的论文", data=f.read(),
                    file_name=f"formatted_{paper_file.name}",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True)
        except Exception as e:
            progress.progress(100)
            status.error(f"处理出错: {e}")
            import traceback
            st.code(traceback.format_exc(), language=None)
    elif tc:
        st.markdown("### 模板参数预览")
        st.code(tc.summary(), language=None)
    else:
        st.info("👈 上传论文，调整参数，点击「开始格式化」")
