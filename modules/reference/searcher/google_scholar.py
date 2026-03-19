"""Google Scholar 搜索（通过 SerpAPI 或直接请求）"""
import re
import time
import requests
from bs4 import BeautifulSoup
from .base import BaseSearcher, Paper
from modules.reference.config import REQUEST_TIMEOUT


class GoogleScholarSearcher(BaseSearcher):
    source_name = "Google Scholar"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def search(self, query: str, year_start: int = 2021, year_end: int = 2026, limit: int = 10) -> list[Paper]:
        url = "https://scholar.google.com/scholar"
        params = {
            "q": query,
            "as_ylo": year_start,
            "as_yhi": year_end,
            "hl": "zh-CN",
            "num": limit,
        }

        try:
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                print("[Google Scholar] 被限流 (429)")
                return []
            resp.raise_for_status()
        except Exception as e:
            print(f"[Google Scholar] 请求失败: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.select("div.gs_r.gs_or.gs_scl")

        papers = []
        for item in results[:limit]:
            title_tag = item.select_one("h3.gs_rt a")
            if not title_tag:
                title_tag = item.select_one("h3.gs_rt")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            link = title_tag.get("href", "") if title_tag.name == "a" else ""

            info_line = item.select_one("div.gs_a")
            authors, year, journal = [], None, None
            if info_line:
                info_text = info_line.get_text()
                parts = info_text.split(" - ")
                if parts:
                    authors = [a.strip() for a in parts[0].split(",") if a.strip()]
                year_match = re.search(r"(\d{4})", info_text)
                if year_match:
                    year = int(year_match.group(1))
                if len(parts) >= 2:
                    journal = parts[1].strip().rstrip(",").strip()

            abstract_tag = item.select_one("div.gs_rs")
            abstract = abstract_tag.get_text(strip=True) if abstract_tag else None

            papers.append(Paper(
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                doi=None,
                abstract=abstract,
                url=link if link.startswith("http") else None,
                source=self.source_name,
            ))

        return papers
