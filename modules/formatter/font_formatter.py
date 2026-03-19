"""字体字号统一模块 — 按模板配置统一论文中的字体和字号"""
import re
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from modules.formatter.template_parser import TemplateConfig, ParagraphSpec


def _is_chinese_char(c: str) -> bool:
    return '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf'


def _apply_font_to_run(run, cn_font: str = None, en_font: str = "Times New Roman",
                        size_pt: float = None, bold: bool = None):
    """对单个 run 应用字体设置，区分中英文"""
    rpr = run._element.get_or_add_rPr()

    if cn_font or en_font:
        rfonts = rpr.find(qn('w:rFonts'))
        if rfonts is None:
            rfonts = run._element.makeelement(qn('w:rFonts'), {})
            rpr.insert(0, rfonts)
        if en_font:
            rfonts.set(qn('w:ascii'), en_font)
            rfonts.set(qn('w:hAnsi'), en_font)
            rfonts.set(qn('w:cs'), en_font)
        if cn_font:
            rfonts.set(qn('w:eastAsia'), cn_font)

    if size_pt is not None:
        run.font.size = Pt(size_pt)

    if bold is not None:
        run.font.bold = bold


def _get_heading_level(para) -> int:
    """判断段落是第几级标题，返回 0 表示非标题"""
    style_name = para.style.name.lower()
    if "heading 1" in style_name or style_name == "标题 1":
        return 1
    if "heading 2" in style_name or style_name == "标题 2":
        return 2
    if "heading 3" in style_name or style_name == "标题 3":
        return 3
    if "heading 4" in style_name or style_name == "标题 4":
        return 4
    return 0


def _detect_heading_by_pattern(text: str) -> int:
    """通过文本模式判断标题级别"""
    text = text.strip()
    if re.match(r'^第[一二三四五六七八九十]+章\s', text):
        return 1
    if re.match(r'^第[一二三四五六七八九十]+节\s', text):
        return 2
    if re.match(r'^\d+\.\d+\.\d+\s', text):
        return 3
    if re.match(r'^\d+\.\d+\s', text):
        return 2
    if re.match(r'^[一二三四五六七八九十]+[、.]\s*', text):
        return 1
    if re.match(r'^[\(（][一二三四五六七八九十]+[\)）]\s*', text):
        return 2
    if re.match(r'^\d+[、.]\s', text):
        return 3
    return 0


def format_fonts(doc: Document, config: TemplateConfig) -> dict:
    """统一文档字体"""
    stats = {"headings": 0, "body": 0, "en_font": 0}

    heading_specs = {
        1: config.heading1,
        2: config.heading2,
        3: config.heading3,
    }

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        level = _get_heading_level(para) or _detect_heading_by_pattern(text)

        if level and level in heading_specs and heading_specs[level]:
            spec = heading_specs[level]
            for run in para.runs:
                _apply_font_to_run(
                    run,
                    cn_font=spec.font.cn_name,
                    en_font=spec.font.en_name or "Times New Roman",
                    size_pt=spec.font.size_pt,
                    bold=spec.font.bold if spec.font.bold is not None else True,
                )
            stats["headings"] += 1

        elif config.body_text and len(text) > 10:
            spec = config.body_text
            for run in para.runs:
                _apply_font_to_run(
                    run,
                    cn_font=spec.font.cn_name or "宋体",
                    en_font=spec.font.en_name or "Times New Roman",
                    size_pt=spec.font.size_pt,
                    bold=False,
                )
            stats["body"] += 1

    return stats


def unify_english_font(doc: Document, font_name: str = "Times New Roman") -> int:
    """将所有英文和数字统一为指定字体"""
    count = 0
    for para in doc.paragraphs:
        for run in para.runs:
            has_en = any(c.isascii() and c.isalnum() for c in run.text)
            if has_en:
                rpr = run._element.get_or_add_rPr()
                rfonts = rpr.find(qn('w:rFonts'))
                if rfonts is None:
                    rfonts = run._element.makeelement(qn('w:rFonts'), {})
                    rpr.insert(0, rfonts)
                rfonts.set(qn('w:ascii'), font_name)
                rfonts.set(qn('w:hAnsi'), font_name)
                rfonts.set(qn('w:cs'), font_name)
                count += 1
    return count
