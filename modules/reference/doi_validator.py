"""DOI 真实性验证模块 — 通过 CrossRef 验证 DOI 是否存在"""
import time
import requests
from modules.reference.config import CROSSREF_API, REQUEST_TIMEOUT
from modules.reference.searcher.base import Paper


class DOIValidator:
    def __init__(self):
        self.cache: dict[str, bool] = {}

    def verify(self, doi: str) -> bool:
        if not doi:
            return False

        doi = doi.strip()
        if doi in self.cache:
            return self.cache[doi]

        try:
            url = f"{CROSSREF_API}/works/{doi}"
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            is_real = resp.status_code == 200
            self.cache[doi] = is_real
            return is_real
        except Exception:
            return False

    def verify_batch(self, papers: list[Paper], remove_invalid: bool = True) -> list[Paper]:
        """批量验证论文 DOI，可选过滤掉无效的"""
        result = []
        for p in papers:
            if not p.doi:
                if not remove_invalid:
                    result.append(p)
                continue

            is_valid = self.verify(p.doi)
            if is_valid:
                result.append(p)
            elif not remove_invalid:
                p.doi = None
                result.append(p)
            else:
                print(f"[DOI验证] 无效DOI已过滤: {p.doi} — {p.title[:40]}")

            time.sleep(0.1)

        return result
