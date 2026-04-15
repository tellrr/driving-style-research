"""
Strategic daily synthesis using Claude Opus 4.6.

Called by the orchestrator after the first scraping cycle that completes after 3 AM.
Reads all processed articles since the last strategic report, reads the previous
report for continuity, and produces:
  - Progress assessment per configured pillar (defined in config/topic_config.md)
  - Suggested new search keywords (written to data/suggested_keywords.json)

The report goal, pillars, and domain are all read from config/topic_config.md —
no changes to this file are required when setting up a new research project.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from config.settings import project_meta
from models import Article
from pipeline.stats_tracker import record_snapshot
from pipeline.stats_generator import generate_stats_html
from storage.db import Database

ROOT = Path(__file__).parent.parent
STRATEGIC_REPORTS_DIR = ROOT / "reports" / "strategic"
SUGGESTED_KW_PATH = ROOT / "data" / "suggested_keywords.json"
ENV_PATH = Path(__file__).parent / ".env"

SYSTEM = """You are a strategic research analyst guiding the development of a novel product
or research initiative. You synthesize academic findings into concise, actionable progress
reports. Be specific: cite individual papers by title and URL where relevant. Identify gaps
clearly. Format your output in well-structured markdown."""

MAX_ARTICLES_TO_INCLUDE = 80   # cap to control token cost
MAX_ABSTRACT_CHARS = 400       # per article in the prompt


def _build_pillar_table_rows() -> str:
    """Build the pillar table rows for the USER_TEMPLATE from configured pillars."""
    pillars = project_meta.pillars
    if not pillars:
        return "| Research progress | X% | ... |"
    rows = [f"| {pillar} | X% | ... |" for pillar in pillars]
    return "\n".join(rows)


def _build_user_template(goal: str) -> str:
    pillar_rows = _build_pillar_table_rows()
    pillar_names = " / ".join(project_meta.pillars) if project_meta.pillars else "research pillars"

    return f"""\
## Previous Strategic Report
{{previous_report}}

---

## New Articles Processed Since Last Report ({{n}} articles)

{{articles_block}}

---

## Project Goal
{goal}

---

## Your Task

Produce a strategic research report with the following sections:

### 1. Progress by Pillar
For each pillar, assess progress on a 0–100% scale and briefly summarize
what has been found so far. Cite specific papers (title + URL) where relevant.

| Pillar | Progress | Status summary |
|--------|----------|----------------|
{pillar_rows}

### 2. Key Gaps
For each pillar, what is the most critical still-missing piece of knowledge?

### 3. Promising Leads
Which of the new articles above are most directly actionable? List up to 5 with
a one-line note on why each matters.

### 4. Overall Strategic Position
In 2–3 sentences: how close are we to having enough research to move forward?
What is the single biggest blocker right now?

### 5. Suggested Search Directions
List 8–12 specific search keywords or phrases that would fill the gaps identified above.
Focus on areas where we have weak coverage. Then output them as a JSON block so the
scraper can pick them up automatically:

```json
{{"suggested_keywords": ["keyword 1", "keyword 2", ...]}}
```

### 6. What Would You Build?
Based **only** on the research evidence collected so far — not what you wish existed —
describe concretely what you would build or do **today**:

- **Ready now:** What 2–3 ideas are scientifically ready to act on right now?
- **What to defer:** Which pillar ideas must wait because research is too thin?
- **Biggest insight:** What is the single most surprising or counterintuitive finding
  that should directly shape design or strategy?
