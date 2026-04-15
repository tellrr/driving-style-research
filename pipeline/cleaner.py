"""Text cleaning — normalize article content before feeding to the LLM."""

import re
import unicodedata

import trafilatura


def clean_text(text: str, max_chars: int = 8000) -> str:
    """Normalize whitespace, remove control characters, truncate."""
    if not text:
        return ""
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Remove non-printable control characters (keep newlines/tabs)
    text = re.sub(r"[^\S\n\t ]+", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


def extract_from_url(url: str) -> str | None:
    """Download and extract main text content from a URL using trafilatura."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        return clean_text(text) if text else None
    except Exception:
        return None


def build_llm_context(title: str, abstract: str, full_text: str | None,
                      max_abstract: int = 2000, max_full_text: int = 5000) -> str:
    """Build a compact text block to feed to the LLM."""
    parts = [f"Title: {title.strip()}"]
    if abstract:
        parts.append(f"Abstract: {clean_text(abstract, max_abstract)}")
    if full_text:
        parts.append(f"Content excerpt:\n{clean_text(full_text, max_full_text)}")
    return "\n\n".join(parts)
