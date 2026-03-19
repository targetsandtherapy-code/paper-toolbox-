"""OpenAlex API 搜索"""
import time
import requests
from .base import BaseSearcher, Paper, _is_cjk
from modules.reference.config import OPENALEX_API, REQUEST_TIMEOUT


class OpenAlexSearcher(BaseSearcher):
    source_name = "OpenAlex"

    def search(self, query: str, year_start: int = 2021, year_end: int = 2026, limit: int = 10) -> list[Paper]:
        url = f"{OPENALEX_API}/works"
        params = {
            "search": query,
            "filter": f"publication_year:{year_start}-{year_end}",
            "per_page": limit,
            "sort": "relevance_score:desc",
            "mailto": "test@example.com",
        }

        data = None
        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                if attempt < 2:
                    print(f"[OpenAlex] 连接异常，{2*(attempt+1)}s 后重试 ({attempt+1}/3)")
                    time.sleep(2 * (attempt + 1))
                    continue
                print(f"[OpenAlex] 多次重试后仍然失败: {e}")
                return []
            except Exception as e:
                print(f"[OpenAlex] 请求失败: {e}")
                return []

        if data is None:
            return []

        papers = []
        for item in data.get("results", []):
            authors = []
            for authorship in item.get("authorships") or []:
                author_obj = authorship.get("author") or {}
                name = author_obj.get("display_name", "")
                if name and _is_cjk(name):
                    parts = name.split()
                    if len(parts) == 2 and not _is_cjk(parts[0]) == _is_cjk(parts[1]):
                        name = "".join(reversed(parts))
                    else:
                        name = "".join(parts)
                if name:
                    authors.append(name)

            doi_raw = item.get("doi") or ""
            doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None

            journal = None
            locations = item.get("locations") or []
            for loc in locations:
                src = loc.get("source") or {}
                if src.get("display_name"):
                    journal = src["display_name"]
                    break

            abstract_index = item.get("abstract_inverted_index")
            abstract = self._reconstruct_abstract(abstract_index) if abstract_index else None

            papers.append(Paper(
                title=item.get("display_name") or item.get("title", ""),
                authors=authors,
                year=item.get("publication_year"),
                journal=journal,
                doi=doi,
                abstract=abstract,
                citation_count=item.get("cited_by_count"),
                url=item.get("id"),
                source=self.source_name,
            ))

        return papers

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict) -> str:
        """OpenAlex 的摘要是倒排索引格式，需要重建为正常文本"""
        if not inverted_index:
            return ""
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in word_positions)
