"""PubMed (NCBI E-utilities) 搜索 — 生物医学文献权威数据库"""
import time
import requests
import xml.etree.ElementTree as ET
from .base import BaseSearcher, Paper, format_author_name
from modules.reference.config import REQUEST_TIMEOUT


class PubMedSearcher(BaseSearcher):
    source_name = "PubMed"

    SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def search(self, query: str, year_start: int = 2021, year_end: int = 2026, limit: int = 10) -> list[Paper]:
        # Step 1: 搜索获取 PubMed ID 列表
        search_params = {
            "db": "pubmed",
            "term": f"{query} AND {year_start}:{year_end}[dp]",
            "retmax": limit,
            "sort": "relevance",
            "retmode": "json",
        }

        try:
            resp = requests.get(self.SEARCH_URL, params=search_params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[PubMed] 搜索失败: {e}")
            return []

        id_list = data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        time.sleep(0.5)

        # Step 2: 获取论文详细信息
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "rettype": "xml",
            "retmode": "xml",
        }

        try:
            resp = requests.get(self.FETCH_URL, params=fetch_params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            print(f"[PubMed] 获取详情失败: {e}")
            return []

        return self._parse_xml(resp.text)

    def _parse_xml(self, xml_text: str) -> list[Paper]:
        papers = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"[PubMed] XML 解析失败: {e}")
            return []

        for article in root.findall(".//PubmedArticle"):
            medline = article.find(".//MedlineCitation")
            if medline is None:
                continue

            article_elem = medline.find(".//Article")
            if article_elem is None:
                continue

            title_elem = article_elem.find(".//ArticleTitle")
            title = self._get_text(title_elem)

            authors = []
            for author in article_elem.findall(".//Author"):
                last = self._get_text(author.find("LastName"))
                fore = self._get_text(author.find("ForeName"))
                name = format_author_name(last, fore)
                if name:
                    authors.append(name)

            journal_elem = article_elem.find(".//Journal")
            journal = None
            if journal_elem is not None:
                journal_title = journal_elem.find(".//Title")
                if journal_title is None:
                    journal_title = journal_elem.find(".//ISOAbbreviation")
                journal = self._get_text(journal_title)

            year = None
            pub_date = article_elem.find(".//Journal/JournalIssue/PubDate")
            if pub_date is not None:
                year_elem = pub_date.find("Year")
                if year_elem is not None and year_elem.text:
                    try:
                        year = int(year_elem.text)
                    except ValueError:
                        pass

            doi = None
            for eid in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if eid.get("IdType") == "doi":
                    doi = eid.text
                    break

            pmid = None
            pmid_elem = medline.find(".//PMID")
            if pmid_elem is not None:
                pmid = pmid_elem.text

            abstract_parts = []
            for abs_text in article_elem.findall(".//Abstract/AbstractText"):
                text = self._get_text(abs_text)
                if text:
                    label = abs_text.get("Label", "")
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
            abstract = " ".join(abstract_parts) if abstract_parts else None

            papers.append(Paper(
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                doi=doi,
                abstract=abstract,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                source=self.source_name,
            ))

        return papers

    @staticmethod
    def _get_text(elem) -> str:
        if elem is None:
            return ""
        return "".join(elem.itertext()).strip()
