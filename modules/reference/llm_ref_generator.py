"""当学术库搜不到《…》类文献时，用网页搜索（DuckDuckGo）查找真实来源。"""
from __future__ import annotations

import re
from typing import Optional

from modules.reference.searcher.base import Paper
from modules.reference.searcher.web_search import search_policy_web, search_web_general
from modules.reference.searcher.google_books import search_books


def _extract_guillemet(ctx: str) -> Optional[str]:
    if not ctx or "《" not in ctx:
        return None
    m = re.search(r"《([^》]+)》", ctx)
    if not m:
        return None
    inner = m.group(1).strip()
    inner = re.sub(r'["""\u201c\u201d\']+', '', inner).strip()
    return inner or None


def _normalize_for_match(s: str) -> str:
    return re.sub(r'[""「」\s《》\'"]+', '', (s or "").lower())


def _best_match_from_results(results: list[Paper], inner: str) -> Optional[Paper]:
    """从搜索结果中选最匹配《inner》的条目。宽松匹配：去掉引号/空格后比较。"""
    if not results:
        return None
    norm_inner = _normalize_for_match(inner)
    for p in results:
        norm_title = _normalize_for_match(p.title or "")
        if norm_inner in norm_title or norm_title in norm_inner:
            return p
        core_chars = [c for c in norm_inner if c.isalnum()]
        title_chars = [c for c in norm_title if c.isalnum()]
        if len(core_chars) > 3 and all(
            c in "".join(title_chars) for c in core_chars[:8]
        ):
            return p
    return results[0] if results else None


def try_web_search_for_quoted_title(
    context_before: str,
    ref_type: str,
    key_claim: str = "",
) -> Optional[Paper]:
    """对《…》内容做网页搜索，返回真实来源的 Paper。

    - ref_type R/EB → 搜 gov.cn（政策文件）
    - ref_type M → 通用搜索（专著/教材）
    """
    inner = _extract_guillemet(context_before or "")
    if not inner:
        return None

    if ref_type in ("R", "EB"):
        results = search_policy_web(inner, max_results=5)
    elif ref_type == "M":
        results = search_books(inner, max_results=5)
        if not results:
            results = search_web_general(inner, max_results=3)
    else:
        return None

    best = _best_match_from_results(results, inner)
    if best is None:
        return None

    if not best.title.startswith("《"):
        display = f"《{inner}》"
        if inner.lower() in (best.title or "").lower():
            best = Paper(
                title=best.title,
                authors=best.authors,
                year=best.year,
                journal=best.journal,
                doi=best.doi,
                abstract=best.abstract,
                citation_count=best.citation_count,
                url=best.url,
                source=best.source,
                reference_type=best.reference_type,
                eb_publish_date=best.eb_publish_date,
                access_date=best.access_date,
            )

    return best
