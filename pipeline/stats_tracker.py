"""Collect and persist historical research progress statistics.

Called after each strategic report is generated. Parses the configured pillar
progress percentages from the report markdown and records them alongside
live DB stats into data/pillar_history.json. The stats_generator module
reads this file to build the HTML dashboard.

Pillar names are read from config/topic_config.md (## Pillars section) —
no changes to this file are required when setting up a new research project.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from storage.db import Database

ROOT = Path(__file__).parent.parent
HISTORY_PATH = ROOT / "data" / "pillar_history.json"


def _get_pillars() -> list[str]:
    """Return pillar names from project_meta, or a single fallback."""
    from config.settings import project_meta
    return project_meta.pillars or ["Research Progress"]


def record_snapshot(report_content: str, db: Database) -> dict:
    """Parse pillar percentages from the Opus report, collect DB stats, and
    append a dated snapshot to data/pillar_history.json.

    If a snapshot for today already exists it is replaced (idempotent on re-runs).
    Returns the new snapshot dict.
    """
    pillars = _parse_pillar_percentages(report_content)
    stats = _collect_db_stats(db)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    snapshot = {
        "date": today,
        "pillars": pillars,
        "stats": stats,
    }

    history = load_history()
    history = [e for e in history if e["date"] != today]   # drop today if exists
    history.append(snapshot)
    history.sort(key=lambda e: e["date"])

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return snapshot


def backfill_history(reports_dir: Path, db: Database) -> list[dict]:
    """Parse all existing strategic reports and rebuild data/pillar_history.json."""
    report_files = sorted(reports_dir.glob("*.md"))
    if not report_files:
        return load_history()

    history = load_history()
    new_snapshots: list[dict] = []
    for path in report_files:
        date_str = path.stem
        content = path.read_text(encoding="utf-8")
        pillars = _parse_pillar_percentages(content)
        stats = db.stats_as_of(date_str)

        snapshot = {
            "date": date_str,
            "pillars": pillars,
            "stats": stats,
        }
        new_snapshots.append(snapshot)

    backfill_dates = {s["date"] for s in new_snapshots}
    merged = [e for e in history if e["date"] not in backfill_dates] + new_snapshots
    merged.sort(key=lambda e: e["date"])

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return merged


def load_history() -> list[dict]:
    """Return the full list of daily snapshots, oldest first."""
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_pillar_percentages(content: str) -> dict[str, int | None]:
    """Extract pillar progress percentages from the strategic report table.

    Matches rows of the form:
        | **Pillar Name** | **72%** | ...

    Matches each configured pillar by searching for significant words from its
    name in the raw table cell text (case-insensitive).
    """
    pillars = _get_pillars()
    result: dict[str, int | None] = {p: None for p in pillars}

    # Matches bold pillar name followed by percentage (bold optional) in the same table row
    pattern = re.compile(
        r'\|\s*\*\*([^|*\n]+?)\*\*\s*\|\s*(?:\*\*)?(\d+)%(?:\*\*)?',
        re.IGNORECASE,
    )

    for m in pattern.finditer(content):
        raw = m.group(1).lower().strip()
        pct = int(m.group(2))
        for pillar in pillars:
            # Match if any significant word (>3 chars) from the pillar name appears in the cell
            significant_words = [w.lower() for w in pillar.split() if len(w) > 3]
            if pillar.lower() in raw or any(w in raw for w in significant_words):
                if result[pillar] is None:  # first match wins
                    result[pillar] = pct
                break

    return result


def _collect_db_stats(db: Database) -> dict:
    """Read live counts from the database."""
    db_stats = db.stats()
    by_status = db_stats.get("by_status", {})
    total_scraped = db_stats.get("total_articles", 0)
    total_relevant = (
        by_status.get("categorized", 0)
        + by_status.get("summarized", 0)
        + by_status.get("embedded", 0)
    )
    total_github = db.count_github_repos()
    return {
        "total_scraped": total_scraped,
        "total_relevant": total_relevant,
        "total_github_repos": total_github,
    }
