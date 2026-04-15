# Research Pipeline — Setup Guide

This template creates a **fully automated research pipeline** that:
1. Continuously scrapes OpenAlex, arXiv, PubMed, GitHub, RSS/web, and DuckDuckGo
2. Uses a local Ollama LLM to filter, categorize, and summarize articles
3. Generates a **daily strategic report** using Claude Opus 4.6 (Anthropic API)
4. Publishes status, reports, and custom HTML outputs to a hosted Research Dashboard
5. Tracks configurable research pillars with 0–100% progress scores over time

**Everything is configured through two files: `config/topic_config.md` and `pipeline/.env`.**
No Python code needs to be edited for a standard setup.

---

## Prerequisites

Before starting, make sure you have:

- **Python 3.11+** — `python --version`
- **Ollama** running locally — `ollama serve` — [install here](https://ollama.ai)
- **Required Ollama models:**
  ```
  ollama pull qwen3.5:4b
  ollama pull nomic-embed-text
  ```
- **Anthropic API key** — from [console.anthropic.com](https://console.anthropic.com/)
- (Optional) A **Research Dashboard** instance — see the [research-dashboard repo](../research-dashboard)

---

## Setup Checklist

### Step 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 2 — Configure your research topic

Edit **`config/topic_config.md`**. This is the only file you need to customize.
It has five sections — fill in each one:

#### 2a. Project title (first `#` heading)
Change the title to your research project name.

#### 2b. `## Project Goal`
Write 3–8 sentences describing what you are researching or building.
This text is sent verbatim to Claude Opus in every daily report.
Be specific: name the end product, the core innovation, and what success looks like.

#### 2c. `## Research Domain`
Fill in one or two sentences describing the domain (used in the relevance filter).
Then fill in the **Relevant topics include:** and **Irrelevant:** lines.
These tell the local LLM what to keep and what to discard.

#### 2d. `## Pillars`
Define 2–6 pillars that track progress toward your goal.
Each pillar gets a 0–100% score in every daily report and is graphed on the dashboard.
Format: `- Pillar Name: brief description`

#### 2e. `## Research Subtopics`
Define all research subtopics with keywords.
Each subtopic uses the format:
```markdown
### N. Subtopic Name
**Why:** [relevance explanation]

**Keywords:**
- keyword 1, keyword 2, keyword 3
- keyword 4, keyword 5
```
The scraper rotates through all keywords across all sources automatically.
Aim for 5–20 subtopics with 3–10 keywords each.

### Step 3 — Create the API key file

```bash
cp pipeline/.env.example pipeline/.env
```

Then edit `pipeline/.env`:
- Set `CLAUDE_API_KEY` to your Anthropic key
- (Optional) Set `DASHBOARD_API_URL` and `DASHBOARD_API_KEY` if you have a dashboard

### Step 4 — (Optional) Set up the Research Dashboard

If you want to publish results to the hosted dashboard:

1. Deploy a `research-dashboard` instance (see that repo's README)
2. Log in as admin → Projects → Create Project
3. Note the API key shown once at creation time
4. Fill in `DASHBOARD_API_URL` and `DASHBOARD_API_KEY` in `pipeline/.env`
5. Set the project's `brand_hsl` to a color for your project's dashboard tab

### Step 5 — (Optional) Configure daily tasks

Edit `config/daily_tasks.yaml` to add custom HTML outputs generated from each
day's strategic report.

Each task:
- Extracts sections from the daily report
- Calls Claude with a custom prompt
- Saves the HTML output and publishes it to the dashboard as a new tab

Uncomment and customize the example tasks in the file. See the comments in
that file for full field documentation. No code changes needed.

### Step 6 — Smoke test

Run a single cycle to verify everything works:

```bash
python run.py --test
```

This runs one scraping cycle + 3 pipeline articles and shows the DB stats.
Check that articles are being fetched and filtered correctly.

### Step 7 — Start the continuous pipeline

```bash
python run.py
```

Or use the provided script:
```bash
./StartResearch.bat   # Windows
```

The pipeline runs continuously. Each cycle:
1. **FETCH** — scrapes all sources with rotated keywords
2. **PIPELINE** — filters → categorizes → summarizes → embeds new articles
3. **SYNTHESIZE** — daily/weekly synthesis passes per subtopic (via local LLM)
4. **STRATEGIC REPORT** — once per day after 3 AM (via Claude Opus 4.6)
5. **DAILY TASKS** — custom HTML outputs generated from the strategic report
6. **SYNC** — status and reports pushed to the Research Dashboard

---

## File Structure

```
research-template/
├── SETUP.md                    ← this file
├── run.py                      ← entry point (python run.py)
├── orchestrator.py             ← main loop: fetch → pipeline → synthesize
├── models.py                   ← Article and SynthesisRun dataclasses
├── requirements.txt
│
├── config/
│   ├── topic_config.md         ← ★ CONFIGURE THIS for your research topic
│   ├── daily_tasks.yaml        ← ★ CONFIGURE THIS for custom daily outputs
│   └── settings.py             ← technical settings (models, timeouts, etc.)
│
├── pipeline/
│   ├── .env                    ← ★ CREATE THIS (copy from .env.example)
│   ├── .env.example            ← template for the above
│   ├── filter.py               ← relevance filter (prompt from topic_config.md)
│   ├── categorizer.py          ← subtopic assignment
│   ├── summarizer.py           ← article summarization
│   ├── synthesizer.py          ← nightly cross-paper synthesis
│   ├── strategic_report.py     ← daily Opus report (goal/pillars from topic_config.md)
│   ├── stats_tracker.py        ← pillar progress history (pillars from topic_config.md)
│   ├── stats_generator.py      ← local HTML stats dashboard
│   ├── cloud_sync.py           ← push to Research Dashboard
│   ├── daily_tasks_runner.py   ← runs config/daily_tasks.yaml
│   └── cleaner.py              ← text normalization
│
├── scraper/
│   ├── scheduler.py            ← coordinates all sources, rotates keywords
│   └── sources/
│       ├── openalex.py         ← OpenAlex API
│       ├── arxiv.py            ← arXiv API
│       ├── pubmed.py           ← PubMed/Entrez API
│       ├── github.py           ← GitHub search API
│       ├── web.py              ← RSS feeds + trafilatura full-text extraction
│       └── search.py           ← DuckDuckGo web search
│
├── llm/
│   └── client.py               ← Ollama HTTP client (filter/categorize/summarize/embed)
│
├── storage/
│   ├── db.py                   ← SQLite database (article status, synthesis runs)
│   └── vectorstore.py          ← ChromaDB vector store (semantic search)
│
├── data/                       ← auto-created, gitignored
│   ├── research.db             ← SQLite database
│   ├── chroma/                 ← ChromaDB vector store
│   ├── pillar_history.json     ← daily pillar progress history
│   └── suggested_keywords.json ← Opus-suggested search terms (fed back to scraper)
│
├── reports/                    ← auto-created, gitignored
│   ├── strategic/              ← YYYY-MM-DD.md — daily Opus reports
│   ├── daily/                  ← YYYY-MM-DD_{task-name}.html — daily task outputs
│   └── stats.html              ← local pillar progress dashboard
│
└── logs/                       ← auto-created, gitignored
    └── pipeline_YYYY-MM-DD.log
```

---

## How the topic_config.md → pipeline connection works

Everything flows from `config/topic_config.md`. Here is what each section drives:

| Section | Used by |
|---|---|
| `## Project Goal` | `strategic_report.py` — sent to Claude Opus as the project context |
| `## Research Domain` | `filter.py`, `categorizer.py`, `summarizer.py` — LLM system prompts |
| `## Pillars` | `strategic_report.py` (table rows), `stats_tracker.py` (history), `stats_generator.py` (chart), Research Dashboard (progress chart) |
| `## Research Subtopics` keywords | `scraper/scheduler.py` — all keywords fed to all sources |
| `## Research Subtopics` names | `categorizer.py` — articles are assigned to these categories |

---

## Connecting to the Research Dashboard

The pipeline pushes data to the dashboard via HTTP after each cycle/report:

| Event | What is pushed |
|---|---|
| Every cycle | Status (article counts by status) |
| After strategic report | Pillar progress, full report markdown, suggested keywords |
| After each daily task | Task HTML output (becomes a new tab on the dashboard) |

All pushes are no-ops if `DASHBOARD_API_URL` is not set — the pipeline works
fully offline without a dashboard.

---

## Tuning the pipeline

All technical settings are in `config/settings.py` dataclasses. Key ones:

| Setting | Default | Effect |
|---|---|---|
| `llm.pipeline_model` | `qwen3.5:4b` | Local model for filter/categorize/summarize |
| `llm.synthesis_model` | `qwen3.5:4b` | Local model for nightly synthesis passes |
| `pipeline.relevance_threshold` | `0.55` | Below this score → article is discarded |
| `orchestrator.cycle_interval_seconds` | `900` | Wait between cycles (15 min) |
| `orchestrator.max_pipeline_per_cycle` | `50` | Max articles processed per cycle |
| `scraper.github_token` | `""` | Add a GitHub PAT to raise rate limits |
| `scraper.contact_email` | see file | Your email for OpenAlex polite pool |

---

## Common commands

```bash
# Start the continuous pipeline
python run.py

# Show database stats and exit
python run.py --status

# Run a single small cycle and exit (smoke test)
python run.py --test

# Semantic search over collected articles
python run.py --search "your search query"
```

---

## Running multiple research projects on one machine

Multiple pipelines can share the same Ollama instance — Ollama queues requests
sequentially. Each project should live in its own directory with its own SQLite
database and ChromaDB store (`data/` is local to each project).

Resource guidance:
- **2 projects**: comfortable, minimal contention
- **3 projects**: feasible but each cycle is slower during overlapping windows
- **4+ projects**: consider staggering `cycle_interval_seconds` so their active
  windows don't overlap

---

## Troubleshooting

**"Ollama is not reachable"**
→ Start Ollama: `ollama serve` and verify the models are pulled.

**"CLAUDE_API_KEY not set"**
→ Create `pipeline/.env` from `pipeline/.env.example` and add your key.

**Filter is discarding everything / keeping everything**
→ Check `## Research Domain` in `topic_config.md`. Make the relevant/irrelevant
  lists more specific. Adjust `relevance_threshold` in `config/settings.py`.

**Strategic report says "No articles"**
→ The pipeline needs at least a few summarized articles first. Run `python run.py --test`
  a few times to populate the database, then trigger a report.

**Dashboard not receiving updates**
→ Check `DASHBOARD_API_URL` and `DASHBOARD_API_KEY` in `pipeline/.env`.
  Verify the project slug in the dashboard matches what was configured at creation.
