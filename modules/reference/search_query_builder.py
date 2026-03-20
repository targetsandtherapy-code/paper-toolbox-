"""从 AnalysisResult 的「检索轨道」字段组装数据库检索式（与 key_claim 论证轨道分离）。

核心原则：知网/CrossRef 搜索词越短越精准。最终检索式 **最多 3-4 个词**。
"""
from __future__ import annotations

import re
from typing import List

MAX_QUERY_TOKENS = 4

_QUERY_JUNK_TOKENS = frozenset(
    {
        "角标", "参考文献", "引用", "本文", "本研究", "怎么", "如何",
        "ppt", "课件", "读书报告", "文献检索", "检索技巧", "论文",
        "text", "summarization", "summarisation", "journal", "article",
        "研究发现", "结果表明", "显著", "日益",
    }
)

_QUERY_JUNK_PHRASES_RE = re.compile(
    r"text\s+summariz|文献检索|读书报告|护理文献|发生率|负相关|正相关|显著高于|日益严峻",
    re.I,
)


def _is_junk_token(t: str) -> bool:
    s = (t or "").strip()
    if not s or len(s) < 2:
        return True
    low = s.lower()
    if low in _QUERY_JUNK_TOKENS:
        return True
    if _QUERY_JUNK_PHRASES_RE.search(s):
        return True
    return False


def _clean_tokens(parts: List[str], max_tokens: int = 0) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for p in parts:
        for raw in re.split(r"[\s,，;；]+", (p or "").strip()):
            t = raw.strip()
            if not t or _is_junk_token(t):
                continue
            k = t.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(t)
            if max_tokens and len(out) >= max_tokens:
                return out
    return out


def _first_latin_author(authors: List[str]) -> str | None:
    for a in authors:
        if a and re.search(r"[A-Za-z]", a):
            return a.strip()
    return None


def _first_cn_author(authors: List[str]) -> str | None:
    for a in authors:
        if a and re.search(r"[\u4e00-\u9fff]", a):
            return a.strip()
    return None


def build_search_queries_from_analysis(analysis) -> tuple[str, str]:
    """组装最终检索式。每条最多 MAX_QUERY_TOKENS 个词。

    优先级：作者 → 题名关键词（前几个）→ search_query_* 兜底。
    不使用 key_claim（结论性表述不适合直接检索）。
    """
    authors = list(getattr(analysis, "ref_authors", None) or [])
    tk_cn = list(getattr(analysis, "ref_title_keywords_cn", None) or [])
    tk_en = list(getattr(analysis, "ref_title_keywords_en", None) or [])

    cn_kw = list(getattr(analysis, "cn_keywords", None) or [])
    en_kw = list(getattr(analysis, "en_keywords", None) or [])
    sq_cn = (getattr(analysis, "search_query_cn", None) or "").strip()
    sq_en = (getattr(analysis, "search_query_en", None) or "").strip()

    # -- 中文 --
    cn_pool: List[str] = []
    cn_author = _first_cn_author(authors)
    if cn_author:
        cn_pool.append(cn_author)
    cn_pool.extend(tk_cn[:5])
    if not cn_pool:
        cn_pool.extend(cn_kw[:4])
    cn_q = " ".join(_clean_tokens(cn_pool, MAX_QUERY_TOKENS))
    if not cn_q and sq_cn:
        cn_q = " ".join(_clean_tokens([sq_cn], MAX_QUERY_TOKENS))
    if not cn_q:
        cn_q = " ".join(_clean_tokens(cn_kw[:4], MAX_QUERY_TOKENS))

    # -- 英文 --
    en_pool: List[str] = []
    la = _first_latin_author(authors)
    if la:
        en_pool.append(la)
    en_pool.extend(tk_en[:5])
    if not en_pool:
        en_pool.extend(en_kw[:4])
    en_q = " ".join(_clean_tokens(en_pool, MAX_QUERY_TOKENS))
    if not en_q and sq_en:
        en_q = " ".join(_clean_tokens([sq_en], MAX_QUERY_TOKENS))
    if not en_q:
        en_q = " ".join(_clean_tokens(en_kw[:4], MAX_QUERY_TOKENS))

    return cn_q.strip(), en_q.strip()


def rank_keywords_from_analysis(analysis) -> list[str]:
    """fast_rank / 相关度排序用。不限长度，但仍去垃圾词。"""
    parts: List[str] = []
    parts.extend(getattr(analysis, "ref_authors", None) or [])
    parts.extend(getattr(analysis, "ref_title_keywords_cn", None) or [])
    parts.extend(getattr(analysis, "ref_title_keywords_en", None) or [])
    parts.extend(getattr(analysis, "ref_population", None) or [])
    parts.extend(getattr(analysis, "ref_method", None) or [])
    yh = (getattr(analysis, "ref_year_hint", None) or "").strip()
    jh = (getattr(analysis, "ref_journal_hint", None) or "").strip()
    if yh:
        parts.append(yh)
    if jh:
        parts.append(jh)
    if not parts:
        parts.extend(getattr(analysis, "cn_keywords", None) or [])
        parts.extend(getattr(analysis, "en_keywords", None) or [])
    return _clean_tokens(parts)
