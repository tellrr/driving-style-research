"""Summarizer — produces structured summaries and key findings per article.

The SYSTEM prompt is built dynamically from config/topic_config.md so this file
works correctly for any research topic without modification.
"""

from loguru import logger

from config.settings import project_meta
from llm.client import OllamaClient
from models import Article
from pipeline.cleaner import build_llm_context


def _build_system() -> str:
    name = project_meta.name or "the configured research topic"
    product = project_meta.product_short or "the planned product or research output"
    return f"""You are a research summarizer specializing in {name}.
Produce concise, informative summaries that capture the most useful findings
for building {product}.
You MUST respond with valid JSON only."""


SYSTEM = _build_system()

USER_TEMPLATE = """{context}

Summarize this research article.
Respond with JSON:
{{
  "summary": "3–5 sentence summary of the study, methods, and findings",
  "key_findings": [
    "Specific finding 1",
    "Specific finding 2",
    "Specific finding 3"
  ],
  "app_relevance": "1–2 sentences on how this could inform the product or research goal"
}}"""


def summarize_article(
    article: Article,
    client: OllamaClient,
    max_abstract: int = 2000,
    max_full_text: int = 5000,
) -> tuple[str, list[str], str]:
    """
    Returns (summary, key_findings, app_relevance).
    Falls back to abstract-only summary on failure.
    """
    context = build_llm_context(
        article.title,
        article.abstract,
        article.full_text,
        max_abstract=max_abstract,
        max_full_text=max_full_text,
    )

    try:
        result = client.chat_json(
            system=SYSTEM,
            user=USER_TEMPLATE.format(context=context),
        )
        summary = str(result.get("summary", "")).strip()
        key_findings = [str(f).strip() for f in result.get("key_findings", []) if f]
        app_relevance = str(result.get("app_relevance", "")).strip()

        if not summary:
            summary = article.abstract[:500]

        logger.debug(f"Summarized: {article.title[:60]}")
        return summary, key_findings, app_relevance

    except Exception as e:
        logger.warning(f"Summarize failed for {article.id}: {e}")
        fallback = article.abstract[:500] if article.abstract else article.title
        return fallback, [], ""
