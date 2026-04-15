"""
force_report.py — Run the strategic report + daily tasks immediately.

Use this to generate the first dashboard entry without waiting for the
overnight 3 AM trigger. Safe to run while the main pipeline loop is running.

Usage:
    python force_report.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger
from config.settings import config, project_meta
from pipeline.strategic_report import run_strategic_report
from pipeline.daily_tasks_runner import run_daily_tasks
from pipeline.stats_generator import generate_stats_html
from pipeline import cloud_sync
from storage.db import Database

logger.remove()
logger.add(sys.stderr, level="INFO", colorize=True,
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}")

config.ensure_dirs()
db = Database(config.data_dir / "research.db")

stats = db.stats()
by_status = stats.get("by_status", {})
summarized = by_status.get("summarized", 0) + by_status.get("embedded", 0)
fetched = by_status.get("fetched", 0)

logger.info(f"Project: {project_meta.name}")
logger.info(f"DB — fetched: {fetched}  summarized/embedded: {summarized}  "
            f"filtered_out: {by_status.get('filtered_out', 0)}")

if summarized == 0:
    logger.warning(
        "No summarized articles yet — Opus will produce a framework report "
        "based on the project goal only. Re-run after the pipeline has processed "
        "some articles for a richer first report."
    )

logger.info("Running strategic report (Claude Opus 4.6)...")
suggested = run_strategic_report(
    db=db,
    reports_dir=config.reports_dir / "strategic",
)

today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

logger.info("Syncing to dashboard...")
cloud_sync.sync_all_after_strategic_report(today, config.reports_dir / "strategic")
cloud_sync.sync_sources(db)

logger.info("Running daily tasks (report-mockup, daily-brief)...")
run_daily_tasks(today)

logger.info("Regenerating stats HTML...")
generate_stats_html()

if suggested:
    logger.info(f"Done — {len(suggested)} new search keywords suggested by Opus")
else:
    logger.info("Done")
