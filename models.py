"""Shared data models for the AccentResearch pipeline."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Article:
    """Represents a research article or web document in the pipeline."""

    id: str                          # SHA256 of canonical URL or DOI
    title: str
    source_url: str
    source_type: str                 # api_openalex | api_arxiv | api_pubmed | web | github
    abstract: str = ""
    full_text: Optional[str] = None
    authors: list = field(default_factory=list)
    publication_date: Optional[str] = None
    doi: Optional[str] = None

    # Pipeline output fields
    subtopics: list = field(default_factory=list)
    relevance_score: float = 0.0
    summary: Optional[str] = None
    key_findings: list = field(default_factory=list)

    # Lifecycle
    date_collected: str = ""
    status: str = "fetched"          # fetched | filtered_out | categorized | summarized | embedded | error


@dataclass
class SynthesisRun:
    """A cross-paper synthesis report for a subtopic."""

    id: str
    subtopic: str
    run_type: str                    # daily | weekly | full
    content: str
    articles_included: int
    created_at: str
