"""SQLite state store — tracks every article through the pipeline."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from models import Article, SynthesisRun


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self):
        with self._conn() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS articles (
                    id               TEXT PRIMARY KEY,
                    title            TEXT NOT NULL,
                    source_url       TEXT UNIQUE NOT NULL,
                    source_type      TEXT NOT NULL,
                    abstract         TEXT DEFAULT '',
                    full_text        TEXT,
                    authors          TEXT DEFAULT '[]',
                    publication_date TEXT,
                    doi              TEXT,
                    subtopics        TEXT DEFAULT '[]',
                    relevance_score  REAL DEFAULT 0.0,
                    summary          TEXT,
                    key_findings     TEXT DEFAULT '[]',
                    date_collected   TEXT NOT NULL,
                    date_processed   TEXT,
                    status           TEXT DEFAULT 'fetched'
                );

                CREATE TABLE IF NOT EXISTS synthesis_runs (
                    id                  TEXT PRIMARY KEY,
                    subtopic            TEXT NOT NULL,
                    run_type            TEXT NOT NULL,
                    content             TEXT NOT NULL,
                    articles_included   INTEGER DEFAULT 0,
                    created_at          TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fetch_log (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    source        TEXT NOT NULL,
                    query         TEXT NOT NULL,
                    items_found   INTEGER DEFAULT 0,
                    items_new     INTEGER DEFAULT 0,
                    timestamp     TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS scraper_cursors (
                    source  TEXT NOT NULL,
                    key     TEXT NOT NULL,
                    value   TEXT NOT NULL,
                    PRIMARY KEY (source, key)
                );

                CREATE INDEX IF NOT EXISTS idx_articles_status
                    ON articles(status);
                CREATE INDEX IF NOT EXISTS idx_articles_source_type
                    ON articles(source_type);
                CREATE INDEX IF NOT EXISTS idx_synthesis_subtopic
                    ON synthesis_runs(subtopic, created_at);
            """)
        # Migrations — safe to re-run; ALTER TABLE is a no-op if column exists
        with self._conn() as con:
            existing = {r[1] for r in con.execute("PRAGMA table_info(articles)").fetchall()}
            if "date_processed" not in existing:
                con.execute("ALTER TABLE articles ADD COLUMN date_processed TEXT")
                logger.info("DB migration: added date_processed column")
        logger.debug(f"Database ready: {self.db_path}")

    # ------------------------------------------------------------------
    # Articles
    # ------------------------------------------------------------------

    def exists(self, article_id: str) -> bool:
        with self._conn() as con:
            row = con.execute(
                "SELECT 1 FROM articles WHERE id = ?", (article_id,)
            ).fetchone()
            return row is not None

    def insert(self, article: Article) -> bool:
        """Insert a new article. Returns False if already exists."""
        try:
            with self._conn() as con:
                con.execute(
                    """INSERT INTO articles
                       (id, title, source_url, source_type, abstract, full_text,
                        authors, publication_date, doi, subtopics, relevance_score,
                        summary, key_findings, date_collected, status)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        article.id,
                        article.title,
                        article.source_url,
                        article.source_type,
                        article.abstract or "",
                        article.full_text,
                        json.dumps(article.authors),
                        article.publication_date,
                        article.doi,
                        json.dumps(article.subtopics),
                        article.relevance_score,
                        article.summary,
                        json.dumps(article.key_findings),
                        article.date_collected or _now(),
                        article.status,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def update_status(self, article_id: str, status: str, **kwargs):
        """Update status and any extra fields."""
        fields = {"status": status}
        fields.update(kwargs)
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [article_id]
        with self._conn() as con:
            con.execute(
                f"UPDATE articles SET {set_clause} WHERE id = ?", values
            )

    def update_pipeline_result(
        self,
        article_id: str,
        *,
        subtopics: Optional[list] = None,
        relevance_score: Optional[float] = None,
        summary: Optional[str] = None,
        key_findings: Optional[list] = None,
        status: Optional[str] = None,
    ):
        sets, vals = [], []
        if subtopics is not None:
            sets.append("subtopics = ?"); vals.append(json.dumps(subtopics))
        if relevance_score is not None:
            sets.append("relevance_score = ?"); vals.append(relevance_score)
        if summary is not None:
            sets.append("summary = ?"); vals.append(summary)
        if key_findings is not None:
            sets.append("key_findings = ?"); vals.append(json.dumps(key_findings))
        if status is not None:
            sets.append("status = ?"); vals.append(status)
        if status == "summarized":
            sets.append("date_processed = ?"); vals.append(_now())
        if not sets:
            return
        vals.append(article_id)
        with self._conn() as con:
            con.execute(
                f"UPDATE articles SET {', '.join(sets)} WHERE id = ?", vals
            )

    def get_by_status(self, status: str, limit: int = 50) -> list[Article]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM articles WHERE status = ? ORDER BY date_collected LIMIT ?",
                (status, limit),
            ).fetchall()
        return [_row_to_article(r) for r in rows]

    def count_by_status(self) -> dict[str, int]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT status, COUNT(*) as n FROM articles GROUP BY status"
            ).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def get_processed_since(self, since_iso: str) -> list[Article]:
        """Fetch all articles with summaries (summarized + embedded) processed since a given time.
        Uses date_processed (when summarized) with fallback to date_collected for legacy rows."""
        with self._conn() as con:
            rows = con.execute(
                """SELECT * FROM articles
                   WHERE status IN ('summarized', 'embedded')
                     AND summary IS NOT NULL
                     AND COALESCE(date_processed, date_collected) >= ?
                   ORDER BY relevance_score DESC""",
                (since_iso,),
            ).fetchall()
        return [_row_to_article(r) for r in rows]

    def get_summarized_since(self, since_iso: str, subtopic: Optional[str] = None) -> list[Article]:
        """Fetch summarized articles for synthesis."""
        if subtopic:
            with self._conn() as con:
                rows = con.execute(
                    """SELECT * FROM articles
                       WHERE status = 'summarized'
                         AND COALESCE(date_processed, date_collected) >= ?
                         AND subtopics LIKE ?""",
                    (since_iso, f"%{subtopic}%"),
                ).fetchall()
        else:
            with self._conn() as con:
                rows = con.execute(
                    """SELECT * FROM articles WHERE status = 'summarized'
                       AND COALESCE(date_processed, date_collected) >= ?""",
                    (since_iso,),
                ).fetchall()
        return [_row_to_article(r) for r in rows]

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def insert_synthesis(self, run: SynthesisRun):
        with self._conn() as con:
            con.execute(
                """INSERT OR REPLACE INTO synthesis_runs
                   (id, subtopic, run_type, content, articles_included, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (run.id, run.subtopic, run.run_type, run.content,
                 run.articles_included, run.created_at),
            )

    def last_synthesis_time(self, run_type: str) -> Optional[str]:
        with self._conn() as con:
            row = con.execute(
                "SELECT created_at FROM synthesis_runs WHERE run_type = ? ORDER BY created_at DESC LIMIT 1",
                (run_type,),
            ).fetchone()
        return row["created_at"] if row else None

    # ------------------------------------------------------------------
    # Fetch log
    # ------------------------------------------------------------------

    def log_fetch(self, source: str, query: str, found: int, new: int):
        with self._conn() as con:
            con.execute(
                "INSERT INTO fetch_log (source, query, items_found, items_new, timestamp) VALUES (?,?,?,?,?)",
                (source, query, found, new, _now()),
            )

    # ------------------------------------------------------------------
    # Scraper cursors (for pagination / "last seen" tracking)
    # ------------------------------------------------------------------

    def get_cursor(self, source: str, key: str, default: str = "") -> str:
        with self._conn() as con:
            row = con.execute(
                "SELECT value FROM scraper_cursors WHERE source = ? AND key = ?",
                (source, key),
            ).fetchone()
        return row["value"] if row else default

    def set_cursor(self, source: str, key: str, value: str):
        with self._conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO scraper_cursors (source, key, value) VALUES (?,?,?)",
                (source, key, value),
            )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats_as_of(self, date_str: str) -> dict:
        """Return article counts as they stood at end-of-day on date_str (YYYY-MM-DD).
        Used for backfilling historical statistics snapshots."""
        cutoff = f"{date_str}T23:59:59"
        with self._conn() as con:
            total = con.execute(
                "SELECT COUNT(*) FROM articles WHERE date_collected <= ?",
                (cutoff,),
            ).fetchone()[0]
            relevant = con.execute(
                """SELECT COUNT(*) FROM articles
                   WHERE date_collected <= ?
                     AND status NOT IN ('filtered_out', 'fetched', 'error')""",
                (cutoff,),
            ).fetchone()[0]
            github = con.execute(
                """SELECT COUNT(*) FROM articles
                   WHERE source_type = 'github'
                     AND date_collected <= ?
                     AND status NOT IN ('filtered_out', 'fetched', 'error')""",
                (cutoff,),
            ).fetchone()[0]
        return {
            "total_scraped": total,
            "total_relevant": relevant,
            "total_github_repos": github,
        }

    def count_github_repos(self) -> int:
        """Count GitHub repositories that passed the relevance filter."""
        with self._conn() as con:
            return con.execute(
                """SELECT COUNT(*) FROM articles
                   WHERE source_type = 'github'
                     AND status NOT IN ('filtered_out', 'fetched', 'error')"""
            ).fetchone()[0]

    def stats(self) -> dict:
        counts = self.count_by_status()
        total = sum(counts.values())
        with self._conn() as con:
            synth_count = con.execute(
                "SELECT COUNT(*) FROM synthesis_runs"
            ).fetchone()[0]
        return {"total_articles": total, "by_status": counts, "synthesis_runs": synth_count}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_article(row: sqlite3.Row) -> Article:
    return Article(
        id=row["id"],
        title=row["title"],
        source_url=row["source_url"],
        source_type=row["source_type"],
        abstract=row["abstract"] or "",
        full_text=row["full_text"],
        authors=json.loads(row["authors"] or "[]"),
        publication_date=row["publication_date"],
        doi=row["doi"],
        subtopics=json.loads(row["subtopics"] or "[]"),
        relevance_score=row["relevance_score"] or 0.0,
        summary=row["summary"],
        key_findings=json.loads(row["key_findings"] or "[]"),
        date_collected=row["date_collected"],
        status=row["status"],
    )
