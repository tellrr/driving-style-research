"""Subtopic categorization — assigns one or more research subtopics to an article.

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
    return f"""You are a research categorizer for {name}.
Assign the most relevant subtopics from the provided list to the given article.
Choose 1–4 subtopics. Only use names from the provided list exactly as written.
You MUST respond with valid JSON only."""


SYSTEM = _build_system()

USER_TEMPLATE = """{context}

Available subtopics:
{subtopics}

Which subtopics does this article belong to?
Respond with JSON: {{"subtopics": ["Subtopic Name 1", "Subtopic Name 2"]}}"""


def categorize_article(
    article: Article,
    client: OllamaClient,
    subtopic_names: list[str],
) -> list[str]:
    """
    Returns list of matching subtopic names from subtopic_names.
    Falls back to empty list on failure.
    """
    context = build_llm_context(article.title, article.abstract, None)
    subtopics_block = "\n".join(f"- {name}" for name in subtopic_names)

    try:
        result = client.chat_json(
            system=SYSTEM,
            user=USER_TEMPLATE.format(context=context, subtopics=subtopics_block),
        )
        assigned = result.get("subtopics", [])
        # Validate — only accept names that actually exist in the list
        valid = [s for s in assigned if s in subtopic_names]
        if not valid and assigned:
            # Fuzzy fallback: partial match
            assigned_lower = [s.lower() for s in assigned]
            valid = [
                name for name in subtopic_names
                if any(a in name.lower() or name.lower() in a for a in assigned_lower)
            ]
        logger.debug(f"Categorized '{article.title[:50]}' → {valid}")
        return valid

    except Exception as e:
        logger.warning(f"Categorize failed for {article.id}: {e}")
        return []
