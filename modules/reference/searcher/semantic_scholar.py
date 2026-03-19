"""Semantic Scholar API 搜索"""
import time
import requests
from .base import BaseSearcher, Paper
from modules.reference.config import SEMANTIC_SCHOLAR_API, REQUEST_TIMEOUT


class SemanticScholarSearcher(BaseSearcher):
    source_name = "Semantic Scholar"

    def search(self, query: str, year_start: int = 2021, year_end: int = 2026, limit: int = 10) -> list[Paper]:
        url = f"{SEMANTIC_SCHOLAR_API}/paper/search"
        params = {
            "query": query,
            "year": f"{year_start}-{year_end}",
            "limit": limit,
            "fields": "title,authors,year,venue,externalIds,abstract,citationCount,url",
        }

        data = None
        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 429:
                    wait = 5 * (attempt + 1) + 5
                    print(f"[Semantic Scholar] 限流，等待 {wait}s 后重试 ({attempt+1}/3)")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.exceptions.HTTPError:
                if attempt < 2:
                    time.sleep(2)
                    continue
                print(f"[Semantic Scholar] 多次重试后仍然失败")
                return []
            except Exception as e:
                print(f"[Semantic Scholar] 请求失败: {e}")
                return []

        if data is None:
            print("[Semantic Scholar] 所有重试均失败")
            return []

        papers = []
        for item in data.get("data", []):
            doi = None
            ext_ids = item.get("externalIds") or {}
            if isinstance(ext_ids, dict):
                doi = ext_ids.get("DOI")

            authors = []
            for a in item.get("authors") or []:
                if isinstance(a, dict) and a.get("name"):
                    authors.append(a["name"])

            papers.append(Paper(
                title=item.get("title", ""),
                authors=authors,
                year=item.get("year"),
                journal=item.get("venue") or None,
                doi=doi,
                abstract=item.get("abstract"),
                citation_count=item.get("citationCount"),
                url=item.get("url"),
                source=self.source_name,
            ))

        return papers
