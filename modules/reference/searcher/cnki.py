"""知网 (CNKI) 搜索器 — 集成到 paper-toolbox 的适配层

通过知网 kns8s API 搜索中文学术文献，绕过本地代理直连知网。
需要 cookies.txt（项目根目录）保存知网会话 Cookie。
"""

import html
import json
import logging
import os
import random
import re
import time
import urllib.parse
from pathlib import Path
from typing import List, Optional

import requests
import urllib3
from bs4 import BeautifulSoup, Tag

from .base import BaseSearcher, Paper

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

CNKI_SEARCH_URL = "https://kns.cnki.net/kns8s/brief/grid"
CNKI_REFERER_URL = "https://kns.cnki.net/kns8s/defaultresult/index"
CNKI_ORIGIN = "https://kns.cnki.net"
KUAKU_CODES = "YSTT4HG0,LSTPFY1C,JUP3MUPD,MPMFIG1A,WQ0UVIAA,BLZOG7CK,PWFIRAGL,EMRPGLPA,NLBO1Z6R,NN3FJMUV"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
COOKIE_FILE = PROJECT_ROOT / "cnki_cookies.txt"


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_year(text: str) -> int:
    text = _clean_text(text)
    m = re.search(r"(19|20)\d{2}", text)
    return int(m.group()) if m else 0


