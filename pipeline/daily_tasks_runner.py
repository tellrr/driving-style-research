"""
daily_tasks_runner.py — Runs configured daily generation tasks.

Called by the orchestrator immediately after the strategic report is written.
For each enabled task in config/daily_tasks.yaml it:
  1. Extracts the configured section(s) from today's strategic report
  2. Optionally loads the most recent previous HTML output for continuity
  3. Calls Claude API with the filled prompt template
  4. Saves the HTML to reports/daily/YYYY-MM-DD_{task_name}.html
  5. Pushes the HTML to the Research Dashboard via cloud_sync

Add new daily tasks purely through config/daily_tasks.yaml — no code changes needed.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv
from loguru import logger

from pipeline import cloud_sync

ROOT = Path(__file__).parent.parent
ENV_PATH = Path(__file__).parent / ".env"
TASKS_CONFIG = ROOT / "config" / "daily_tasks.yaml"
DAILY_REPORTS_DIR = ROOT / "reports" / "daily"
STRATEGIC_REPORTS_DIR = ROOT / "reports" / "strategic"

load_dotenv(ENV_PATH)

CLAUDE_MODELS = {
    "claude-sonnet": "claude-sonnet-4-6",
    "claude-opus": "claude-opus-4-6",
}


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

def _extract_sections(report_md: str, section_headings: list[str]) -> str:
    """
    Extract content for each listed heading from the report markdown.
    Matches from the heading line to the next heading of the same or higher level.
    Returns concatenated content of all matched sections.
    """
    extracted = []
    for heading in section_headings:
        # Determine heading level from leading #s in the config string
        level = len(heading) - len(heading.lstrip("#"))
        if level == 0:
            level = 2  # default to ##

        # Build a regex that finds this heading and captures until the next same/higher level
        escaped = re.escape(heading.strip())
        # Match the heading line itself (any amount of leading #s matching config)
        hashes = "#" * level
        pattern = rf"(?m)^{hashes}[^#].*?{re.escape(heading.strip().lstrip('#').strip())}.*?$"

        # Find the heading position
        match = re.search(pattern, report_md, re.IGNORECASE)
        if not match:
            # Fallback: search by the text content without the hashes
            text_only = heading.strip().lstrip("#").strip()
            match = re.search(
                rf"(?m)^#{{{level},}}\s+{re.escape(text_only)}\s*$",
                report_md,
                re.IGNORECASE,
            )

        if not match:
            logger.debug(f"daily_tasks: section not found: {heading!r}")
            continue

        start = match.start()
        # Find the next heading of same or higher level after the matched heading
        next_heading_pattern = rf"(?m)^#{{{1},{level}}}\s"
        end_match = re.search(next_heading_pattern, report_md[match.end():])
        if end_match:
            end = match.end() + end_match.start()
        else:
            end = len(report_md)

        section_content = report_md[start:end].strip()
        extracted.append(section_content)
        logger.debug(f"daily_tasks: extracted {len(section_content)} chars for {heading!r}")

    return "\n\n---\n\n".join(extracted) if extracted else ""


# ---------------------------------------------------------------------------
# Previous output loader
# ---------------------------------------------------------------------------

def _load_previous_output(task_name: str, today: str) -> str:
    """
    Find the most recent previous HTML output for this task (before today).
    Returns the HTML string, or empty string if none found.
    """
    DAILY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    candidates = sorted(DAILY_REPORTS_DIR.glob(f"*_{task_name}.html"), reverse=True)
    for path in candidates:
        # Extract date prefix from filename
        stem = path.stem  # e.g. "2026-04-11_app-mockup"
        date_prefix = stem.split("_")[0]
        if date_prefix < today:  # strictly before today
            try:
                content = path.read_text(encoding="utf-8")
                logger.debug(f"daily_tasks: loaded previous output from {path.name} ({len(content)} chars)")
                # Truncate very large previous outputs to stay within context limits
                if len(content) > 55000:
                    content = content[:55000] + "\n<!-- (truncated for context length) -->\n"
                return content
            except Exception as e:
                logger.warning(f"daily_tasks: could not read {path}: {e}")
    return ""


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_claude(prompt: str, model_key: str, max_tokens: int) -> str:
    api_key = os.getenv("CLAUDE_API_KEY", "")
    if not api_key:
        raise ValueError("CLAUDE_API_KEY not set in pipeline/.env")

    model = CLAUDE_MODELS.get(model_key, CLAUDE_MODELS["claude-sonnet"])
    client = Anthropic(api_key=api_key)

    logger.info(f"daily_tasks: calling {model} (max_tokens={max_tokens})")
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "max_tokens":
        logger.warning(
            f"daily_tasks: response truncated by max_tokens={max_tokens} — "
            f"increase max_tokens in config/daily_tasks.yaml"
        )

    text = message.content[0].text.strip()

    # Strip markdown fences if the model added them despite instructions
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.rstrip())

    return text


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_daily_tasks(date: str) -> None:
    """
    Run all enabled daily tasks for the given date.
    Reads today's strategic report, generates outputs, saves and pushes them.

    Args:
        date: ISO date string, e.g. "2026-04-12"
    """
    # Load task config
    if not TASKS_CONFIG.exists():
        logger.debug("daily_tasks: config/daily_tasks.yaml not found, skipping")
        return

    with TASKS_CONFIG.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    tasks = config.get("tasks", [])
    if not tasks:
        logger.debug("daily_tasks: no tasks configured")
        return

    # Load today's strategic report
    report_path = STRATEGIC_REPORTS_DIR / f"{date}.md"
    if not report_path.exists():
        logger.warning(f"daily_tasks: strategic report not found for {date}, skipping")
        return

    report_md = report_path.read_text(encoding="utf-8")
    logger.info(f"daily_tasks: running tasks for {date} ({len(report_md)} char report)")

    DAILY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    for task in tasks:
        if not task.get("enabled", True):
            continue

        name = task["name"]
        title = task.get("title", name)
        logger.info(f"daily_tasks: running task '{name}'")

        try:
            # 1. Extract source sections
            source_sections = task.get("source_sections", [])
            source = _extract_sections(report_md, source_sections) if source_sections else report_md

            if not source:
                logger.warning(f"daily_tasks: no source content extracted for '{name}', skipping")
                continue

            # 2. Load previous output
            previous = ""
            if task.get("use_previous", False):
                previous = _load_previous_output(name, date)

            # 3. Fill prompt template
            prompt_template = task.get("prompt", "")
            prompt = (
                prompt_template
                .replace("{{source}}", source)
                .replace("{{previous}}", previous if previous else "(no previous output)")
                .replace("{{date}}", date)
            )

            # 4. Call LLM
            llm = task.get("llm", "claude-sonnet")
            max_tokens = task.get("max_tokens", 6000)
            html = _call_claude(prompt, llm, max_tokens)

            if not html.lstrip().startswith("<!"):
                logger.warning(f"daily_tasks: output for '{name}' does not look like HTML, skipping")
                logger.debug(f"Output starts with: {html[:200]}")
                continue

            # 5. Save locally
            output_path = DAILY_REPORTS_DIR / f"{date}_{name}.html"
            output_path.write_text(html, encoding="utf-8")
            logger.info(f"daily_tasks: saved {output_path.name} ({len(html):,} chars)")

            # 6. Push to dashboard
            pushed = cloud_sync.sync_output(date, name, title, output_path)
            if pushed:
                logger.info(f"daily_tasks: '{name}' pushed to dashboard")
            else:
                logger.debug(f"daily_tasks: '{name}' push skipped (dashboard not configured)")

        except Exception as e:
            logger.error(f"daily_tasks: task '{name}' failed: {e}", exc_info=True)
            # Continue with next task — don't let one failure block others
