"""
cloud_sync.py — Pushes current pipeline state to the Research Dashboard.

Called from the orchestrator after each cycle (status) and after the
strategic report (progress, report, keywords, daily task outputs).

Configure in pipeline/.env:
  DASHBOARD_API_URL=https://research-dashboard.railway.app
  DASHBOARD_API_KEY=<key from admin panel>
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

import httpx
from loguru import logger

ROOT = Path(__file__).parent.parent


def _client() -> tuple[str, dict]:
    """Return (base_url, headers) or raise if not configured."""
    url = os.getenv("DASHBOARD_API_URL", "").rstrip("/")
    key = os.getenv("DASHBOARD_API_KEY", "")
    if not url or not key:
        raise ValueError("DASHBOARD_API_URL and DASHBOARD_API_KEY must be set in pipeline/.env")
    return url, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _post(path: str, payload: dict) -> bool:
    """POST to the dashboard API. Returns True on success, logs and returns False on error."""
    try:
        url, headers = _client()
        r = httpx.post(f"{url}{path}", json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        return True
    except ValueError as e:
        logger.debug(f"cloud_sync skipped ({e})")
        return False
    except Exception as e:
        logger.warning(f"cloud_sync failed for {path}: {e}")
        return False


# ---------------------------------------------------------------------------
# Push functions — each called at the right point in the orchestrator
# ---------------------------------------------------------------------------

def sync_status(db) -> bool:
    """
    Push pipeline heartbeat after every cycle.
    Call: cloud_sync.sync_status(self.db)
    """
    try:
        stats = db.stats()
        by_status = stats.get("by_status", {})
        return _post("/api/push/status", {
            "scraped_total": sum(by_status.values()),
            "relevant_total": by_status.get("embedded", 0) + by_status.get("summarized", 0),
            "github_repos": stats.get("github_repos", 0),
            "last_cycle_at": datetime.now(timezone.utc).isoformat(),
            "cycle_count": stats.get("cycle_count", 0),
        })
    except Exception as e:
        logger.warning(f"cloud_sync.sync_status error: {e}")
        return False


def _load_pillar_descriptions() -> dict:
    """Read pillar descriptions from config/pillar_descriptions.yaml, if present."""
    cfg_path = ROOT / "config" / "pillar_descriptions.yaml"
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        return data.get("descriptions", {}) if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"cloud_sync: could not read pillar_descriptions.yaml: {e}")
        return {}


def sync_progress(date: str) -> bool:
    """
    Push pillar progress percentages for a specific date.
    Reads from data/pillar_history.json — call after strategic report writes it.
    Also pushes pillar descriptions from config/pillar_descriptions.yaml if present.

    Call: cloud_sync.sync_progress(today_str)
    """
    path = ROOT / "data" / "pillar_history.json"
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
        # Find the entry for this date
        entry = next((h for h in reversed(history) if h.get("date") == date), None)
        if not entry:
            logger.debug(f"cloud_sync: no pillar history entry for {date}")
            return False

        pillars_raw = entry.get("pillars", {})
        pillars = [{"name": name, "pct": pct} for name, pct in pillars_raw.items()]
        payload = {"date": date, "pillars": pillars}

        descriptions = _load_pillar_descriptions()
        if descriptions:
            payload["descriptions"] = descriptions

        return _post("/api/push/progress", payload)
    except Exception as e:
        logger.warning(f"cloud_sync.sync_progress error: {e}")
        return False


def sync_report(date: str, reports_dir: Path = None) -> bool:
    """
    Push the strategic report markdown for a specific date.
    Call: cloud_sync.sync_report(today_str)
    """
    if reports_dir is None:
        reports_dir = ROOT / "reports" / "strategic"
    report_path = reports_dir / f"{date}.md"
    try:
        content = report_path.read_text(encoding="utf-8")
        return _post("/api/push/report", {"date": date, "content_md": content})
    except FileNotFoundError:
        logger.debug(f"cloud_sync: report not found for {date}")
        return False
    except Exception as e:
        logger.warning(f"cloud_sync.sync_report error: {e}")
        return False


def sync_keywords() -> bool:
    """
    Replace the keyword pool on the dashboard with the current suggested_keywords.json.
    Call: cloud_sync.sync_keywords()
    """
    path = ROOT / "data" / "suggested_keywords.json"
    try:
        keywords = json.loads(path.read_text(encoding="utf-8"))
        return _post("/api/push/keywords", {"keywords": keywords})
    except Exception as e:
        logger.warning(f"cloud_sync.sync_keywords error: {e}")
        return False


def sync_output(date: str, task_name: str, task_title: str, html_path: Path) -> bool:
    """
    Push a daily task HTML output to the dashboard.

    Call after generating each daily task output, e.g.:
      cloud_sync.sync_output("2026-04-12", "app-mockup", "App Mockup", Path("reports/app-mockup-v2.html"))
    """
    try:
        html = html_path.read_text(encoding="utf-8")
        return _post("/api/push/output", {
            "date": date,
            "task_name": task_name,
            "task_title": task_title,
            "html_content": html,
        })
    except FileNotFoundError:
        logger.debug(f"cloud_sync: output file not found: {html_path}")
        return False
    except Exception as e:
        logger.warning(f"cloud_sync.sync_output error: {e}")
        return False


def sync_sources(db, top_n: int = 100) -> bool:
    """
    Push the top-N most relevant processed articles to the dashboard as Best Sources.
    Reads from the pipeline SQLite DB — call after any pipeline cycle.

    Call: cloud_sync.sync_sources(self.db)
    """
    try:
        with db._conn() as con:
            rows = con.execute(
                """
                SELECT title, source_url, source_type, publication_date, relevance_score
                FROM articles
                WHERE status IN ('summarized', 'embedded')
                  AND source_url != ''
                  AND title != ''
                ORDER BY relevance_score DESC
                LIMIT ?
                """,
                (top_n,),
            ).fetchall()

        sources = [
            {
                "url": r["source_url"],
                "title": r["title"],
                "source_type": r["source_type"],
                "publication_date": r["publication_date"],
                "relevance_score": r["relevance_score"],
            }
            for r in rows
        ]
        return _post("/api/push/sources", {"sources": sources})
    except Exception as e:
        logger.warning(f"cloud_sync.sync_sources error: {e}")
        return False


def sync_all_after_strategic_report(date: str, reports_dir: Path = None) -> None:
    """
    Convenience: call all post-strategic-report syncs in one go.
    Call: cloud_sync.sync_all_after_strategic_report(today_str, self.config.reports_dir / "strategic")
    """
    sync_progress(date)
    sync_report(date, reports_dir)
    sync_keywords()
    logger.info("cloud_sync: progress, report, keywords pushed to dashboard")
