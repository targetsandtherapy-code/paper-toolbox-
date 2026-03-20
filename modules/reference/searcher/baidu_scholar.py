"""百度学术搜索（爬虫）"""
import requests
from bs4 import BeautifulSoup
from .base import BaseSearcher, Paper
from modules.reference.config import REQUEST_TIMEOUT

# 主流程已不调用本模块；保留类供自行实验。URL 不再写入根 config。
BAIDU_SCHOLAR_SEARCH_URL = "https://xueshu.baidu.com/s"


class BaiduScholarSearcher(BaseSearcher):
    source_name = "百度学术"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://xueshu.baidu.com/",
    }

    def search(self, query: str, year_start: int = 2021, year_end: int = 2026, limit: int = 10) -> list[Paper]:
        session = requests.Session()
        # 先访问首页获取 cookie
        try:
            session.get("https://xueshu.baidu.com/", headers=self.HEADERS, timeout=REQUEST_TIMEOUT)
        except Exception:
            pass

        params = {
            "wd": query,
            "ie": "utf-8",
            "sc_as_para": f"sc_filter_year_start={year_start}&sc_filter_year_end={year_end}",
        }

        try:
            resp = session.get(
                BAIDU_SCHOLAR_SEARCH_URL,
                params=params,
                headers=self.HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            resp.encoding = "utf-8"
        except Exception as e:
            print(f"[百度学术] 请求失败 (status={getattr(e, 'response', None) and e.response.status_code}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        result_items = soup.select("div.sc_content")

        papers = []
        for item in result_items[:limit]:
            title_tag = item.select_one("h3 a")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            url = title_tag.get("href", "")

            author_tags = item.select("span.sc_author span a") or item.select("div.sc_info span a")
            authors = [a.get_text(strip=True) for a in author_tags]

            info_spans = item.select("div.sc_info span")
            year = None
            journal = None
            for span in info_spans:
                text = span.get_text(strip=True)
                if text.isdigit() and len(text) == 4:
                    year = int(text)
                elif not journal and len(text) > 1 and not text.isdigit():
                    has_link = span.select_one("a")
                    if has_link:
                        journal = has_link.get_text(strip=True)

            abstract_tag = item.select_one("div.c_abstract") or item.select_one("div.sc_abstract")
            abstract = abstract_tag.get_text(strip=True) if abstract_tag else None

            doi = None
            doi_tag = item.select_one("a[href*='doi.org']")
            if doi_tag:
                href = doi_tag.get("href", "")
                if "doi.org/" in href:
                    doi = href.split("doi.org/")[-1]

            papers.append(Paper(
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                doi=doi,
                abstract=abstract,
                url=url if url.startswith("http") else None,
                source=self.source_name,
            ))

        return papers
