"""
Strategic daily synthesis using Claude Opus 4.6.

Called by the orchestrator after the first scraping cycle that completes after 3 AM.
Reads all processed articles since the last strategic report, reads the previous
report for continuity, and produces:
  - Progress assessment per configured pillar (defined in config/topic_config.md)
  - Suggested new search keywords (written to data/suggested_keywords.json)

The report goal, pillars, and domain are all read from config/topic_config.md —
no changes to this file are required when setting up a new research project.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from config.settings import project_meta
from models import Article
from pipeline.stats_tracker import record_snapshot
from pipeline.stats_generator import generate_stats_html
from pipeline import cloud_sync
from storage.db import Database

ROOT = Path(__file__).parent.parent
STRATEGIC_REPORTS_DIR = ROOT / "reports" / "strategic"
DAILY_REPORTS_DIR = ROOT / "reports" / "daily"
SUGGESTED_KW_PATH = ROOT / "data" / "suggested_keywords.json"
ENV_PATH = Path(__file__).parent / ".env"

SYSTEM = """You are a strategic research analyst guiding the development of a novel product
or research initiative. You synthesize academic findings into concise, actionable progress
reports. Be specific: cite individual papers by title and URL where relevant. Identify gaps
clearly. Format your output in well-structured markdown."""

MAX_ARTICLES_TO_INCLUDE = 80   # cap to control token cost
MAX_ABSTRACT_CHARS = 400       # per article in the prompt


def _build_pillar_table_rows() -> str:
    """Build the pillar table rows for the USER_TEMPLATE from configured pillars."""
    pillars = project_meta.pillars
    if not pillars:
        return "| Research progress | X% | ... |"
    rows = [f"| {pillar} | X% | ... |" for pillar in pillars]
    return "\n".join(rows)


def _build_user_template(goal: str) -> str:
    pillar_rows = _build_pillar_table_rows()
    pillar_names = " / ".join(project_meta.pillars) if project_meta.pillars else "research pillars"

    return f"""\
## Previous Strategic Report
{{previous_report}}

---

## New Articles Processed Since Last Report ({{n}} articles)

{{articles_block}}

---

## Project Goal
{goal}

---

## Your Task

Produce a strategic research report with the following sections:

### 1. Progress by Pillar
For each pillar, assess progress on a 0–100% scale and briefly summarize
what has been found so far. Cite specific papers (title + URL) where relevant.

| Pillar | Progress | Status summary |
|--------|----------|----------------|
{pillar_rows}

### 2. Key Gaps
For each pillar, what is the most critical still-missing piece of knowledge?

### 3. Promising Leads
Which of the new articles above are most directly actionable? List up to 5 with
a one-line note on why each matters.

### 4. Overall Strategic Position
In 2–3 sentences: how close are we to having enough research to move forward?
What is the single biggest blocker right now?

### 5. Suggested Search Directions
List 8–12 specific search keywords or phrases that would fill the gaps identified above.
Focus on areas where we have weak coverage. Then output them as a JSON block so the
scraper can pick them up automatically:

```json
{{"suggested_keywords": ["keyword 1", "keyword 2", ...]}}
```

### 6. What Would You Build?
Based **only** on the research evidence collected so far — not what you wish existed —
describe concretely what you would build or do **today**:

- **Ready now:** What 2–3 ideas are scientifically ready to act on right now?
- **What to defer:** Which pillar ideas must wait because research is too thin?
- **Biggest insight:** What is the single most surprising or counterintuitive finding
  that should directly shape design or strategy?

