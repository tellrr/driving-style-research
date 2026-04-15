"""Generate the HTML statistics dashboard at reports/stats.html.

Reads data/pillar_history.json (written by stats_tracker) and produces a
single self-contained HTML file with:
  - Three stat cards: total scraped / total relevant / GitHub repos
  - A line chart showing each pillar's progress percentage over time

Chart.js is loaded from CDN; the page requires an internet connection to
render the chart on first open (the chart data itself is embedded inline).

Pillar names and chart title are driven by config/topic_config.md —
no changes to this file are required when setting up a new research project.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.stats_tracker import load_history, _get_pillars

ROOT = Path(__file__).parent.parent
STATS_HTML_PATH = ROOT / "reports" / "stats.html"
DAILY_REPORTS_DIR = ROOT / "reports" / "daily"


def _latest_report_graph_rel_path() -> tuple[str, str] | tuple[None, None]:
    """
    Return (relative_path, date_label) for the most recent
    *_report-graph-suggestions.html in reports/daily/.
    Returns (None, None) if nothing is found.
    """
    if DAILY_REPORTS_DIR.exists():
        candidates = sorted(
            DAILY_REPORTS_DIR.glob("*_report-graph-suggestions.html"), reverse=True
        )
        if candidates:
            path = candidates[0]
            date_label = path.stem.split("_")[0]
            return f"daily/{path.name}", date_label
    return None, None

# Colour palette for up to 8 pillars — chosen for contrast on a dark background
_PILLAR_COLOR_PALETTE = [
    "#38bdf8",   # sky blue
    "#a78bfa",   # violet
    "#34d399",   # emerald
    "#fb923c",   # orange
    "#f472b6",   # pink
    "#facc15",   # amber
    "#4ade80",   # green
    "#f87171",   # red
]


def _get_pillar_colors(pillars: list[str]) -> dict[str, str]:
    return {
        pillar: _PILLAR_COLOR_PALETTE[i % len(_PILLAR_COLOR_PALETTE)]
        for i, pillar in enumerate(pillars)
    }


def generate_stats_html() -> Path:
    """Build and write reports/stats.html. Returns the output path."""
    from config.settings import project_meta

    pillars = _get_pillars()
    pillar_colors = _get_pillar_colors(pillars)
    history = load_history()
    project_name = project_meta.name or "Research Pipeline"

    # ── Latest snapshot for the stat cards ────────────────────────────────
    latest_stats = history[-1].get("stats", {}) if history else {}
    total_scraped = latest_stats.get("total_scraped", 0)
    total_relevant = latest_stats.get("total_relevant", 0)
    total_github = latest_stats.get("total_github_repos", 0)

    # ── Chart.js dataset ───────────────────────────────────────────────────
    dates = [e["date"] for e in history]
    datasets = []
    for pillar in pillars:
        values = [e["pillars"].get(pillar) for e in history]   # None = missing
        color = pillar_colors.get(pillar, "#94a3b8")
        datasets.append({
            "label": pillar,
            "data": values,
            "borderColor": color,
            "backgroundColor": color + "22",
            "tension": 0.3,
            "fill": False,
            "pointRadius": 5,
            "pointHoverRadius": 7,
            "spanGaps": True,
        })

    chart_data_json = json.dumps({"labels": dates, "datasets": datasets})
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    has_data = len(history) > 0
    no_data_html = (
        "" if has_data
        else '<div class="no-data">No history yet — run the pipeline to collect data.</div>'
    )
    canvas_display = "block" if has_data else "none"

    # Report & Graph Suggestions section (shown when a daily output exists)
    report_graph_rel, report_graph_date = _latest_report_graph_rel_path()
    if report_graph_rel:
        section_label = f"Report &amp; Graph Suggestions ({report_graph_date})"
        mockup_section = (
            f'  <div style="margin-top:2.5rem;">\n'
            f'    <div class="chart-header"><span class="chart-title">{section_label}</span></div>\n'
            f'    <iframe src="{report_graph_rel}" style="width:100%;height:900px;border:none;'
            f'border-radius:10px;background:#070a10;" title="Report &amp; Graph Suggestions"></iframe>\n'
            f'  </div>'
        )
    else:
        mockup_section = ""

    html = _HTML_TEMPLATE.format(
        project_name=project_name,
        generated=generated,
        total_scraped=f"{total_scraped:,}",
        total_relevant=f"{total_relevant:,}",
        total_github=f"{total_github:,}",
        chart_data_json=chart_data_json,
        snapshot_count=len(history),
        no_data_html=no_data_html,
        canvas_display=canvas_display,
        mockup_section=mockup_section,
    )

    STATS_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_HTML_PATH.write_text(html, encoding="utf-8")
    return STATS_HTML_PATH


# ─────────────────────────────────────────────────────────────────────────────
# HTML template  (uses double-braces {{ }} for literal JS braces)
# ─────────────────────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{project_name} \u2014 Statistics</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 2.5rem 1.5rem;
    }}

    .wrapper {{
      max-width: 1100px;
      margin: 0 auto;
    }}

    h1 {{
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}

    .subtitle {{
      color: #64748b;
      font-size: 0.875rem;
      margin-top: 0.35rem;
      margin-bottom: 2.25rem;
    }}

    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2.5rem;
    }}

    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 14px;
      padding: 1.75rem 1.5rem;
      text-align: center;
    }}

    .card-value {{
      font-size: 2.75rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      line-height: 1;
    }}

    .card-label {{
      font-size: 0.8rem;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      margin-top: 0.65rem;
    }}

    .card:nth-child(1) .card-value {{ color: #38bdf8; }}
    .card:nth-child(2) .card-value {{ color: #34d399; }}
    .card:nth-child(3) .card-value {{ color: #a78bfa; }}

    .chart-panel {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 14px;
      padding: 1.75rem 1.5rem 1.5rem;
    }}

    .chart-header {{
      display: flex;
      align-items: baseline;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }}

    .chart-title {{
      font-size: 1.05rem;
      font-weight: 600;
    }}

    .chart-meta {{
      font-size: 0.8rem;
      color: #64748b;
    }}

    .chart-container {{
      position: relative;
      height: 400px;
    }}

    .no-data {{
      display: flex;
      align-items: center;
      justify-content: center;
      height: 200px;
      color: #475569;
      font-size: 0.95rem;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <h1>{project_name} &mdash; Pipeline Statistics</h1>
    <p class="subtitle">
      Generated: {generated}
      &nbsp;&middot;&nbsp;
      {snapshot_count} daily snapshot(s)
    </p>

    <div class="stats">
      <div class="card">
        <div class="card-value">{total_scraped}</div>
        <div class="card-label">Documents Scraped</div>
      </div>
      <div class="card">
        <div class="card-value">{total_relevant}</div>
        <div class="card-label">Relevant Documents</div>
      </div>
      <div class="card">
        <div class="card-value">{total_github}</div>
        <div class="card-label">GitHub Repos Found</div>
      </div>
    </div>

    <div class="chart-panel">
      <div class="chart-header">
        <span class="chart-title">Research Progress by Pillar</span>
        <span class="chart-meta">(% toward goal, assessed daily by Claude Opus)</span>
      </div>
      <div class="chart-container">
        {no_data_html}
        <canvas id="pillarChart" style="display:{canvas_display};"></canvas>
      </div>
    </div>

{mockup_section}
  </div>

  <script>
  (function() {{
    const chartData = {chart_data_json};
    if (!chartData.labels || chartData.labels.length === 0) return;

    const ctx = document.getElementById('pillarChart').getContext('2d');
    new Chart(ctx, {{
      type: 'line',
      data: chartData,
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{
          mode: 'index',
          intersect: false,
        }},
        plugins: {{
          legend: {{
            labels: {{
              color: '#cbd5e1',
              font: {{ size: 13 }},
              padding: 20,
              usePointStyle: true,
            }}
          }},
          tooltip: {{
            backgroundColor: '#0f172a',
            borderColor: '#334155',
            borderWidth: 1,
            titleColor: '#e2e8f0',
            bodyColor: '#94a3b8',
            padding: 12,
            callbacks: {{
              label: (ctx) => {{
                const v = ctx.parsed.y;
                return ` ${{ctx.dataset.label}}: ${{v !== null ? v + '%' : 'n/a'}}`;
              }}
            }}
          }}
        }},
        scales: {{
          x: {{
            ticks: {{ color: '#94a3b8', font: {{ size: 12 }} }},
            grid:  {{ color: '#1e293b' }},
          }},
          y: {{
            min: 0,
            max: 100,
            ticks: {{
              color: '#94a3b8',
              font: {{ size: 12 }},
              callback: (v) => v + '%',
            }},
            grid: {{ color: '#334155' }},
          }}
        }}
      }}
    }});
  }})();
  </script>
</body>
</html>
"""
