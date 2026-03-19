"""搜索结果统一数据模型和基类"""
import re
from dataclasses import dataclass, field
from typing import Optional
from abc import ABC, abstractmethod


def _is_cjk(text: str) -> bool:
    return any('\u4e00' <= c <= '\u9fff' for c in text)


def format_author_name(family: str, given: str) -> str:
    """按语言正确拼接作者姓名：中文 '姓名' 无空格，西文 'Given Family'"""
    family = (family or "").strip()
    given = (given or "").strip()
    if not family:
        return given
    if not given:
        return family
    if _is_cjk(family) or _is_cjk(given):
        return family + given
    return f"{given} {family}"


@dataclass
class Paper:
    title: str
    authors: list[str]
    year: Optional[int]
    journal: Optional[str]
    doi: Optional[str]
    abstract: Optional[str]
    citation_count: Optional[int] = None
    url: Optional[str] = None
    source: str = ""  # 数据来源标识

    @property
    def doi_url(self) -> Optional[str]:
        if self.doi:
            return f"https://doi.org/{self.doi}"
        return self.url

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "journal": self.journal,
            "doi": self.doi,
            "doi_url": self.doi_url,
            "abstract": self.abstract,
            "citation_count": self.citation_count,
            "source": self.source,
        }

    def __str__(self) -> str:
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += " et al."
        return f"{authors_str}. {self.title}. {self.journal or 'N/A'}, {self.year or 'N/A'}. DOI: {self.doi or 'N/A'}"


class BaseSearcher(ABC):
    """搜索引擎基类"""

    source_name: str = "unknown"

    @abstractmethod
    def search(self, query: str, year_start: int = 2021, year_end: int = 2026, limit: int = 10) -> list[Paper]:
        ...
