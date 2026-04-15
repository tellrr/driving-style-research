"""PubMed/Entrez API source — clinical speech therapy and audiology research."""

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
from loguru import logger

from models import Article
from scraper.sources.base import BaseSource
from storage.db import Database

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class PubMedSource(BaseSource):
    name = "pubmed"

    def __init__(self, db: Database, delay: float = 0.5, max_results: int = 20):
        super().__init__(db, delay)
        self.max_results = max_results

    def fetch(self, keywords: list[str], max_per_keyword: int = 20) -> list[Article]:
        all_new: list[Article] = []
        for kw in keywords:
            try:
                articles = self._search(kw, min(max_per_keyword, self.max_results))
                new = [a for a in articles if not self.db.exists(a.id)]
                all_new.extend(new)
                self.db.log_fetch(self.name, kw, len(articles), len(new))
                logger.debug(f"PubMed '{kw[:40]}': {len(articles)} found, {len(new)} new")
                time.sleep(self.delay)
            except Exception as e:
                logger.warning(f"PubMed fetch failed for '{kw}': {e}")
        return all_new

    def _search(self, keyword: str, max_results: int) -> list[Article]:
        # Step 1: get PMIDs
        search_params = {
            "db": "pubmed",
            "term": keyword,
            "retmax": max_results,
            "retmode": "json",
            "sort": "date",
        }
        resp = httpx.get(ESEARCH, params=search_params, timeout=20)
        resp.raise_for_status()
        pmids = resp.json().get("esearchresult", {}).get("idlist", [])
        if not pmids:
            return []

        time.sleep(self.delay)

        # Step 2: fetch abstracts for those PMIDs
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        resp = httpx.get(EFETCH, params=fetch_params, timeout=30)
        resp.raise_for_status()
        return _parse_xml(resp.text)


def _parse_xml(xml_text: str) -> list[Article]:
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for article_el in root.findall(".//PubmedArticle"):
        article = _parse_article(article_el)
        if article:
            articles.append(article)
    return articles


def _parse_article(el: ET.Element) -> Article | None:
    # Title
    title_el = el.find(".//ArticleTitle")
    title = "".join(title_el.itertext()).strip() if title_el is not None else ""
    if not title:
        return None

    # Abstract
    abstract_parts = [
        "".join(a.itertext()).strip()
        for a in el.findall(".//AbstractText")
    ]
    abstract = " ".join(p for p in abstract_parts if p)

    # PMID → canonical URL
    pmid_el = el.find(".//PMID")
    pmid = pmid_el.text.strip() if pmid_el is not None else ""
    if not pmid:
        return None
    source_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

    # DOI
    doi = None
    for id_el in el.findall(".//ArticleId"):
        if id_el.get("IdType") == "doi":
            doi = id_el.text.strip() if id_el.text else None

    # Authors
    authors = []
    for author in el.findall(".//Author")[:5]:
        last = author.findtext("LastName") or ""
        fore = author.findtext("ForeName") or ""
        name = f"{fore} {last}".strip()
        if name:
            authors.append(name)

    # Publication date
    pub_year = el.findtext(".//PubDate/Year") or ""
    pub_month = el.findtext(".//PubDate/Month") or ""
    pub_date = pub_year + (f"-{pub_month}" if pub_month else "")

    return Article(
        id=BaseSource.make_id(source_url),
        title=title,
        source_url=source_url,
        source_type="api_pubmed",
        abstract=abstract,
        authors=authors,
        publication_date=pub_date or None,
        doi=doi,
        date_collected=datetime.now(timezone.utc).isoformat(),
    )
