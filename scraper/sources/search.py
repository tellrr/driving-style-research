"""Public web search source — uses DuckDuckGo to find pages not in academic DBs."""

import time
from datetime import datetime, timezone

from ddgs import DDGS
from loguru import logger

from models import Article
from scraper.sources.base import BaseSource
from storage.db import Database


class SearchSource(BaseSource):
    name = "search"

    def __init__(
        self,
        db: Database,
        delay: float = 2.0,
        max_results: int = 8,
    ):
        super().__init__(db, delay)
        self.max_results = max_results

    def fetch(self, keywords: list[str], max_per_keyword: int = 8) -> list[Article]:
        all_new: list[Article] = []
        limit = min(max_per_keyword, self.max_results)
        with DDGS() as ddgs:
            for kw in keywords:
                try:
                    articles = self._search(ddgs, kw, limit)
                    new = [a for a in articles if not self.db.exists(a.id)]
                    all_new.extend(new)
                    self.db.log_fetch(self.name, kw, len(articles), len(new))
                    logger.debug(f"Search '{kw[:40]}': {len(articles)} results, {len(new)} new")
                    time.sleep(self.delay)
                except Exception as e:
                    logger.warning(f"Search fetch failed for '{kw}': {e}")
        return all_new

    def _search(self, ddgs: DDGS, keyword: str, limit: int) -> list[Article]:
        results = ddgs.text(keyword, max_results=limit)
        articles: list[Article] = []
        for r in results or []:
            url = r.get("href") or r.get("url", "")
            if not url:
                continue
            title = (r.get("title") or url).strip()
            abstract = (r.get("body") or "").strip()
            article = Article(
                id=BaseSource.make_id(url),
                title=title,
                source_url=url,
                source_type="search",
                abstract=abstract,
                date_collected=datetime.now(timezone.utc).isoformat(),
            )
            articles.append(article)
        return articles