"""


def run_strategic_report(db: Database, reports_dir: Path | None = None) -> list[str]:
    """
    Build and save the daily strategic report.

    Returns the list of suggested keywords extracted from the response
    (empty list if the report fails or produces none).
    """
    load_dotenv(ENV_PATH)
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logger.error("CLAUDE_API_KEY not set — cannot run strategic report")
        return []

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed — run: pip install anthropic")
        return []

    reports_dir = reports_dir or STRATEGIC_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ── Previous report ────────────────────────────────────────────────────
    previous_report = _load_previous_report(reports_dir)

    # ── Articles since last report ─────────────────────────────────────────
    last_run = _last_run_timestamp(reports_dir)
    articles = db.get_processed_since(last_run)
    logger.info(f"Strategic report: {len(articles)} new articles since {last_run[:16]}")

    if not articles and not previous_report:
        logger.info("No articles and no previous report — skipping strategic synthesis")
        return []

    # Cap and build the articles block
    top_articles = articles[:MAX_ARTICLES_TO_INCLUDE]
    articles_block = _build_articles_block(top_articles)

    # ── Build prompt from project_meta ─────────────────────────────────────
    goal = project_meta.goal or f"Research project: {project_meta.name}"
    user_template = _build_user_template(goal)
    user_msg = user_template.format(
        previous_report=previous_report or "*No previous report — this is the first run.*",
        n=len(top_articles),
        articles_block=articles_block,
    )

    # ── Call Opus 4.6 ──────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    logger.info("Calling Claude Opus 4.6 for strategic synthesis...")
    try:
        messages = [{"role": "user", "content": user_msg}]
        content_parts = []

        for attempt in range(4):  # initial + up to 3 continuations
            chunk_parts = []
            stop_reason = None
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=32768,
                system=SYSTEM,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    chunk_parts.append(text)
                stop_reason = stream.get_final_message().stop_reason

            partial = "".join(chunk_parts)
            content_parts.append(partial)

            if stop_reason != "max_tokens":
                break

            logger.warning(
                f"Strategic report truncated (attempt {attempt + 1}), "
                "sending continuation request..."
            )
            messages.append({"role": "assistant", "content": partial})
            messages.append({
                "role": "user",
                "content": "Your response was cut off. Continue exactly where you stopped.",
            })

        content = "".join(content_parts)
    except Exception as e:
        logger.error(f"Opus API call failed: {e}")
        return []

    # ── Save report ────────────────────────────────────────────────────────
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = reports_dir / f"{today}.md"
    header = (
        f"# Strategic Report — {today}\n"
        f"*Articles included: {len(top_articles)} | "
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n\n---\n\n"
    )
    report_path.write_text(header + content, encoding="utf-8")
    logger.info(f"Strategic report saved: {report_path}")

    # ── Extract and persist suggested keywords ────────────────────────────
    suggested = _extract_suggested_keywords(content)
    if suggested:
        _save_suggested_keywords(suggested)
        logger.info(f"Suggested keywords updated: {len(suggested)} terms")

    # ── Record pillar history and regenerate stats dashboard ──────────────
    try:
        snapshot = record_snapshot(content, db)
        stats_path = generate_stats_html()
        logger.info(
            f"Stats dashboard updated: {stats_path} "
            f"(pillars: {snapshot['pillars']})"
        )
    except Exception as e:
        logger.warning(f"Stats update failed (non-fatal): {e}")

    return suggested


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_previous_report(reports_dir: Path) -> str:
    """Return the most recent strategic report text, or empty string if none."""
    reports = sorted(reports_dir.glob("*.md"))
    if not reports:
        return ""
    latest = reports[-1]
    try:
        text = latest.read_text(encoding="utf-8")
        # Trim to avoid ballooning the prompt with huge historical reports
        if len(text) > 8000:
            text = text[:8000] + "\n\n*[truncated for brevity]*"
        return text
    except Exception:
        return ""


def _last_run_timestamp(reports_dir: Path) -> str:
    """Return ISO timestamp of when the last strategic report was created, or epoch."""
    reports = sorted(reports_dir.glob("*.md"))
    if not reports:
        return "2000-01-01T00:00:00+00:00"
    last_date = reports[-1].stem  # "2026-04-03"
    return f"{last_date}T00:00:00+00:00"


def _build_articles_block(articles: list[Article]) -> str:
    parts = []
    for i, a in enumerate(articles, 1):
        abstract = (a.abstract or "")[:MAX_ABSTRACT_CHARS]
        if len(a.abstract or "") > MAX_ABSTRACT_CHARS:
            abstract += "…"
        findings = ""
        if a.key_findings:
            findings = "\n  Key findings: " + " | ".join(a.key_findings[:3])
        topics = ", ".join(a.subtopics) if a.subtopics else "uncategorized"
        parts.append(
            f"**[{i}] {a.title}**\n"
            f"  URL: {a.source_url}\n"
            f"  Score: {a.relevance_score:.2f} | Topics: {topics}\n"
            f"  {abstract}{findings}"
        )
    return "\n\n".join(parts) if parts else "*No new articles in this period.*"


def _extract_suggested_keywords(text: str) -> list[str]:
    """Parse the ```json ... ``` block from the Opus response."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        kws = data.get("suggested_keywords", [])
        return [str(k).strip() for k in kws if k and str(k).strip()]
    except (json.JSONDecodeError, KeyError):
        return []


def _save_suggested_keywords(keywords: list[str]):
    """Write suggested keywords to the shared JSON file for the scraper to blend in."""
    SUGGESTED_KW_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if SUGGESTED_KW_PATH.exists():
        try:
            existing = json.loads(SUGGESTED_KW_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Merge: keep existing, add new ones (deduplicated, preserve order)
    seen = {k.lower() for k in existing}
    merged = existing + [k for k in keywords if k.lower() not in seen]
    SUGGESTED_KW_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
