"""GitHub repository source — searches public repos by keyword, fetches README.md content."""

import time
from datetime import datetime, timezone

import httpx
from loguru import logger

from models import Article
from scraper.sources.base import BaseSource
from storage.db import Database

SEARCH_URL = "https://api.github.com/search/repositories"
README_URL = "https://api.github.com/repos/{full_name}/readme"

# GitHub unauthenticated: 10 req/min search, 60 req/min other.
# We stay well under by respecting self.delay between calls.
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "accent-research-bot",
}


class GitHubSource(BaseSource):
    name = "github"

    def __init__(
        self,
        db: Database,
        delay: float = 6.0,   # 10 search req/min unauthenticated → ~6s safe
        max_results: int = 10,
        github_token: str | None = None,
    ):
        super().__init__(db, delay)
        self.max_results = max_results
        self.headers = dict(HEADERS)
        if github_token:
            self.headers["Authorization"] = f"Bearer {github_token}"

    def fetch(self, keywords: list[str], max_per_keyword: int = 10) -> list[Article]:
        all_new: list[Article] = []
        limit = min(max_per_keyword, self.max_results)
        for kw in keywords:
            try:
                articles = self._search(kw, limit)
                new = [a for a in articles if not self.db.exists(a.id)]
                all_new.extend(new)
                self.db.log_fetch(self.name, kw, len(articles), len(new))
                logger.debug(f"GitHub '{kw[:40]}': {len(articles)} repos, {len(new)} new")
                time.sleep(self.delay)
            except Exception as e:
                logger.warning(f"GitHub fetch failed for '{kw}': {e}")
        return all_new

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _search(self, keyword: str, limit: int) -> list[Article]:
        params = {
            "q": keyword,
            "sort": "stars",
            "order": "desc",
            "per_page": limit,
        }
        resp = httpx.get(SEARCH_URL, params=params, headers=self.headers, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("items", [])

        articles: list[Article] = []
        for item in items:
            article = self._repo_to_article(item)
            if article:
                articles.append(article)
            time.sleep(1.0)  # brief pause between README fetches
        return articles

    def _repo_to_article(self, repo: dict) -> Article | None:
        full_name: str = repo.get("full_name", "")
        html_url: str = repo.get("html_url", "")
        if not html_url:
            return None

        title = repo.get("name", full_name)
        description = repo.get("description") or ""
        stars: int = repo.get("stargazers_count", 0)
        pushed_at: str = (repo.get("pushed_at") or "")[:10]

        readme_text = self._fetch_readme(full_name)

        # Use description as abstract; README as full_text
        abstract = description
        if stars:
            abstract = f"[{stars} stars] {description}".strip()

        return Article(
            id=BaseSource.make_id(html_url),
            title=title,
            source_url=html_url,
            source_type="github",
            abstract=abstract,
            full_text=readme_text or None,
            authors=[repo.get("owner", {}).get("login", "")] if repo.get("owner") else [],
            publication_date=pushed_at or None,
            date_collected=datetime.now(timezone.utc).isoformat(),
        )

    def _fetch_readme(self, full_name: str) -> str:
        """Fetch decoded README text for a repo. Returns empty string on failure."""
        url = README_URL.format(full_name=full_name)
        try:
            resp = httpx.get(
                url,
                headers={**self.headers, "Accept": "application/vnd.github.raw+json"},
                timeout=20,
            )
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.debug(f"README fetch failed for '{full_name}': {e}")
            return ""
