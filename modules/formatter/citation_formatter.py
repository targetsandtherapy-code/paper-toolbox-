"""角标上标 + 参考文献格式模块"""
import re
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

CITATION_PATTERN = re.compile(r'\[(\d+(?:\s*[-\u2013\u2014]\s*\d+)?(?:\s*[,\uff0c]\s*\d+)*)\]')


def _get_run_positions(paragraph):
    """计算每个 run 在段落文本中的起止位置"""
    positions = []
    offset = 0
    for run in paragraph.runs:
        length = len(run.text)
        positions.append((offset, offset + length, run))
        offset += length
    return positions


def _is_already_superscript(run) -> bool:
    rPr = run._element.find(qn('w:rPr'))
    if rPr is not None:
        vert = rPr.find(qn('w:vertAlign'))
        if vert is not None and vert.get(qn('w:val')) == 'superscript':
            return True
    return False


def _set_run_superscript(run, size_pt: float = None):
    """将 run 设为上标"""
    rPr = run._element.get_or_add_rPr()

    vert = rPr.find(qn('w:vertAlign'))
    if vert is None:
        vert = run._element.makeelement(qn('w:vertAlign'), {})
        rPr.append(vert)
    vert.set(qn('w:val'), 'superscript')

    if size_pt:
        run.font.size = Pt(size_pt)


def _split_run_at(run, position):
    """在指定位置拆分 run，返回 (前半run元素, 后半run元素)"""
    from copy import deepcopy

    text = run.text
    if position <= 0 or position >= len(text):
        return None, None

    before_text = text[:position]
    after_text = text[position:]

    run.text = before_text

    new_r = deepcopy(run._element)
    for t in new_r.findall(qn('w:t')):
        new_r.remove(t)
    new_t = run._element.makeelement(qn('w:t'), {})
    new_t.text = after_text
    new_t.set(qn('xml:space'), 'preserve')
    new_r.append(new_t)

    run._element.addnext(new_r)
    return run._element, new_r


def format_citation_superscript(doc: Document, size_pt: float = 9.0) -> int:
    """将正文中的引用角标设为上标，处理跨 run 和已有上标的情况"""
    count = 0

    for para in doc.paragraphs:
        full_text = para.text
        if not CITATION_PATTERN.search(full_text):
            continue

        matches = list(CITATION_PATTERN.finditer(full_text))
        if not matches:
            continue

        citation_ranges = [(m.start(), m.end()) for m in matches]

        run_positions = _get_run_positions(para)

        for cite_start, cite_end in reversed(citation_ranges):
            affected_runs = []
            for run_start, run_end, run in run_positions:
                if run_end <= cite_start or run_start >= cite_end:
                    continue
                affected_runs.append((run_start, run_end, run))

            if not affected_runs:
                continue

            if len(affected_runs) == 1:
                run_start, run_end, run = affected_runs[0]
                local_start = cite_start - run_start
                local_end = cite_end - run_start

                if local_start == 0 and local_end == len(run.text):
                    if not _is_already_superscript(run):
                        _set_run_superscript(run, size_pt)
                        count += 1
                else:
                    original_text = run.text
                    before = original_text[:local_start]
                    cite_text = original_text[local_start:local_end]
                    after = original_text[local_end:]

                    run.text = before if before else ""

                    insert_after = run._element

                    cite_run_elem = _make_superscript_run_elem(para, cite_text, run, size_pt)
                    insert_after.addnext(cite_run_elem)
                    insert_after = cite_run_elem

                    if after:
                        after_run_elem = _clone_run_elem_with_text(run, after)
                        insert_after.addnext(after_run_elem)

                    if not before:
                        run.text = ""

                    count += 1
            else:
                for run_start, run_end, run in affected_runs:
                    if not _is_already_superscript(run):
                        overlap_start = max(cite_start, run_start) - run_start
                        overlap_end = min(cite_end, run_end) - run_start

                        if overlap_start == 0 and overlap_end == len(run.text):
                            _set_run_superscript(run, size_pt)
                        else:
                            text = run.text
                            cite_part = text[overlap_start:overlap_end]
                            before = text[:overlap_start]
                            after = text[overlap_end:]

                            run.text = before if before else ""
                            insert_after = run._element

                            sup_elem = _make_superscript_run_elem(para, cite_part, run, size_pt)
                            insert_after.addnext(sup_elem)
                            insert_after = sup_elem

                            if after:
                                after_elem = _clone_run_elem_with_text(run, after)
                                insert_after.addnext(after_elem)

                            if not before:
                                run.text = ""

                count += 1

            run_positions = _get_run_positions(para)

    return count


