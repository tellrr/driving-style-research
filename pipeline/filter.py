"""Relevance filtering — decides if an article belongs in the research corpus.

The SYSTEM prompt is built dynamically from config/topic_config.md so this file
works correctly for any research topic without modification.
"""

from loguru import logger

from config.settings import project_meta
from llm.client import OllamaClient
from models import Article
from pipeline.cleaner import build_llm_context


def _build_system() -> str:
    domain = project_meta.domain_summary or f"the configured research topic: {project_meta.name}"
    relevant = project_meta.relevant_topics or "topics directly related to the research"
    irrelevant = project_meta.irrelevant_topics or "unrelated or tangential topics"
    return f"""You are a research relevance filter for a study on {domain}.
You decide if an article is relevant to this research.

Relevant topics include: {relevant}

Irrelevant: {irrelevant}

You MUST respond with valid JSON only."""


SYSTEM = _build_system()

USER_TEMPLATE = """{context}

Is this article relevant to this research project?
Respond with JSON: {{"relevant": true or false, "score": 0.0 to 1.0, "reason": "one sentence"}}"""


def filter_article(
    article: Article,
    client: OllamaClient,
    threshold: float = 0.55,
) -> tuple[bool, float, str]:
    """
    Returns (is_relevant, score, reason).
    score is 0.0–1.0; articles below threshold are marked filtered_out.
    """
    context = build_llm_context(article.title, article.abstract, None)

    try:
        result = client.chat_json(
            system=SYSTEM,
            user=USER_TEMPLATE.format(context=context),
        )
        score = float(result.get("score", 0.0))
        relevant = bool(result.get("relevant", score >= threshold))
        reason = str(result.get("reason", ""))

        # Override if score contradicts boolean
        if score < threshold:
            relevant = False

        logger.debug(
            f"Filter [{score:.2f}] {'KEEP' if relevant else 'DROP'}: {article.title[:60]}"
        )
        return relevant, score, reason

    except Exception as e:
        logger.warning(f"Filter failed for {article.id}: {e} — defaulting to keep")
        return True, 0.5, "filter error — kept by default"
