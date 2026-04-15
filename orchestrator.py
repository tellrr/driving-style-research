"""
Orchestrator — the main long-running loop.

Phases each cycle:
  1. FETCH     — scrape new articles from all sources
  2. PIPELINE  — filter → categorize → summarize → embed
  3. SYNTHESIZE — daily/weekly cross-paper reports (when due)

Checkpointing: every article's status is persisted in SQLite, so the loop
resumes from exactly where it left off after a crash or restart.
"""

import time
from datetime import datetime, timedelta, timezone

from loguru import logger

from config.settings import Config
from llm.client import OllamaClient
from models import Article
from pipeline.categorizer import categorize_article
from pipeline.filter import filter_article
from pipeline.strategic_report import run_strategic_report
from pipeline import cloud_sync
from pipeline.daily_tasks_runner import run_daily_tasks
from pipeline.stats_generator import generate_stats_html
from pipeline.summarizer import summarize_article
from pipeline.synthesizer import synthesize_subtopic
from scraper.scheduler import Scraper
from storage.db import Database
from storage.vectorstore import VectorStore


class Orchestrator:
    def __init__(self, config: Config, db: Database, llm: OllamaClient,
                 scraper: Scraper, vectorstore: VectorStore):
        self.config = config
        self.db = db
        self.llm = llm
        self.scraper = scraper
        self.vs = vectorstore
        self.subtopic_names = scraper.get_subtopic_names()
        self._cycle_count = 0

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        from config.settings import project_meta
        logger.info("=" * 60)
        logger.info(f"Research Pipeline starting: {project_meta.name}")
        logger.info(f"  Pipeline model : {self.config.llm.pipeline_model}")
        logger.info(f"  Synthesis model: {self.config.llm.synthesis_model}")
        logger.info(f"  Subtopics      : {len(self.subtopic_names)}")
        logger.info(f"  Pillars        : {len(project_meta.pillars)}")
        logger.info(f"  Cycle interval : {self.config.orchestrator.cycle_interval_seconds}s")
        logger.info("=" * 60)

        if not self.llm.is_available():
            logger.error("Ollama is not reachable at "
                         f"{self.config.llm.base_url} — start it first.")
            return

        while True:
            try:
                self._run_cycle()
            except KeyboardInterrupt:
                logger.info("Shutdown requested — exiting cleanly.")
                break
            except Exception as e:
                logger.error(f"Unhandled error in cycle: {e}", exc_info=True)
                logger.info("Sleeping 60s before retry...")
                time.sleep(60)

    # ------------------------------------------------------------------
    # Single cycle
    # ------------------------------------------------------------------

    def _run_cycle(self):
        self._cycle_count += 1
        cycle_start = time.time()
        oc = self.config.orchestrator
        logger.info(f"--- Cycle {self._cycle_count} start ---")

        # 1. FETCH
        self.scraper.run_cycle(keywords_per_source=6)
        stats = self.db.stats()
        logger.info(f"DB stats: {stats['by_status']}")

        # 1b. STRATEGIC REPORT — once per day, after first cycle that completes post-3 AM
        if self._strategic_report_due():
            self._run_strategic_report()

        # 2. PIPELINE — process pending articles
        pending = self.db.get_by_status("fetched", limit=oc.max_pipeline_per_cycle)
        logger.info(f"Pipeline: {len(pending)} articles to process")
        processed = 0
        for article in pending:
            if self._process_article(article):
                processed += 1

        logger.info(f"Pipeline complete: {processed}/{len(pending)} articles processed")

        # 3. SYNTHESIZE — check if due
        if self._synthesis_due("daily", oc.synthesis_interval_hours):
            self._run_synthesis("daily")
        if self._synthesis_due("weekly", oc.weekly_synthesis_interval_days * 24):
            self._run_synthesis("weekly")

        # Push heartbeat to dashboard
        cloud_sync.sync_status(self.db)

        elapsed = time.time() - cycle_start
        sleep_for = oc.cycle_interval_seconds
        logger.info(
            f"--- Cycle {self._cycle_count} done in {elapsed:.0f}s "
            f"| waiting {sleep_for:.0f}s before next cycle ---"
        )
        time.sleep(sleep_for)

    # ------------------------------------------------------------------
    # Article pipeline
    # ------------------------------------------------------------------

    def _process_article(self, article: Article) -> bool:
        """Run filter → categorize → summarize → embed on one article. Returns True on success."""
        try:
            pc = self.config.pipeline

            # --- Filter ---
            relevant, score, reason = filter_article(article, self.llm, pc.relevance_threshold)
            if not relevant:
                self.db.update_status(article.id, "filtered_out", relevance_score=score)
                logger.debug(f"Filtered out [{score:.2f}]: {article.title[:60]}")
                return True  # processed, just not relevant

            # --- Categorize ---
            subtopics = categorize_article(article, self.llm, self.subtopic_names)

            # --- Summarize ---
            summary, key_findings, app_relevance = summarize_article(
                article, self.llm,
                max_abstract=pc.max_abstract_chars,
                max_full_text=pc.max_full_text_chars,
            )
            if app_relevance:
                summary = f"{summary}\n\n*Relevance: {app_relevance}*"

            # --- Persist ---
            self.db.update_pipeline_result(
                article.id,
                subtopics=subtopics,
                relevance_score=score,
                summary=summary,
                key_findings=key_findings,
                status="summarized",
            )
            article.subtopics = subtopics
            article.summary = summary
            article.key_findings = key_findings

            # --- Embed ---
            self.vs.add(article)
            self.db.update_status(article.id, "embedded")

            logger.info(
                f"✓ [{score:.2f}] {article.title[:55]} "
                f"→ {', '.join(subtopics[:2]) or 'uncategorized'}"
            )
            return True

        except Exception as e:
            logger.error(f"Pipeline failed for '{article.title[:40]}': {e}", exc_info=True)
            self.db.update_status(article.id, "error")
            return False

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _synthesis_due(self, run_type: str, interval_hours: int) -> bool:
        last = self.db.last_synthesis_time(run_type)
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            return datetime.now(timezone.utc) - last_dt > timedelta(hours=interval_hours)
        except ValueError:
            return True

    def _run_synthesis(self, run_type: str):
        since_hours = (
            self.config.orchestrator.synthesis_interval_hours if run_type == "daily"
            else self.config.orchestrator.weekly_synthesis_interval_days * 24
        )
        since = (
            datetime.now(timezone.utc) - timedelta(hours=since_hours)
        ).isoformat()

        logger.info(f"Synthesis [{run_type}] — collecting articles since {since[:16]}")
        all_articles = self.db.get_summarized_since(since)
        logger.info(f"Synthesis [{run_type}] — {len(all_articles)} summarized articles")

        if not all_articles:
            logger.info("No new summaries for synthesis, skipping.")
            return

        for subtopic in self.subtopic_names:
            run = synthesize_subtopic(
                subtopic=subtopic,
                articles=all_articles,
                client=self.llm,
                run_type=run_type,
                reports_dir=self.config.reports_dir,
            )
            if run:
                self.db.insert_synthesis(run)

        logger.info(f"Synthesis [{run_type}] complete")

    # ------------------------------------------------------------------
    # Strategic report (Opus 4.6, once per day after 3 AM)
    # ------------------------------------------------------------------

    def _strategic_report_due(self) -> bool:
        now = datetime.now(timezone.utc)
        if now.hour < 3:
            return False
        last = self.db.get_cursor("strategic", "last_run", "")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            today_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
            return last_dt < today_3am
        except ValueError:
            return True

    def _run_strategic_report(self):
        logger.info("Strategic report [Opus 4.6] — starting")
        try:
            suggested = run_strategic_report(
                db=self.db,
                reports_dir=self.config.reports_dir / "strategic",
            )
            self.db.set_cursor("strategic", "last_run",
                               datetime.now(timezone.utc).isoformat())
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            cloud_sync.sync_all_after_strategic_report(
                today, self.config.reports_dir / "strategic"
            )
            cloud_sync.sync_sources(self.db)
            run_daily_tasks(today)
            generate_stats_html()  # refresh to include today's daily task outputs
            if suggested:
                logger.info(
                    f"Strategic report complete — {len(suggested)} new search terms suggested"
                )
            else:
                logger.info("Strategic report complete")
        except Exception as e:
            logger.error(f"Strategic report failed: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Status snapshot (call anytime)
    # ------------------------------------------------------------------

    def status(self) -> dict:
        s = self.db.stats()
        s["cycle"] = self._cycle_count
        s["vector_store_count"] = self.vs.count()
        s["llm_available"] = self.llm.is_available()
        return s
