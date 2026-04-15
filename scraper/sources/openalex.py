"""OpenAlex API source — free, no key required, 200M+ papers."""

import time
from datetime import datetime, timezone

import httpx
from loguru import logger

from models import Article
from scraper.sources.base import BaseSource
from storage.db import Database

BASE_URL = "https://api.openalex.org/works"


class OpenAlexSource(BaseSource):
    name = "openalex"

    def __init__(self, db: Database, contact_email: str, delay: float = 1.5, per_page: int = 25):
        super().__init__(db, delay)
        self.contact_email = contact_email
        self.per_page = per_page

    def fetch(self, keywords: list[str], max_per_keyword: int = 25) -> list[Article]:
        all_new: list[Article] = []
        for kw in keywords:
            try:
                articles = self._search(kw, max_per_keyword)
                new = [a for a in articles if not self.db.exists(a.id)]
                all_new.extend(new)
                self.db.log_fetch(self.name, kw, len(articles), len(new))
                logger.debug(f"OpenAlex '{kw[:40]}': {len(articles)} found, {len(new)} new")
                time.sleep(self.delay)
            except Exception as e:
                logger.warning(f"OpenAlex fetch failed for '{kw}': {e}")
        return all_new

    def _search(self, keyword: str, max_results: int) -> list[Article]:
        params = {
            "search": keyword,
            "per-page": min(max_results, self.per_page),
            "filter": "type:article",
            "select": "id,title,abstract_inverted_index,authorships,publication_date,doi,primary_location,open_access",
            "mailto": self.contact_email,
        }
        resp = httpx.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        articles = []
        for item in results:
            article = _parse_work(item)
            if article:
                articles.append(article)
        return articles


def _parse_work(item: dict) -> Article | None:
    title = (item.get("title") or "").strip()
    if not title:
        return None

    # Reconstruct abstract from inverted index
    abstract = _decode_abstract(item.get("abstract_inverted_index"))

    # Prefer DOI as canonical ID, fall back to OpenAlex ID
    doi = item.get("doi")
    openalex_id = item.get("id", "")
    canonical = doi or openalex_id
    if not canonical:
        return None

    # Source URL — prefer open access PDF/landing page
    oa = item.get("open_access", {})
    source_url = oa.get("oa_url") or ""
    if not source_url:
        loc = item.get("primary_location") or {}
        source_url = loc.get("landing_page_url") or doi or openalex_id

    authors = [
        a.get("author", {}).get("display_name", "")
        for a in item.get("authorships", [])[:5]
        if a.get("author", {}).get("display_name")
    ]

    return Article(
        id=BaseSource.make_id(canonical),
        title=title,
        source_url=source_url,
        source_type="api_openalex",
        abstract=abstract,
        authors=authors,
        publication_date=item.get("publication_date"),
        doi=doi,
        date_collected=datetime.now(timezone.utc).isoformat(),
    )


def _decode_abstract(inverted_index: dict | None) -> str:
    """Reconstruct abstract text from OpenAlex inverted index format."""
    if not inverted_index:
        return ""
    try:
        positions: list[tuple[int, str]] = []
        for word, pos_list in inverted_index.items():
            for pos in pos_list:
                positions.append((pos, word))
        positions.sort()
        return " ".join(word for _, word in positions)
    except Exception:
        return ""
