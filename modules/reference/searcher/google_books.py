"""Google Books API 搜索（免费、无需 API key），用于 M 类型专著/教材。"""
from __future__ import annotations

import re
from typing import Optional

import requests

from .base import Paper

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"


def _extract_year(date_str: str) -> Optional[int]:
    m = re.match(r"(\d{4})", date_str or "")
    return int(m.group(1)) if m else None


def search_books(
    query: str,
    max_results: int = 5,
    lang_restrict: str = "",
) -> list[Paper]:
    """搜索 Google Books，返回 Paper 列表（reference_type=M）。"""
    params = {
        "q": query,
        "maxResults": min(max_results, 10),
        "printType": "books",
    }
    if lang_restrict:
        params["langRestrict"] = lang_restrict

    try:
        resp = requests.get(GOOGLE_BOOKS_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[GoogleBooks] 请求失败: {e}")
        return []

    items = data.get("items", [])
    papers: list[Paper] = []

    for item in items[:max_results]:
        info = item.get("volumeInfo", {})
        title = info.get("title", "")
        if not title:
            continue

        subtitle = info.get("subtitle", "")
        if subtitle:
            title = f"{title}: {subtitle}"

        authors = info.get("authors", [])
        publisher = info.get("publisher", "")
        year = _extract_year(info.get("publishedDate", ""))

        identifiers = info.get("industryIdentifiers", [])
        isbn = ""
        for ident in identifiers:
            if ident.get("type") in ("ISBN_13", "ISBN_10"):
                isbn = ident.get("identifier", "")
                break

        papers.append(Paper(
            title=title,
            authors=authors,
            year=year,
            journal=publisher or None,
            doi=None,
            abstract=info.get("description", "")[:300] if info.get("description") else None,
            citation_count=None,
            url=info.get("infoLink") or info.get("canonicalVolumeLink") or None,
            source="google_books",
            reference_type="M",
        ))

    return papers
