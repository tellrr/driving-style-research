"""Scheduler — coordinates all scraper sources, rotates keywords, rate-limits."""

import json
import random
from pathlib import Path

from loguru import logger

from config.settings import Config, load_subtopics
from models import Article
from scraper.sources.base import BaseSource
from scraper.sources.arxiv import ArXivSource
from scraper.sources.github import GitHubSource
from scraper.sources.openalex import OpenAlexSource
from scraper.sources.pubmed import PubMedSource
from scraper.sources.web import WebSource
from scraper.sources.search import SearchSource
from storage.db import Database


class Scraper:
    """Manages all sources and runs a single fetch cycle."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        sc = config.scraper

        self.sources: list[BaseSource] = [
            OpenAlexSource(db, sc.contact_email, sc.request_delay, sc.openalex_per_page),
            ArXivSource(db, sc.request_delay * 2, sc.arxiv_max_results),
            PubMedSource(db, sc.request_delay, sc.pubmed_max_results),
            WebSource(db, sc.web_delay),
            GitHubSource(
                db,
                delay=sc.github_delay,
                max_results=sc.github_max_results,
                github_token=sc.github_token or None,
            ),
            SearchSource(db, delay=sc.search_delay, max_results=sc.search_max_results),
        ]

        # Load subtopics → keywords from topic_config.md
        self._subtopic_keywords = load_subtopics(config.topic_config_path)
        self._all_keywords = self._build_keyword_pool()
        self._suggested_kw_path = Path(config.data_dir) / "suggested_keywords.json"
        logger.info(
            f"Scraper ready: {len(self.sources)} sources, "
            f"{len(self._subtopic_keywords)} subtopics, "
            f"{len(self._all_keywords)} total keywords"
        )

    def run_cycle(self, keywords_per_source: int = 5) -> list[Article]:
        """
        Run one fetch cycle across all sources.
        Rotates through keywords so long runs cover all subtopics.
        Returns list of newly inserted Article objects.
        """
        # Rotate: pick a random slice of keywords this cycle
        keywords = self._pick_keywords(keywords_per_source)
        logger.info(f"Fetch cycle — {len(keywords)} keywords across {len(self.sources)} sources")

        all_new: list[Article] = []
        for source in self.sources:
            try:
                # Web source ignores keywords and uses feeds; GitHub uses keywords
                kw = [] if source.name == "web" else keywords
                new = source.fetch(kw, max_per_keyword=self.config.scraper.openalex_per_page)
                for article in new:
                    inserted = self.db.insert(article)
                    if inserted:
                        all_new.append(article)
                logger.info(f"  {source.name}: {len(new)} new articles")
            except Exception as e:
                logger.error(f"  {source.name} cycle error: {e}")

        logger.info(f"Cycle complete — {len(all_new)} total new articles")
        return all_new

    def get_subtopic_names(self) -> list[str]:
        return list(self._subtopic_keywords.keys())

    def get_keywords_for_subtopic(self, subtopic: str) -> list[str]:
        return self._subtopic_keywords.get(subtopic, [])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_keyword_pool(self) -> list[str]:
        """Flatten all keywords, deduplicate."""
        seen: set[str] = set()
        pool: list[str] = []
        for kws in self._subtopic_keywords.values():
            for kw in kws:
                kw_lower = kw.lower().strip()
                if kw_lower and kw_lower not in seen:
                    seen.add(kw_lower)
                    pool.append(kw)
        return pool

    def _pick_keywords(self, n: int) -> list[str]:
        """
        Pick n keywords using a 50/50 blend of the static rotating pool and
        the Opus-suggested keywords (from data/suggested_keywords.json).
        If no suggested keywords exist, all n slots use the static pool.
        """
        pool = self._all_keywords
        if not pool:
            return []

        suggested = self._load_suggested_keywords()

        if suggested:
            n_suggested = n // 2
            n_static = n - n_suggested
        else:
            n_static = n
            n_suggested = 0

        # Static pool: rotating cursor
        cursor = int(self.db.get_cursor("scraper", "kw_cursor", "0"))
        static_picks = []
        for i in range(n_static):
            idx = (cursor + i) % len(pool)
            static_picks.append(pool[idx])
        new_cursor = (cursor + n_static) % len(pool)
        self.db.set_cursor("scraper", "kw_cursor", str(new_cursor))

        # Suggested pool: random sample
        suggested_picks = random.sample(suggested, min(n_suggested, len(suggested)))

        return static_picks + suggested_picks

    def _load_suggested_keywords(self) -> list[str]:
        """Load Opus-suggested keywords from the shared JSON file."""
        if not self._suggested_kw_path.exists():
            return []
        try:
            data = json.loads(self._suggested_kw_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(k) for k in data if k]
        except Exception:
            pass
        return []
