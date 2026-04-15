"""arXiv API source — CS/NLP/speech preprints, free, no key required."""

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
from loguru import logger

from models import Article
from scraper.sources.base import BaseSource
from storage.db import Database

BASE_URL = "https://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArXivSource(BaseSource):
    name = "arxiv"

    def __init__(self, db: Database, delay: float = 3.0, max_results: int = 20):
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
                logger.debug(f"arXiv '{kw[:40]}': {len(articles)} found, {len(new)} new")
                time.sleep(self.delay)
            except Exception as e:
                logger.warning(f"arXiv fetch failed for '{kw}': {e}")
        return all_new

    def _search(self, keyword: str, max_results: int) -> list[Article]:
        # arXiv search: title+abstract search
        query = f"ti:{keyword} OR abs:{keyword}"
        params = {
            "search_query": query,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        resp = httpx.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        return _parse_feed(resp.text)


def _parse_feed(xml_text: str) -> list[Article]:
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for entry in root.findall("atom:entry", NS):
        article = _parse_entry(entry)
        if article:
            articles.append(article)
    return articles


def _parse_entry(entry: ET.Element) -> Article | None:
    title_el = entry.find("atom:title", NS)
    summary_el = entry.find("atom:summary", NS)
    if title_el is None:
        return None

    title = (title_el.text or "").replace("\n", " ").strip()
    abstract = (summary_el.text or "").replace("\n", " ").strip() if summary_el else ""

    # Canonical arXiv URL
    source_url = ""
    arxiv_id = ""
    for link in entry.findall("atom:link", NS):
        rel = link.get("rel", "")
        href = link.get("href", "")
        if rel == "alternate":
            source_url = href
        if not arxiv_id and "arxiv.org/abs/" in href:
            arxiv_id = href

    if not source_url:
        source_url = arxiv_id
    if not source_url:
        return None

    authors = []
    for author in entry.findall("atom:author", NS)[:5]:
        name_el = author.find("atom:name", NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    pub_date = ""
    pub_el = entry.find("atom:published", NS)
    if pub_el is not None and pub_el.text:
        pub_date = pub_el.text[:10]

    return Article(
        id=BaseSource.make_id(source_url),
        title=title,
        source_url=source_url,
        source_type="api_arxiv",
        abstract=abstract,
        authors=authors,
        publication_date=pub_date,
        date_collected=datetime.now(timezone.utc).isoformat(),
    )
