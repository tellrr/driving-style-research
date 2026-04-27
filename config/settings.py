"""Runtime configuration for the research pipeline.

Two types of configuration live here:
  1. Technical settings (LLM models, timeouts, scraper rate limits) — set via dataclass fields
  2. Project metadata (goal, research domain, pillars) — loaded from config/topic_config.md

When starting a new project, only config/topic_config.md needs to be edited.
The dataclass defaults in this file are reasonable for most setups.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent

# Load pipeline/.env early so LLMConfig field defaults pick up the variables
load_dotenv(ROOT / "pipeline" / ".env")


# ---------------------------------------------------------------------------
# Sub-configs (technical settings)
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "ollama"))

    # Per-provider model names — set the right one, then just flip LLM_PROVIDER
    pipeline_model_ollama: str = field(default_factory=lambda: os.getenv("PIPELINE_MODEL_OLLAMA", "qwen3.5:4b"))
    pipeline_model_gemini: str = field(default_factory=lambda: os.getenv("PIPELINE_MODEL_GEMINI", "gemini-3.1-flash-lite-preview"))
    pipeline_model_openai: str = field(default_factory=lambda: os.getenv("PIPELINE_MODEL_OPENAI", "gpt-5-mini"))
    pipeline_model_deepseek: str = field(default_factory=lambda: os.getenv("PIPELINE_MODEL_DEEPSEEK", "deepseek-v4-flash"))

    report_model: str = field(default_factory=lambda: os.getenv("REPORT_MODEL", "claude-opus-4-6"))
    embed_model: str = "nomic-embed-text"       # local Ollama embedding model
    base_url: str = "http://localhost:11434"
    timeout: int = 120                          # seconds per LLM call
    temperature: float = 0.1                    # low = consistent structured output

    # Resolved at init — rest of the codebase uses these two unchanged
    pipeline_model: str = field(init=False)
    synthesis_model: str = field(init=False)

    def __post_init__(self):
        model = {
            "gemini": self.pipeline_model_gemini,
            "openai": self.pipeline_model_openai,
            "deepseek": self.pipeline_model_deepseek,
        }.get(self.provider, self.pipeline_model_ollama)
        self.pipeline_model = model
        self.synthesis_model = model


@dataclass
class ScraperConfig:
    openalex_per_page: int = 25
    arxiv_max_results: int = 20
    pubmed_max_results: int = 20
    request_delay: float = 1.5                  # seconds between API calls
    web_delay: float = 3.0                      # seconds between web requests
    github_max_results: int = 10                # repos per keyword
    github_delay: float = 6.0                   # seconds between search calls (unauthenticated: 10/min)
    github_token: str = ""                      # optional PAT — raises rate limit to 30 search req/min
    search_max_results: int = 8                 # DuckDuckGo results per keyword
    search_delay: float = 2.0                   # seconds between DDG queries
    # Used as "mailto" param in OpenAlex polite pool — set this to your email
    contact_email: str = "researcher@example.com"


@dataclass
class PipelineConfig:
    relevance_threshold: float = 0.55           # below this → filtered_out
    max_abstract_chars: int = 2000              # truncate abstract fed to LLM
    max_full_text_chars: int = 6000             # truncate full text fed to LLM
    batch_size: int = 20                        # articles processed per cycle


@dataclass
class OrchestratorConfig:
    cycle_interval_seconds: int = 300           # wait time after each cycle completes
    synthesis_interval_hours: int = 3           # daily synthesis pass interval
    weekly_synthesis_interval_days: int = 7
    max_pipeline_per_cycle: int = 50            # cap LLM calls per cycle


# ---------------------------------------------------------------------------
# Project metadata — loaded from topic_config.md
# ---------------------------------------------------------------------------

@dataclass
class ProjectMeta:
    """Describes the research project. Loaded from config/topic_config.md.

    All fields are used to dynamically build LLM prompts so the pipeline
    is correctly focused on the configured topic rather than the template default.
    """
    name: str = "Research Project"
    goal: str = ""               # ## Project Goal section — used in strategic report prompt
    domain_summary: str = ""     # ## Research Domain section — used in filter/summarizer prompts
    relevant_topics: str = ""    # "Relevant topics include:" line from domain section
    irrelevant_topics: str = ""  # "Irrelevant:" line from domain section
    product_short: str = ""      # First line of goal — used in "app_relevance" summarizer field
    pillars: list[str] = field(default_factory=list)  # ## Pillars — tracked in daily reports


def _extract_md_section(text: str, heading: str) -> str:
    """Extract content between a ## heading and the next ## heading."""
    # Find the heading line (case-insensitive, handles # count variations)
    escaped = re.escape(heading.strip().lstrip("#").strip())
    pattern = re.compile(rf"(?m)^##\s+{escaped}\s*$", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    # Find next ## heading
    next_heading = re.search(r"(?m)^##\s+", text[start:])
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def _extract_inline(text: str, label: str) -> str:
    """Extract the value after a bold label like **Relevant topics include:** ..."""
    pattern = re.compile(
        rf"\*\*{re.escape(label)}\*\*\s*(.*?)(?:\n|$)", re.IGNORECASE
    )
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    # Also try plain (non-bold) label
    pattern2 = re.compile(rf"{re.escape(label)}\s*(.*?)(?:\n|$)", re.IGNORECASE)
    match2 = pattern2.search(text)
    return match2.group(1).strip() if match2 else ""


def load_project_meta(path: Path) -> ProjectMeta:
    """Parse ProjectMeta from the ## Project Goal, ## Research Domain, and ## Pillars
    sections of topic_config.md.  Returns defaults if the file or sections are missing.
    """
    if not path.exists():
        return ProjectMeta()

    text = path.read_text(encoding="utf-8")

    # --- Project name: first # heading ---
    name_match = re.search(r"(?m)^#\s+(.+)$", text)
    name = name_match.group(1).strip() if name_match else "Research Project"
    # Strip "Research Topic Configuration: " prefix if present
    name = re.sub(r"^Research Topic Configuration:\s*", "", name, flags=re.IGNORECASE)

    # --- Project Goal section ---
    goal = _extract_md_section(text, "## Project Goal")

    # First non-empty line = one-liner for product_short
    product_short = ""
    for line in goal.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            product_short = line
            break

    # --- Research Domain section ---
    domain_section = _extract_md_section(text, "## Research Domain")
    # Strip first paragraph as domain_summary (up to blank line or **Relevant** line)
    domain_lines = []
    for line in domain_section.splitlines():
        if line.strip().startswith("**Relevant") or line.strip().startswith("**Irrelevant"):
            break
        domain_lines.append(line)
    domain_summary = " ".join(domain_lines).strip()

    relevant = _extract_inline(domain_section, "Relevant topics include:")
    irrelevant = _extract_inline(domain_section, "Irrelevant:")

    # --- Pillars section ---
    pillars_section = _extract_md_section(text, "## Pillars")
    pillars = []
    for line in pillars_section.splitlines():
        line = line.strip()
        if line.startswith("- "):
            name_part = line[2:].split(":")[0].strip()
            if name_part:
                pillars.append(name_part)

    return ProjectMeta(
        name=name,
        goal=goal,
        domain_summary=domain_summary,
        relevant_topics=relevant,
        irrelevant_topics=irrelevant,
        product_short=product_short,
        pillars=pillars,
    )


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)

    data_dir: Path = field(default_factory=lambda: ROOT / "data")
    reports_dir: Path = field(default_factory=lambda: ROOT / "reports")
    logs_dir: Path = field(default_factory=lambda: ROOT / "logs")
    topic_config_path: Path = field(default_factory=lambda: ROOT / "config" / "topic_config.md")

    def ensure_dirs(self):
        for d in [self.data_dir, self.reports_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# topic_config.md subtopic parser
# ---------------------------------------------------------------------------

def load_subtopics(topic_config_path: Path) -> dict[str, list[str]]:
    """Parse topic_config.md and return {subtopic_name: [keywords]}."""
    text = topic_config_path.read_text(encoding="utf-8")
    subtopics: dict[str, list[str]] = {}

    # Split on "### N." headings
    sections = re.split(r"\n###\s+\d+\.\s+", text)

    for section in sections[1:]:
        lines = section.strip().splitlines()
        if not lines:
            continue
        name = lines[0].strip()

        keywords: list[str] = []
        in_keywords = False
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("**Keywords:**"):
                in_keywords = True
                continue
            if stripped.startswith("**") and in_keywords:
                break
            if in_keywords and stripped.startswith("-"):
                for kw in stripped[1:].split(","):
                    kw = kw.strip()
                    if kw:
                        keywords.append(kw)

        subtopics[name] = keywords

    return subtopics


# ---------------------------------------------------------------------------
# Singletons — import these in other modules
# ---------------------------------------------------------------------------

config = Config()
project_meta = load_project_meta(config.topic_config_path)