### 7. Report & Graph Suggestions
Based **only** on the research collected so far, suggest 6–10 specific reports and
graphs that a fleet telematics platform should include. For each:
- **Name & type** — report or graph name, chart type (line, bar, gauge, scatter, heat map, table…)
- **Key dimensions** — axes, groupings, or breakdowns that make it meaningful
- **Research basis** — cite 1–2 specific papers / findings that justify this metric
- **Audience** — fleet manager / driver / operations director
"""


def run_strategic_report(db: Database, reports_dir: Path | None = None) -> list[str]:
    """
    Build and save the daily strategic report.

    Returns the list of suggested keywords extracted from the response
    (empty list if the report fails or produces none).
    """
    load_dotenv(ENV_PATH)
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logger.error("CLAUDE_API_KEY not set — cannot run strategic report")
        return []

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed — run: pip install anthropic")
        return []

    reports_dir = reports_dir or STRATEGIC_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ── Previous report ────────────────────────────────────────────────────
    previous_report = _load_previous_report(reports_dir)

    # ── Articles since last report ─────────────────────────────────────────
    last_run = _last_run_timestamp(reports_dir)
    articles = db.get_processed_since(last_run)
    logger.info(f"Strategic report: {len(articles)} new articles since {last_run[:16]}")

    if not articles and not previous_report:
        logger.info("No articles and no previous report — skipping strategic synthesis")
        return []

    # Cap and build the articles block
    top_articles = articles[:MAX_ARTICLES_TO_INCLUDE]
    articles_block = _build_articles_block(top_articles)

    # ── Build prompt from project_meta ─────────────────────────────────────
    goal = project_meta.goal or f"Research project: {project_meta.name}"
    user_template = _build_user_template(goal)
    user_msg = (
        user_template
        .replace("{previous_report}", previous_report or "*No previous report — this is the first run.*")
        .replace("{n}", str(len(top_articles)))
        .replace("{articles_block}", articles_block)
    )

    # ── Call Opus 4.6 ──────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    logger.info("Calling Claude Opus 4.6 for strategic synthesis...")
    try:
        messages = [{"role": "user", "content": user_msg}]
        content_parts = []

        for attempt in range(4):  # initial + up to 3 continuations
            chunk_parts = []
            stop_reason = None
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=32768,
                system=SYSTEM,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    chunk_parts.append(text)
                stop_reason = stream.get_final_message().stop_reason

            partial = "".join(chunk_parts)
            content_parts.append(partial)

            if stop_reason != "max_tokens":
                break

            logger.warning(
                f"Strategic report truncated (attempt {attempt + 1}), "
                "sending continuation request..."
            )
            messages.append({"role": "assistant", "content": partial})
            messages.append({
                "role": "user",
                "content": "Your response was cut off. Continue exactly where you stopped.",
            })

        content = "".join(content_parts)
    except Exception as e:
        logger.error(f"Opus API call failed: {e}")
        return []

    # ── Save report ────────────────────────────────────────────────────────
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = reports_dir / f"{today}.md"
    header = (
        f"# Strategic Report — {today}\n"
        f"*Articles included: {len(top_articles)} | "
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n\n---\n\n"
    )
    report_path.write_text(header + content, encoding="utf-8")
    logger.info(f"Strategic report saved: {report_path}")

    # ── Extract and persist suggested keywords ────────────────────────────
    suggested = _extract_suggested_keywords(content)
    if suggested:
        _save_suggested_keywords(suggested)
        logger.info(f"Suggested keywords updated: {len(suggested)} terms")

    # ── Generate Report & Graph Suggestions HTML ───────────────────────────
    try:
        _generate_report_graph_html(content, today, client)
    except Exception as e:
        logger.warning(f"Report & Graph Suggestions HTML generation failed (non-fatal): {e}")

    # ── Record pillar history and regenerate stats dashboard ──────────────
    try:
        snapshot = record_snapshot(content, db)
        stats_path = generate_stats_html()
        logger.info(
            f"Stats dashboard updated: {stats_path} "
            f"(pillars: {snapshot['pillars']})"
        )
    except Exception as e:
        logger.warning(f"Stats update failed (non-fatal): {e}")

    return suggested


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_previous_report(reports_dir: Path) -> str:
    """Return the most recent strategic report text, or empty string if none."""
    reports = sorted(reports_dir.glob("*.md"))
    if not reports:
        return ""
    latest = reports[-1]
    try:
        text = latest.read_text(encoding="utf-8")
        # Trim to avoid ballooning the prompt with huge historical reports
        if len(text) > 8000:
            text = text[:8000] + "\n\n*[truncated for brevity]*"
        return text
    except Exception:
        return ""


def _last_run_timestamp(reports_dir: Path) -> str:
    """Return ISO timestamp of when the last strategic report was created, or epoch."""
    reports = sorted(reports_dir.glob("*.md"))
    if not reports:
        return "2000-01-01T00:00:00+00:00"
    last_date = reports[-1].stem  # "2026-04-03"
    return f"{last_date}T00:00:00+00:00"


def _build_articles_block(articles: list[Article]) -> str:
    parts = []
    for i, a in enumerate(articles, 1):
        abstract = (a.abstract or "")[:MAX_ABSTRACT_CHARS]
        if len(a.abstract or "") > MAX_ABSTRACT_CHARS:
            abstract += "…"
        findings = ""
        if a.key_findings:
            findings = "\n  Key findings: " + " | ".join(a.key_findings[:3])
        topics = ", ".join(a.subtopics) if a.subtopics else "uncategorized"
        parts.append(
            f"**[{i}] {a.title}**\n"
            f"  URL: {a.source_url}\n"
            f"  Score: {a.relevance_score:.2f} | Topics: {topics}\n"
            f"  {abstract}{findings}"
        )
    return "\n\n".join(parts) if parts else "*No new articles in this period.*"


def _extract_suggested_keywords(text: str) -> list[str]:
    """Parse the ```json ... ``` block from the Opus response."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        kws = data.get("suggested_keywords", [])
        return [str(k).strip() for k in kws if k and str(k).strip()]
    except (json.JSONDecodeError, KeyError):
        return []


