"""文本比对模块 — N-gram 滑动窗口 + 连续重复片段检测"""
import re
from collections import defaultdict


def _split_sentences(text: str) -> list[str]:
    """按中英文句号分割句子"""
    parts = re.split(r'(?<=[。！？.!?])\s*', text)
    return [s.strip() for s in parts if s.strip() and len(s.strip()) >= 5]


def _ngrams(text: str, n: int = 13) -> set[str]:
    """提取 N-gram 字符片段"""
    text = re.sub(r'\s+', '', text)
    grams = set()
    for i in range(len(text) - n + 1):
        grams.add(text[i:i + n])
    return grams


def sentence_ngram_overlap(sent_a: str, sent_b: str, n: int = 6) -> float:
    """计算两个句子的 N-gram 重叠率"""
    grams_a = _ngrams(sent_a, n)
    grams_b = _ngrams(sent_b, n)
    if not grams_a or not grams_b:
        return 0.0
    overlap = len(grams_a & grams_b)
    return overlap / min(len(grams_a), len(grams_b))


def compute_document_similarity(text_a: str, text_b: str, n: int = 13) -> dict:
    """计算两篇文档的整体 N-gram 重复率"""
    grams_a = _ngrams(text_a, n)
    grams_b = _ngrams(text_b, n)
    if not grams_a:
        return {"overlap_ratio": 0.0, "overlap_count": 0, "total_a": 0}

    overlap = grams_a & grams_b
    return {
        "overlap_ratio": round(len(overlap) / len(grams_a), 4),
        "overlap_count": len(overlap),
        "total_a": len(grams_a),
    }


def find_repeated_sentences(text: str, threshold: float = 0.8, n: int = 6) -> list[dict]:
    """在文档内部查找高度重复的句子对"""
    sentences = _split_sentences(text)
    results = []

    for i in range(len(sentences)):
        for j in range(i + 1, len(sentences)):
            overlap = sentence_ngram_overlap(sentences[i], sentences[j], n)
            if overlap >= threshold:
                results.append({
                    "index_a": i,
                    "index_b": j,
                    "sentence_a": sentences[i],
                    "sentence_b": sentences[j],
                    "overlap": round(overlap, 4),
                })

    return results


def highlight_repeated_segments(text: str, reference_text: str, n: int = 13) -> list[dict]:
    """标记原文中与参考文本重复的片段位置"""
    clean_text = re.sub(r'\s+', '', text)
    ref_grams = _ngrams(reference_text, n)

    segments = []
    i = 0
    while i < len(clean_text) - n + 1:
        gram = clean_text[i:i + n]
        if gram in ref_grams:
            start = i
            end = i + n
            while end < len(clean_text) and clean_text[end - n + 1:end + 1] in ref_grams:
                end += 1
            segments.append({"start": start, "end": end, "text": clean_text[start:end]})
            i = end
        else:
            i += 1

    return segments