def _make_superscript_run_elem(para, text, source_run, size_pt):
    """基于源 run 创建上标 run 元素，保留字体信息"""
    from copy import deepcopy

    new_r = deepcopy(source_run._element)

    for t in new_r.findall(qn('w:t')):
        new_r.remove(t)

    new_t = para._element.makeelement(qn('w:t'), {})
    new_t.text = text
    new_t.set(qn('xml:space'), 'preserve')
    new_r.append(new_t)

    rPr = new_r.find(qn('w:rPr'))
    if rPr is None:
        rPr = para._element.makeelement(qn('w:rPr'), {})
        new_r.insert(0, rPr)

    vert = rPr.find(qn('w:vertAlign'))
    if vert is None:
        vert = para._element.makeelement(qn('w:vertAlign'), {})
        rPr.append(vert)
    vert.set(qn('w:val'), 'superscript')

    if size_pt:
        sz = rPr.find(qn('w:sz'))
        if sz is None:
            sz = para._element.makeelement(qn('w:sz'), {})
            rPr.append(sz)
        sz.set(qn('w:val'), str(int(size_pt * 2)))

        szCs = rPr.find(qn('w:szCs'))
        if szCs is None:
            szCs = para._element.makeelement(qn('w:szCs'), {})
            rPr.append(szCs)
        szCs.set(qn('w:val'), str(int(size_pt * 2)))

    return new_r


def _clone_run_elem_with_text(source_run, text):
    """克隆 run 元素保留格式，使用新文本"""
    from copy import deepcopy

    new_r = deepcopy(source_run._element)
    for t in new_r.findall(qn('w:t')):
        new_r.remove(t)
    new_t = source_run._element.makeelement(qn('w:t'), {})
    new_t.text = text
    new_t.set(qn('xml:space'), 'preserve')
    new_r.append(new_t)
    return new_r


def format_reference_list(doc: Document, cn_font: str = "宋体", en_font: str = "Times New Roman",
                          size_pt: float = 10.5, hanging_indent_pt: float = 21.0) -> int:
    """格式化参考文献列表：字号、悬挂缩进"""
    in_refs = False
    count = 0

    for para in doc.paragraphs:
        text = para.text.strip()

        if text in ("参考文献", "References", "REFERENCES", "参 考 文 献"):
            in_refs = True
            continue

        if in_refs and text:
            if re.match(r'^\[\d+\]', text):
                pf = para.paragraph_format
                pf.first_line_indent = Pt(-hanging_indent_pt)
                pf.left_indent = Pt(hanging_indent_pt)
                pf.space_before = Pt(0)
                pf.space_after = Pt(0)

                for run in para.runs:
                    run.font.size = Pt(size_pt)
                    run.font.name = en_font
                    rpr = run._element.get_or_add_rPr()
                    rfonts = rpr.find(qn('w:rFonts'))
                    if rfonts is None:
                        rfonts = run._element.makeelement(qn('w:rFonts'), {})
                        rpr.insert(0, rfonts)
                    rfonts.set(qn('w:eastAsia'), cn_font)
                    rfonts.set(qn('w:ascii'), en_font)
                    rfonts.set(qn('w:hAnsi'), en_font)

                count += 1
            elif not text.startswith("["):
                in_refs = False

    return count