def _save_suggested_keywords(keywords: list[str]):
    """Write suggested keywords to the shared JSON file for the scraper to blend in."""
    SUGGESTED_KW_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if SUGGESTED_KW_PATH.exists():
        try:
            existing = json.loads(SUGGESTED_KW_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Merge: keep existing, add new ones (deduplicated, preserve order)
    seen = {k.lower() for k in existing}
    merged = existing + [k for k in keywords if k.lower() not in seen]
    SUGGESTED_KW_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")


_REPORT_GRAPH_SYSTEM = (
    "You are a senior data-visualisation engineer and fleet telematics product designer. "
    "You produce clean, self-contained HTML gallery pages that showcase dashboard report "
    "and graph suggestions. All CSS is embedded; zero external dependencies."
)

_REPORT_GRAPH_HTML_PROMPT = """\
You are maintaining an evolving HTML gallery of fleet telematics report and graph
suggestions. Today's research has produced an updated list of suggestions.

## Today's research guidance
{suggestions}

## Your previous gallery (base — preserve ALL existing cards unless explicitly merged)
{previous}

## UI design inspiration from full-screen mockups (extract ideas, not screens)
{mockup_inspiration}

## Curation rules — the gallery must only grow, never shrink
**CRITICAL: The total number of cards must be ≥ the number of cards in the previous gallery.**

Apply these rules in order:

1. KEEP: Carry forward every existing card unchanged unless it is being merged.
2. DEDUPLICATE: If two cards are near-identical (same metric, same view), merge them into ONE
   richer card. The surviving card absorbs all dimensions/research from both. Net count stays the same.
3. UPDATE: Refine an existing card in place (better thresholds, stronger research, new dimension).
   Never remove a card — update it.
4. ADD: If today's research introduces a concept not yet in the gallery, add a new card.
5. If no previous gallery exists, design from scratch using today's guidance.

The gallery represents the full evolving body of knowledge — ideas are added and refined, never deleted.

## Output requirements
Return ONLY raw HTML — no markdown fences, no explanation.

Page structure and design system:
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Report & Graph Suggestions · {date}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #070a10; color: #e2e8f0; font-family: system-ui, sans-serif;
           padding: 2rem 1.5rem; }}
    h1 {{ font-size: 1.5rem; font-weight: 700; color: #e2e8f0; margin-bottom: 0.4rem; }}
    .meta {{ color: #64748b; font-size: 0.875rem; margin-bottom: 2rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
             gap: 1.75rem; }}
    .card {{ background: #0f1117; border: 1px solid #2d3748; border-radius: 12px;
             padding: 1.25rem; display: flex; flex-direction: column; gap: 0.75rem; }}
    .card-title {{ font-size: 1rem; font-weight: 600; color: #e2e8f0; }}
    .badge {{ display: inline-block; background: #1e293b; color: #6c8fff;
              border: 1px solid #334155; border-radius: 6px; font-size: 0.7rem;
              padding: 0.2rem 0.55rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .preview {{ background: #1a1d27; border-radius: 8px; padding: 1rem;
                min-height: 140px; display: flex; align-items: center;
                justify-content: center; }}
    .dimensions {{ font-size: 0.8rem; color: #94a3b8; }}
    .basis {{ font-size: 0.8rem; color: #64748b; font-style: italic; }}
    .audience {{ font-size: 0.75rem; color: #34d399; font-weight: 500; }}
  </style>
</head>
<body>
  <h1>Report &amp; Graph Suggestions</h1>
  <p class="meta">Evolving design · updated from daily research · {date}</p>
  <div class="grid">
    <!-- one card per report/graph: -->
    <div class="card">
      <div class="card-title">[Report / Graph name]</div>
      <div><span class="badge">[chart type]</span></div>
      <div class="preview">
        <!-- SVG inline preview — a realistic miniature chart using CSS color tokens:
             accent #6c8fff, safe #34d399, warn #fbbf24, danger #f87171 -->
      </div>
      <div class="dimensions"><strong>Dimensions:</strong> [axes, groupings]</div>
      <div class="basis"><strong>Research basis:</strong> [paper / finding]</div>
      <div class="audience"><strong>Audience:</strong> [fleet manager / driver / ops]</div>
    </div>
  </div>
</body>
</html>

Rules:
- Apply the curation rules above — result must be a clean, non-redundant set
- Each card MUST include an SVG inline chart preview (bar, line, gauge, scatter, heat map…)
  that looks like a realistic miniature of the actual chart — not a placeholder box
- Use realistic fleet telematics values in SVGs (scores 0-100, G-force 0.1-1.2g, km/h, dates)
- Color code consistently: green = safe/good, yellow = warning, red = critical
- All CSS inline or in the embedded <style> — no external resources
"""


def _extract_section(content: str, heading: str) -> str:
    """Extract a markdown section by heading text regardless of heading level (#–###)."""
    clean = re.escape(heading.lstrip("# ").strip())
    pattern = re.compile(
        rf"(#{{1,6}}\s+{clean}.*?)(?=\n#{{1,2}}\s|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(content)
    return m.group(1).strip() if m else ""


def _load_previous_report_graph_html(today: str) -> str:
    """Return the most recent *_report-graph-suggestions.html before today, or empty string."""
    if not DAILY_REPORTS_DIR.exists():
        return ""
    candidates = sorted(DAILY_REPORTS_DIR.glob("*_report-graph-suggestions.html"), reverse=True)
    for path in candidates:
        date_prefix = path.stem.split("_")[0]
        if date_prefix < today:
            try:
                content = path.read_text(encoding="utf-8")
                # Truncate to stay within context limits
                if len(content) > 55000:
                    content = content[:55000] + "\n<!-- (truncated for context length) -->\n"
                logger.debug(f"Loaded previous report-graph HTML from {path.name} ({len(content):,} chars)")
                return content
            except Exception as e:
                logger.warning(f"Could not read previous report-graph HTML {path}: {e}")
    return ""


def _load_previous_mockup_html(today: str) -> str:
    """Return a brief text summary of screen names from the most recent *_report-mockup.html
    before today, so design ideas can be absorbed without inflating context."""
    if not DAILY_REPORTS_DIR.exists():
        return ""
    candidates = sorted(DAILY_REPORTS_DIR.glob("*_report-mockup.html"), reverse=True)
    for path in candidates:
        date_prefix = path.stem.split("_")[0]
        if date_prefix < today:
            try:
                content = path.read_text(encoding="utf-8")
                # Extract screen-label texts as a compact list of UI screen titles
                labels = re.findall(r'class="screen-label"[^>]*>([^<]+)<', content)
                if labels:
                    summary = "\n".join(f"- {lbl.strip()}" for lbl in labels)
                    logger.debug(f"Loaded mockup screen list from {path.name} ({len(labels)} screens)")
                    return (
                        f"Previous UI mockup screens from {date_prefix} "
                        f"(incorporate concepts not already covered by the card gallery):\n{summary}"
                    )
            except Exception as e:
                logger.warning(f"Could not read previous mockup HTML {path}: {e}")
    return ""


def _generate_report_graph_html(report_content: str, today: str, client) -> None:
    """
    Extract the 'Report & Graph Suggestions' section from the Opus report,
    call Claude Sonnet to generate/evolve a styled HTML gallery, and save it to
    reports/daily/YYYY-MM-DD_report-graph-suggestions.html.
    Loads the previous day's output so the gallery evolves incrementally.
    Uses continuation requests if the response is truncated at max_tokens.
    """
    suggestions = _extract_section(report_content, "7. Report & Graph Suggestions")
    if not suggestions:
        logger.warning("No 'Report & Graph Suggestions' section found in report — skipping HTML generation")
        return

    previous = _load_previous_report_graph_html(today)
    mockup_inspiration = _load_previous_mockup_html(today)
    user_msg = _REPORT_GRAPH_HTML_PROMPT.format(
        suggestions=suggestions,
        date=today,
        previous=previous if previous else "(no previous gallery — design from scratch)",
        mockup_inspiration=mockup_inspiration if mockup_inspiration else "(none)",
    )

    try:
        messages: list[dict] = [{"role": "user", "content": user_msg}]
        html_parts: list[str] = []

        for attempt in range(4):  # initial + up to 3 continuations
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=32768,
                system=_REPORT_GRAPH_SYSTEM,
                messages=messages,
            )
            chunk = message.content[0].text
            html_parts.append(chunk)

            if message.stop_reason != "max_tokens":
                break

            logger.warning(
                f"Report & Graph HTML truncated (attempt {attempt + 1}), sending continuation..."
            )
            messages.append({"role": "assistant", "content": chunk})
            messages.append({
                "role": "user",
                "content": "Your HTML was cut off. Continue exactly where you stopped, outputting only raw HTML.",
            })

        html = "".join(html_parts).strip()
    except Exception as e:
        logger.error(f"Sonnet call for Report & Graph Suggestions HTML failed: {e}")
        return

    if not html.lower().startswith("<!doctype"):
        logger.warning("Sonnet response did not start with <!DOCTYPE html> — skipping save")
        return

    # Validate the HTML is complete (not truncated)
    if not re.search(r'</html\s*>', html, re.IGNORECASE):
        logger.warning("Report & Graph HTML appears truncated (no </html>) — saving anyway but flagging")

    DAILY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DAILY_REPORTS_DIR / f"{today}_report-graph-suggestions.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info(f"Report & Graph Suggestions HTML saved: {out_path}")

    pushed = cloud_sync.sync_output(today, "report-graph-suggestions", "Report & Graph Suggestions", out_path)
    if pushed:
        logger.info("cloud_sync: Report & Graph Suggestions pushed to dashboard")
