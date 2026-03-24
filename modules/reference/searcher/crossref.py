"""CrossRef API 搜索"""
import requests
from .base import BaseSearcher, Paper, format_author_name
from modules.reference.config import CROSSREF_API, REQUEST_TIMEOUT, REQUEST_HEADERS


class CrossRefSearcher(BaseSearcher):
    source_name = "CrossRef"

    def search(self, query: str, year_start: int = 2021, year_end: int = 2026, limit: int = 10) -> list[Paper]:
        url = f"{CROSSREF_API}/works"
        params = {
            "query": query,
            "rows": limit,
            "filter": f"from-pub-date:{year_start},until-pub-date:{year_end}",
            "sort": "relevance",
            "order": "desc",
            "select": "DOI,title,author,published-print,published-online,container-title,abstract,is-referenced-by-count,volume,issue,page",
        }

        try:
            resp = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[CrossRef] 请求失败: {e}")
            return []

        papers = []
        for item in data.get("message", {}).get("items", []):
            title_list = item.get("title", [])
            title = title_list[0] if title_list else ""

            authors = []
            for a in item.get("author") or []:
                name = format_author_name(a.get("family", ""), a.get("given", ""))
                if name:
                    authors.append(name)

            year = None
            for date_field in ("published-print", "published-online"):
                date_parts = (item.get(date_field) or {}).get("date-parts", [[]])
                if date_parts and date_parts[0]:
                    year = date_parts[0][0]
                    break

            journal_list = item.get("container-title", [])
            journal = journal_list[0] if journal_list else None

            abstract_raw = item.get("abstract", "")
            if abstract_raw:
                import re
                abstract_raw = re.sub(r"<[^>]+>", "", abstract_raw).strip()

            papers.append(Paper(
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                doi=item.get("DOI"),
                abstract=abstract_raw or None,
                citation_count=item.get("is-referenced-by-count"),
                source=self.source_name,
                volume=item.get("volume"),
                issue=item.get("issue"),
                pages=item.get("page"),
            ))

        return papers