class CNKISearcher(BaseSearcher):
    source_name = "CNKI"

    def __init__(self, cookie_path: Optional[str] = None):
        self._session = requests.Session()
        self._session.verify = False
        self._session.proxies = {"http": None, "https": None}
        self._session.trust_env = False
        self._last_request_time: Optional[float] = None

        self._session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Referer": CNKI_REFERER_URL,
            "Origin": CNKI_ORIGIN,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })

        cookie_file = Path(cookie_path) if cookie_path else COOKIE_FILE
        self._load_cookies(cookie_file)

    def _load_cookies(self, cookie_file: Path) -> bool:
        if not cookie_file.exists():
            logger.warning("[CNKI] 未找到 %s，搜索可能失败", cookie_file)
            return False
        try:
            cookie_str = cookie_file.read_text(encoding="utf-8").strip()
            if not cookie_str:
                return False
            for item in cookie_str.split(";"):
                item = item.strip()
                if "=" in item:
                    k, _, v = item.partition("=")
                    self._session.cookies.set(k.strip(), v.strip())
            logger.info("[CNKI] 加载了 Cookie")
            return True
        except Exception as e:
            logger.warning("[CNKI] Cookie 加载失败: %s", e)
            return False

    def _build_query_json(self, keyword: str) -> str:
        query_dict = {
            "Platform": "",
            "Resource": "CROSSDB",
            "Classid": "WD0FTY92",
            "Products": "",
            "QNode": {"QGroup": [{
                "Key": "Subject", "Title": "", "Logic": 0,
                "Items": [{"Field": "SU", "Value": keyword,
                           "Operator": "TOPRANK", "Logic": 0, "Title": "主题"}],
                "ChildItems": [],
            }]},
            "ExScope": 1,
            "SearchType": 2,
            "Rlang": "CHINESE",
            "KuaKuCode": KUAKU_CODES,
            "Expands": {},
            "SearchFrom": 1,
        }
        return urllib.parse.quote(json.dumps(query_dict, ensure_ascii=False))

    def _wait(self):
        if self._last_request_time is not None:
            remaining = 1.2 - (time.monotonic() - self._last_request_time)
            if remaining > 0:
                time.sleep(remaining)

    def _fetch_html(self, keyword: str, page_size: int) -> str:
        self._session.headers["User-Agent"] = random.choice(USER_AGENTS)
        qj = self._build_query_json(keyword)
        aside = urllib.parse.quote(f"主题：{keyword}")
        search_from = urllib.parse.quote("资源范围：总库")
        data = (
            f"boolSearch=true&QueryJson={qj}"
            f"&pageNum=1&pageSize={page_size}"
            f"&sortField=&sortType=&dstyle=listmode"
            f"&productStr=&aside={aside}"
            f"&searchFrom={search_from}"
            f"&subject=&language=&uniplatform=&CurPage=1"
        )
        self._wait()
        for attempt in range(3):
            try:
                resp = self._session.post(
                    CNKI_SEARCH_URL,
                    data=data.encode("utf-8"),
                    timeout=20,
                )
                self._last_request_time = time.monotonic()
                if resp.status_code == 200:
                    return resp.text
                logger.warning("[CNKI] 状态码 %d (尝试 %d/3)", resp.status_code, attempt + 1)
            except Exception as e:
                logger.warning("[CNKI] 请求异常 (尝试 %d/3): %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(2 ** attempt)
        return ""

    def _parse_html(self, html_content: str) -> List[Paper]:
        if not html_content:
            return []
        try:
            soup = BeautifulSoup(html_content, "lxml")
        except Exception:
            return []

        table = None
        for sel in ["table.result-table-list", "table.GridTableContent", "table#gridTable"]:
            table = soup.select_one(sel)
            if table:
                break
        if not table:
            for t in soup.find_all("table"):
                tbody = t.find("tbody")
                if tbody and tbody.find("tr"):
                    table = t
                    break
        if not table:
            return []

        tbody = table.find("tbody")
        rows = (tbody or table).find_all("tr")
        rows = [r for r in rows if not r.find("th") and r.find_all("td")]

        papers = []
        for row in rows:
            p = self._parse_row(row)
            if p:
                papers.append(p)
        return papers

    def _parse_row(self, row: Tag) -> Optional[Paper]:
        tds = row.find_all("td")
        if not tds:
            return None

        title = ""
        for td in tds:
            if "name" in td.get("class", []):
                link = td.find("a")
                title = _clean_text(link.get_text()) if link else _clean_text(td.get_text())
                break
        if not title:
            for td in tds[1:]:
                link = td.find("a")
                if link:
                    title = _clean_text(link.get_text())
                    if title:
                        break

        if not title:
            return None

        authors = []
        for td in tds:
            if "author" in td.get("class", []):
                authors = self._parse_authors(td)
                break
        if not authors and len(tds) >= 4:
            authors = self._parse_authors(tds[2])

        journal = ""
        for td in tds:
            if "source" in td.get("class", []):
                link = td.find("a")
                journal = _clean_text(link.get_text()) if link else _clean_text(td.get_text())
                break
        if not journal and len(tds) >= 5:
            td = tds[3]
            link = td.find("a")
            journal = _clean_text(link.get_text()) if link else _clean_text(td.get_text())

        year = 0
        for td in tds:
            if "date" in td.get("class", []):
                year = _parse_year(td.get_text())
                break
        if not year:
            for td in tds:
                y = _parse_year(td.get_text())
                if y:
                    year = y
                    break

        return Paper(
            title=title,
            authors=authors,
            year=year if year else None,
            journal=journal or None,
            doi=None,
            abstract=None,
            citation_count=None,
            source=self.source_name,
        )

    def _parse_authors(self, td: Tag) -> List[str]:
        links = td.find_all("a")
        if links:
            names = [_clean_text(a.get_text()) for a in links]
            return [n for n in names if n]
        text = _clean_text(td.get_text())
        if not text:
            return []
        if ";" in text or "；" in text:
            parts = re.split(r"[;；]", text)
        elif "," in text or "，" in text:
            parts = re.split(r"[,，]", text)
        else:
            parts = [text]
        return [_clean_text(p) for p in parts if _clean_text(p)]

    def search(self, query: str, year_start: int = 2021, year_end: int = 2026, limit: int = 10) -> List[Paper]:
        logger.info("[CNKI] 搜索: '%s', %d-%d, limit=%d", query, year_start, year_end, limit)
        html_content = self._fetch_html(query, page_size=min(limit * 2, 50))
        if not html_content:
            logger.warning("[CNKI] 未获取到 HTML")
            return []

        papers = self._parse_html(html_content)
        if year_start or year_end:
            papers = [
                p for p in papers
                if p.year and year_start <= p.year <= year_end
            ]

        logger.info("[CNKI] 解析到 %d 篇论文", len(papers))
        return papers[:limit]
