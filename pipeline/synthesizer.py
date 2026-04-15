"""Synthesizer — cross-paper analysis run nightly/weekly per subtopic.

The SYSTEM prompt is built dynamically from config/topic_config.md so this file
works correctly for any research topic without modification.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from config.settings import project_meta
from llm.client import OllamaClient
from models import Article, SynthesisRun


def _build_system() -> str:
    name = project_meta.name or "the configured research topic"
    product = project_meta.product_short or "the planned product or research output"
    return f"""You are a research synthesizer for {name}.
You analyze multiple research summaries and produce a structured synthesis report
aimed at informing the development of {product}.
Write in clear, analytical prose using markdown formatting."""


def _build_user_template() -> str:
    # Build pillar references from configured pillars (if any)
    pillar_names = project_meta.pillars
    if pillar_names:
        pillar_list = ", ".join(pillar_names)
        pillar_hint = f"**Implications for the research goal** ({pillar_list})"
    else:
        pillar_hint = "**Implications for the research goal**"

    return f"""Below are summaries of {{n}} research papers on the subtopic:
**{{subtopic}}**

---
{{summaries}}
---

Write a synthesis report covering:
1. **Main themes and consensus findings**
2. **Conflicting or debated points**
3. **Key gaps in the research**
4. {pillar_hint}

Be specific and cite individual findings where relevant. Use markdown."""


SYSTEM = _build_system()
USER_TEMPLATE = _build_user_template()


def synthesize_subtopic(
    subtopic: str,
    articles: list[Article],
    client: OllamaClient,
    run_type: str = "daily",
    reports_dir: Path | None = None,
) -> SynthesisRun | None:
    """
    Synthesize summaries for a subtopic. Saves a markdown report to disk.
    Returns a SynthesisRun or None if no articles.
    """
    # Filter to articles that have summaries and belong to this subtopic
    relevant = [
        a for a in articles
        if a.summary and (subtopic in a.subtopics or not a.subtopics)
    ]
    if not relevant:
        logger.debug(f"No summarized articles for subtopic '{subtopic}'")
        return None

    summaries_block = _build_summaries_block(relevant)
    now = datetime.now(timezone.utc).isoformat()

    try:
        content = client.chat(
            system=SYSTEM,
            user=USER_TEMPLATE.format(
                n=len(relevant),
                subtopic=subtopic,
                summaries=summaries_block,
            ),
            model=client.synthesis_model,
            json_output=False,
        )

        run = SynthesisRun(
            id=hashlib.sha256(f"{subtopic}:{now}".encode()).hexdigest()[:16],
            subtopic=subtopic,
            run_type=run_type,
            content=content,
            articles_included=len(relevant),
            created_at=now,
        )

        if reports_dir:
            _save_report(run, reports_dir)

        logger.info(f"Synthesized '{subtopic}' — {len(relevant)} articles")
        return run

    except Exception as e:
        logger.error(f"Synthesis failed for '{subtopic}': {e}")
        return None


def _build_summaries_block(articles: list[Article]) -> str:
    parts = []
    for i, a in enumerate(articles, 1):
        findings = "\n".join(f"  - {f}" for f in a.key_findings) if a.key_findings else ""
        part = f"**[{i}] {a.title}**\n{a.summary}"
        if findings:
            part += f"\nKey findings:\n{findings}"
        if a.source_url:
            part += f"\nSource: {a.source_url}"
        parts.append(part)
    return "\n\n---\n\n".join(parts)


def _save_report(run: SynthesisRun, reports_dir: Path):
    reports_dir.mkdir(parents=True, exist_ok=True)
    safe_name = run.subtopic.replace(" ", "_").replace("/", "-")[:60]
    filename = f"{run.created_at[:10]}_{run.run_type}_{safe_name}.md"
    path = reports_dir / filename
    header = (
        f"# Synthesis: {run.subtopic}\n"
        f"**Type:** {run.run_type} | "
        f"**Articles:** {run.articles_included} | "
        f"**Date:** {run.created_at[:19]}\n\n---\n\n"
    )
    path.write_text(header + run.content, encoding="utf-8")
    logger.info(f"Report saved: {path}")
