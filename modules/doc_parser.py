"""Word 文档解析 & 角标识别模块"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from docx import Document


@dataclass
class CitationMarker:
    """单个引用角标"""
    ids: list[int]           # 角标编号列表，如 [1] → [1], [1,2] → [1,2], [1-3] → [1,2,3]
    paragraph_text: str      # 角标所在段落全文
    context_before: str      # 角标前的句子/片段
    paragraph_index: int     # 段落在文档中的位置索引
    raw_marker: str          # 原始角标文本，如 "[1]", "[1-3]"


MARKER_PATTERN = re.compile(r'\[(\d+(?:\s*[-–—]\s*\d+)?(?:\s*[,，]\s*\d+)*)\]')


def _expand_marker_ids(raw: str) -> list[int]:
    """展开角标编号: "[1-3,5]" → [1,2,3,5]"""
    raw = raw.strip("[]")
    ids = []
    for part in re.split(r'[,，]', raw):
        part = part.strip()
        range_match = re.match(r'(\d+)\s*[-–—]\s*(\d+)', part)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            ids.extend(range(start, end + 1))
        elif part.isdigit():
            ids.append(int(part))
    return sorted(set(ids))


def _extract_context_before(text: str, marker_start: int, max_chars: int = 200) -> str:
    """提取角标前的上下文（取角标前最近的句子）"""
    before = text[:marker_start].rstrip()
    if not before:
        return ""

    # 尝试找最近的句号/分号等分隔符，取最后一个完整句子
    sent_breaks = [m.end() for m in re.finditer(r'[。；;！!？?\.\n]', before)]
    if sent_breaks:
        last_break = sent_breaks[-1]
        if marker_start - last_break < max_chars:
            return before[last_break:].strip()

    return before[-max_chars:].strip()


class DocParser:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if self.file_path.suffix.lower() != ".docx":
            raise ValueError(f"仅支持 .docx 格式，当前: {self.file_path.suffix}")
        self.doc = Document(str(self.file_path))

    def extract_markers(self) -> list[CitationMarker]:
        """提取文档中所有引用角标"""
        markers = []
        for para_idx, para in enumerate(self.doc.paragraphs):
            text = para.text.strip()
            if not text:
                continue

            for match in MARKER_PATTERN.finditer(text):
                raw_marker = match.group(0)
                ids = _expand_marker_ids(raw_marker)
                context_before = _extract_context_before(text, match.start())

                markers.append(CitationMarker(
                    ids=ids,
                    paragraph_text=text,
                    context_before=context_before,
                    paragraph_index=para_idx,
                    raw_marker=raw_marker,
                ))

        return markers

    def extract_markers_grouped(self) -> dict[int, CitationMarker]:
        """按角标编号分组返回（每个编号取第一次出现的位置）"""
        markers = self.extract_markers()
        grouped = {}
        for m in markers:
            for cid in m.ids:
                if cid not in grouped:
                    grouped[cid] = m
        return dict(sorted(grouped.items()))

    def get_title(self) -> str:
        """提取论文标题（取前几个非空段落中最可能是标题的那个）"""
        for para in self.doc.paragraphs[:10]:
            text = para.text.strip()
            if not text or len(text) < 4:
                continue
            if MARKER_PATTERN.search(text):
                continue
            if para.style and para.style.name and 'title' in para.style.name.lower():
                return text
            if para.style and para.style.name and 'heading' in para.style.name.lower():
                return text
        for para in self.doc.paragraphs[:6]:
            text = para.text.strip()
            if text and len(text) >= 4 and not MARKER_PATTERN.search(text):
                return text
        return ""

    def get_full_text(self) -> str:
        """获取文档全文"""
        return "\n".join(p.text for p in self.doc.paragraphs if p.text.strip())

    def get_paragraphs(self) -> list[str]:
        """获取所有非空段落"""
        return [p.text.strip() for p in self.doc.paragraphs if p.text.strip()]
