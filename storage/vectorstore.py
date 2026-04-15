"""
Lightweight SQLite + numpy vector store.

Replaces ChromaDB to avoid Rust/DLL dependency issues on Windows.
Embeddings are stored as BLOBs in SQLite and loaded into numpy for cosine search.
Sufficient for tens of thousands of articles with nomic-embed-text (768-dim).
"""

import json
import sqlite3
import struct
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from loguru import logger

from models import Article

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False
    logger.warning("numpy not installed — VectorStore search disabled")


class VectorStore:
    """SQLite-backed vector store with cosine similarity search."""

    def __init__(self, db_path: Path, embed_fn):
        self._db_path = db_path / "vectors.db"
        self._embed = embed_fn
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        logger.debug(f"VectorStore ready (SQLite): {self._db_path}")

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(self._db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init_schema(self):
        with self._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS vectors (
                    id           TEXT PRIMARY KEY,
                    title        TEXT,
                    source_url   TEXT,
                    subtopics    TEXT,
                    relevance    REAL,
                    embedding    BLOB NOT NULL
                )
            """)

    def add(self, article: Article) -> bool:
        text = _article_text(article)
        if not text:
            return False
        try:
            embedding = self._embed(text)
            blob = _pack(embedding)
            with self._conn() as con:
                con.execute(
                    """INSERT OR REPLACE INTO vectors
                       (id, title, source_url, subtopics, relevance, embedding)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        article.id,
                        article.title[:200],
                        article.source_url,
                        ", ".join(article.subtopics),
                        article.relevance_score,
                        blob,
                    ),
                )
            return True
        except Exception as e:
            logger.warning(f"VectorStore.add failed for {article.id}: {e}")
            return False

    def search(
        self,
        query: str,
        n_results: int = 10,
        subtopic_filter: Optional[str] = None,
    ) -> list[dict]:
        if not _NUMPY:
            return []
        try:
            q_emb = np.array(self._embed(query), dtype=np.float32)
            q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)

            with self._conn() as con:
                if subtopic_filter:
                    rows = con.execute(
                        "SELECT id, title, source_url, subtopics, relevance, embedding "
                        "FROM vectors WHERE subtopics LIKE ?",
                        (f"%{subtopic_filter}%",),
                    ).fetchall()
                else:
                    rows = con.execute(
                        "SELECT id, title, source_url, subtopics, relevance, embedding FROM vectors"
                    ).fetchall()

            if not rows:
                return []

            scores = []
            for row in rows:
                vec = np.array(_unpack(row["embedding"]), dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm < 1e-9:
                    continue
                cos_sim = float(np.dot(q_norm, vec / norm))
                scores.append((cos_sim, row))

            scores.sort(key=lambda x: x[0], reverse=True)
            return [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "source_url": r["source_url"],
                    "subtopics": r["subtopics"],
                    "distance": round(1.0 - sim, 4),   # cosine distance
                }
                for sim, r in scores[:n_results]
            ]
        except Exception as e:
            logger.warning(f"VectorStore.search failed: {e}")
            return []

    def count(self) -> int:
        try:
            with self._conn() as con:
                return con.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
        except Exception:
            return 0


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _pack(floats: list[float]) -> bytes:
    return struct.pack(f"{len(floats)}f", *floats)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _article_text(article: Article) -> str:
    parts = [article.title]
    if article.summary:
        parts.append(article.summary)
    elif article.abstract:
        parts.append(article.abstract[:500])
    if article.key_findings:
        parts.extend(article.key_findings)
    return " | ".join(parts)
