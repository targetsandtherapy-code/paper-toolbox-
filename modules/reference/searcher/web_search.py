"""通用网页搜索（DuckDuckGo），用于政策文件 [R/EB] 和学术库搜不到的文献。"""
from __future__ import annotations

import re
import time
from typing import Optional

from .base import Paper

_ACCESS_DATE = time.strftime("%Y-%m-%d")


def _extract_year_from_text(text: str) -> Optional[int]:
    m = re.search(r"(19|20)\d{2}", text or "")
    return int(m.group(0)) if m else None


def _extract_date_from_text(text: str) -> str:
    m = re.search(r"((?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2})", text or "")
    if m:
        return m.group(1).replace("/", "-")
    return ""


def search_policy_web(
    doc_name: str,
    max_results: int = 5,
    site_restrict: str = "",
) -> list[Paper]:
    """用 DuckDuckGo 搜索政策文件，返回 Paper 列表（reference_type=EB/OL）。

    不使用 site: 限制（中文搜索下效果差），但对结果按 gov.cn 域名优先排序。
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        print("[WebSearch] duckduckgo-search 未安装，跳过")
        return []

    query = doc_name
    if site_restrict:
        query = f"{doc_name} site:{site_restrict}"

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                keywords=query,
                max_results=max_results,
            ))
    except Exception as e:
        print(f"[WebSearch] DuckDuckGo 搜索失败: {e}")
        return []

    papers: list[Paper] = []
    for r in results:
        title = r.get("title", "").strip()
        url = r.get("href", "").strip()
        snippet = r.get("body", "")
        if not title or not url:
            continue

        year = _extract_year_from_text(title) or _extract_year_from_text(snippet)
        pub_date = _extract_date_from_text(title) or _extract_date_from_text(snippet)

        issuer = ""
        if "gov.cn" in url:
            if "国务院" in title or "中共中央" in title:
                issuer = "中共中央 国务院"
            elif "卫生" in title or "卫健" in title:
                issuer = "国家卫生健康委员会"
            elif "教育部" in title:
                issuer = "教育部"

        papers.append(Paper(
            title=title,
            authors=[issuer] if issuer else [],
            year=year,
            journal=None,
            doi=None,
            abstract=snippet[:200] if snippet else None,
            citation_count=None,
            url=url,
            source="duckduckgo",
            reference_type="EB/OL",
            eb_publish_date=pub_date or None,
            access_date=_ACCESS_DATE,
        ))

    # gov.cn 结果排前面
    papers.sort(key=lambda p: (0 if "gov.cn" in (p.url or "") else 1))
    return papers


def search_web_general(
    query: str,
    max_results: int = 5,
) -> list[Paper]:
    """通用网页搜索（无 site 限制），用于 EB 类网络资源。"""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                keywords=query,
                max_results=max_results,
            ))
    except Exception as e:
        print(f"[WebSearch] DuckDuckGo 搜索失败: {e}")
        return []

    papers: list[Paper] = []
    for r in results:
        title = r.get("title", "").strip()
        url = r.get("href", "").strip()
        snippet = r.get("body", "")
        if not title or not url:
            continue

        year = _extract_year_from_text(title) or _extract_year_from_text(snippet)
        papers.append(Paper(
            title=title,
            authors=[],
            year=year,
            journal=None,
            doi=None,
            abstract=snippet[:200] if snippet else None,
            citation_count=None,
            url=url,
            source="duckduckgo",
            reference_type="EB/OL",
            eb_publish_date=None,
            access_date=_ACCESS_DATE,
        ))

    return papers
