"""论文格式调整工具 — 主流程"""
import sys
from pathlib import Path
from docx import Document

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.formatter.template_parser import parse_template, TemplateConfig
from modules.formatter.char_replacer import (
    replace_punctuation, clean_extra_spaces, clean_empty_paragraphs,
    add_space_between_cn_en, add_space_between_number_unit,
)
from modules.formatter.font_formatter import format_fonts, unify_english_font
from modules.formatter.paragraph_formatter import format_paragraphs, set_first_line_indent
from modules.formatter.page_formatter import set_page_margins, set_header_text
from modules.formatter.table_formatter import (
    apply_three_line_table, set_table_font, clear_all_shading, enable_repeat_header_row,
)
from modules.formatter.citation_formatter import format_citation_superscript, format_reference_list


def format_paper(
    paper_path: str,
    output_path: str,
    template_path: str = None,
    options: dict = None,
    callback=None,
) -> dict:
    """格式化论文主流程

    Args:
        paper_path: 论文 .docx 路径
        output_path: 输出 .docx 路径
        template_path: 学校模板 .docx 路径（可选）
        options: 功能开关字典
        callback: 日志回调
    """
    if options is None:
        options = {}

    def log(msg):
        if callback:
            callback(msg)
        else:
            try:
                print(msg)
            except Exception:
                pass

    stats = {}

    # 加载模板配置
    config = None
    custom_config = options.get("_custom_config")
    if custom_config:
        config = custom_config
        log("使用自定义配置")
    elif template_path:
        log("加载学校模板...")
        config = parse_template(template_path)
        log(f"  模板解析完成")
    else:
        from modules.formatter.template_parser import PageSpec, ParagraphSpec, FontSpec
        config = TemplateConfig(
            pages=[PageSpec()],
            heading1=ParagraphSpec(font=FontSpec(cn_name="黑体", en_name="Times New Roman", size_pt=15, bold=True), space_before_pt=24, space_after_pt=18),
            heading2=ParagraphSpec(font=FontSpec(cn_name="黑体", en_name="Times New Roman", size_pt=14, bold=True), space_before_pt=24, space_after_pt=6),
            heading3=ParagraphSpec(font=FontSpec(cn_name="黑体", en_name="Times New Roman", size_pt=12, bold=True)),
            body_text=ParagraphSpec(font=FontSpec(cn_name="宋体", en_name="Times New Roman", size_pt=12), line_spacing_pt=20, first_indent_pt=24),
            abstract_title=ParagraphSpec(font=FontSpec(cn_name="黑体", size_pt=16), line_spacing=1.5, space_before_pt=18, space_after_pt=18, alignment="CENTER"),
        )

    log("打开论文文档...")
    doc = Document(paper_path)

    # 字符替换
    if options.get("punctuation", True):
        direction = options.get("punctuation_direction", "cn_to_en")
        log(f"标点符号替换 ({direction})...")
        n = replace_punctuation(doc, direction)
        stats["punctuation"] = n
        log(f"  替换了 {n} 处")

    if options.get("clean_spaces", True):
        log("清理多余空格...")
        n = clean_extra_spaces(doc)
        stats["clean_spaces"] = n
        log(f"  清理了 {n} 处")

    if options.get("clean_empty_lines", True):
        log("清理空行...")
        n = clean_empty_paragraphs(doc, max_consecutive=0)
        stats["clean_empty_lines"] = n
        log(f"  清理了 {n} 个空段落")

    if options.get("cn_en_space", False):
        log("中英文间距...")
        n = add_space_between_cn_en(doc)
        stats["cn_en_space"] = n
        log(f"  处理了 {n} 处")

    if options.get("number_unit_space", False):
        log("数字与单位间距...")
        n = add_space_between_number_unit(doc)
        stats["number_unit_space"] = n
        log(f"  处理了 {n} 处")

    # 字体
    if options.get("fonts", True):
        log("统一字体字号...")
        s = format_fonts(doc, config)
        stats["fonts"] = s
        log(f"  标题 {s['headings']} 个, 正文 {s['body']} 个")

    if options.get("en_font", True):
        log("统一英文字体为 Times New Roman...")
        n = unify_english_font(doc)
        stats["en_font"] = n
        log(f"  处理了 {n} 个 run")

    # 段落
    if options.get("paragraphs", True):
        log("格式化段落...")
        s = format_paragraphs(doc, config)
        stats["paragraphs"] = s
        log(f"  标题 {s.get('heading',0)}, 正文 {s.get('body',0)}, 章节标题 {s.get('section_title',0)}")

    if options.get("first_indent", True):
        log("设置首行缩进...")
        n = set_first_line_indent(doc)
        stats["first_indent"] = n
        log(f"  设置了 {n} 个段落")

    # 页面
    if options.get("margins", True):
        log("设置页边距...")
        n = set_page_margins(doc, config)
        stats["margins"] = n
        log(f"  设置了 {n} 个 section")

    if options.get("header_text"):
        text = options["header_text"]
        log(f"设置页眉: {text}")
        set_header_text(doc, text)

    # 表格
    if options.get("three_line_table", True):
        log("应用三线表...")
        n = apply_three_line_table(doc)
        stats["three_line_table"] = n
        log(f"  处理了 {n} 个表格")

    if options.get("table_font", True):
        log("统一表格字体...")
        n = set_table_font(doc)
        stats["table_font"] = n
        log(f"  处理了 {n} 个单元格")

    if options.get("clear_shading", True):
        log("清除表格底纹...")
        n = clear_all_shading(doc)
        stats["clear_shading"] = n

    if options.get("repeat_header", True):
        log("启用跨页表头重复...")
        n = enable_repeat_header_row(doc)
        stats["repeat_header"] = n

    # 引用
    if options.get("citation_superscript", True):
        log("角标设为上标...")
        n = format_citation_superscript(doc)
        stats["citation_superscript"] = n
        log(f"  处理了 {n} 个角标")

    if options.get("reference_format", True):
        log("格式化参考文献列表...")
        n = format_reference_list(doc)
        stats["reference_format"] = n
        log(f"  处理了 {n} 条参考文献")

    # 保存
    log(f"保存到: {output_path}")
    doc.save(output_path)
    log("完成!")

    return stats
