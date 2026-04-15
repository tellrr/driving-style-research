"""
Entry point for the research pipeline.

Usage:
    python run.py             # start the continuous loop
    python run.py --status    # print DB stats and exit
    python run.py --test      # run a single small cycle and exit
    python run.py --search "query"  # semantic search and exit
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of working directory
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from config.settings import config, project_meta
from llm import create_llm_client
from orchestrator import Orchestrator
from scraper.scheduler import Scraper
from storage.db import Database
from storage.vectorstore import VectorStore


def build_components():
    config.ensure_dirs()

    # Logging — rotating file + stderr
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}")
    logger.add(
        config.logs_dir / "pipeline_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="1 day",
        retention="14 days",
        encoding="utf-8",
    )

    db = Database(config.data_dir / "research.db")

    llm = create_llm_client(config)
    logger.info(f"LLM provider: {config.llm.provider} | pipeline model: {config.llm.pipeline_model}")

    vs = VectorStore(
        db_path=config.data_dir / "chroma",
        embed_fn=llm.embed,
    )

    scraper = Scraper(config, db)

    orchestrator = Orchestrator(config, db, llm, scraper, vs)
    return orchestrator, db, llm, vs


def cmd_status(orchestrator: Orchestrator):
    s = orchestrator.status()
    print(f"\n=== {project_meta.name} — Pipeline Status ===")
    print(f"  LLM provider     : {config.llm.provider} ({config.llm.pipeline_model})")
    print(f"  LLM available    : {s['llm_available']}")
    print(f"  Cycle count      : {s['cycle']}")
    print(f"  Total articles   : {s['total_articles']}")
    print(f"  Vector store     : {s['vector_store_count']} items")
    print("  By status:")
    for status, n in sorted(s["by_status"].items()):
        print(f"    {status:<18} {n}")
    print(f"  Synthesis runs   : {s['synthesis_runs']}")
    print()


def cmd_search(orchestrator: Orchestrator, query: str):
    results = orchestrator.vs.search(query, n_results=10)
    print(f"\n=== Semantic Search: '{query}' ===\n")
    if not results:
        print("No results (vector store may be empty or unavailable)")
        return
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r.get('distance', 0):.3f}] {r.get('title', 'unknown')}")
        print(f"   {r.get('source_url', '')}")
        print()


def cmd_test(orchestrator: Orchestrator):
    """Run a single minimal cycle for smoke-testing."""
    logger.info("TEST MODE — single small cycle")
    orchestrator.config.orchestrator.max_pipeline_per_cycle = 3
    orchestrator._run_cycle()
    cmd_status(orchestrator)


def main():
    parser = argparse.ArgumentParser(description=f"{project_meta.name} research pipeline")
    parser.add_argument("--status", action="store_true", help="Show DB stats and exit")
    parser.add_argument("--test", action="store_true", help="Run one small cycle and exit")
    parser.add_argument("--search", metavar="QUERY", help="Semantic search and exit")
    args = parser.parse_args()

    orchestrator, db, llm, vs = build_components()

    if args.status:
        cmd_status(orchestrator)
    elif args.search:
        cmd_search(orchestrator, args.search)
    elif args.test:
        cmd_test(orchestrator)
    else:
        orchestrator.run()


if __name__ == "__main__":
    main()
