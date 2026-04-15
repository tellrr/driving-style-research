"""Web scraper source — fetches articles from explicit URL lists and RSS feeds."""

import time
from datetime import datetime, timezone

import feedparser
from loguru import logger

from models import Article
from pipeline.cleaner import extract_from_url
from scraper.sources.base import BaseSource
from storage.db import Database

# Curated RSS/Atom feeds and seed URLs relevant to the research topics
DEFAULT_FEEDS = [
    "https://jasa.asa.pub/rss/xml",                          # JASA
    "https://www.sciencedirect.com/journal/journal-of-phonetics/rss",
    "https://feeds.feedburner.com/LanguageLog",               # Language Log blog
]

DEFAULT_SEED_URLS: list[str] = [
    # Add specific article URLs here for one-off ingestion
]


class WebSource(BaseSource):
    name = "web"

    def __init__(
        self,
        db: Database,
        delay: float = 3.0,
        feeds: list[str] | None = None,
        seed_urls: list[str] | None = None,
    ):
        super().__init__(db, delay)
        self.feeds = feeds if feeds is not None else DEFAULT_FEEDS
        self.seed_urls = seed_urls if seed_urls is not None else DEFAULT_SEED_URLS

    def fetch(self, keywords: list[str], max_per_keyword: int = 0) -> list[Article]:
        """Fetch from RSS feeds and explicit seed URLs (keywords unused for web source)."""
        all_new: list[Article] = []

        # RSS feeds
        for feed_url in self.feeds:
            try:
                articles = self._fetch_feed(feed_url)
                new = [a for a in articles if not self.db.exists(a.id)]
                all_new.extend(new)
                logger.debug(f"Feed '{feed_url[:60]}': {len(articles)} entries, {len(new)} new")
                time.sleep(self.delay)
            except Exception as e:
                logger.warning(f"Feed fetch failed '{feed_url}': {e}")

        # Explicit seed URLs
        for url in self.seed_urls:
            try:
                article = self._fetch_url(url)
                if article and not self.db.exists(article.id):
                    all_new.append(article)
                time.sleep(self.delay)
            except Exception as e:
                logger.warning(f"URL fetch failed '{url}': {e}")

        return all_new

    def _fetch_feed(self, feed_url: str) -> list[Article]:
        feed = feedparser.parse(feed_url)
        articles = []
        for entry in feed.entries[:20]:
            url = entry.get("link") or entry.get("id")
            if not url:
                continue
            title = entry.get("title", "").strip()
            abstract = entry.get("summary", "").strip()
            pub_date = entry.get("published", "")[:10] if entry.get("published") else ""
            article = Article(
                id=BaseSource.make_id(url),
                title=title or url,
                source_url=url,
                source_type="web",
                abstract=abstract,
                publication_date=pub_date or None,
                date_collected=datetime.now(timezone.utc).isoformat(),
            )
            articles.append(article)
        return articles

    def _fetch_url(self, url: str) -> Article | None:
        full_text = extract_from_url(url)
        if not full_text:
            return None
        # Use first line as title approximation
        first_line = full_text.splitlines()[0][:200] if full_text else url
        return Article(
            id=BaseSource.make_id(url),
            title=first_line,
            source_url=url,
            source_type="web",
            full_text=full_text,
            date_collected=datetime.now(timezone.utc).isoformat(),
        )
