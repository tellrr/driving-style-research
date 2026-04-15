"""Abstract base class for all scraper sources."""

import hashlib
from abc import ABC, abstractmethod

from models import Article
from storage.db import Database


class BaseSource(ABC):
    name: str = "base"

    def __init__(self, db: Database, delay: float = 1.5):
        self.db = db
        self.delay = delay          # seconds between requests

    @abstractmethod
    def fetch(self, keywords: list[str], max_per_keyword: int = 20) -> list[Article]:
        """Fetch articles matching keywords. Return only new (not yet in DB) articles."""
        ...

    @staticmethod
    def make_id(url_or_doi: str) -> str:
        return hashlib.sha256(url_or_doi.strip().lower().encode()).hexdigest()[:32]
