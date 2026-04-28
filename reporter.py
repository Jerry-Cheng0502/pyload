"""
reporter.py — HTML + JSON 報告產生器
測試結束後輸出完整報告，含三張折線圖：
  1. Total Requests per Second (RPS + Failures/s)
  2. Response Times P50 / P95 (ms)
  3. Number of Users
"""
import json
import time
from typing import Optional

from .stats import StatsCollector, TimeSeriesCollector


# ── JSON ────────────────────────────────────────────────────────────────────

def save_json(stats: StatsCollector, path: str = "report.json"):
    snap = stats.snapshot()
    snap["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)
    print(f"[PyLoad] JSON 報告已儲存：{path}")


# ── HTML ────────────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PyLoad 負載測試報告</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3e;
    --text: #e2e8f0; --muted: #64748b; --accent: #6366f1;
    --green: #22c55e; --yellow: #eab308; --red: #ef4444;
    --cyan: #06b6d4; --orange: #f97316;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; padding: 2rem; }}
  h1 {{ font-size: 1.8rem; font-weight: 700; color: var(--accent); margin-bottom: 0.25rem; }}
  .meta {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 2rem; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 2.5rem; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.2rem 1.5rem; }}
  .kpi-label {{ font-size: 0.75rem; text-transform: uppercase; color: var(--muted); letter-spacing: .05em; }}
  .kpi-value {{ font-size: 2rem; font-weight: 700; margin-top: 0.25rem; }}
  .kpi-value.good {{ color: var(--green); }}
  .kpi-value.warn {{ color: var(--yellow); }}
  .kpi-value.bad  {{ color: var(--red); }}
  .kpi-value.neutral {{ color: var(--cyan); }}

  /* 圖表區塊 */
  .charts-grid {{ display: grid; grid-template-columns: 1fr; gap: 1.5rem; margin-bottom: 2.5rem; }}
  .chart-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; }}
  .chart-title {{ font-size: 1rem; font-weight: 600; margin-bottom: 1rem; color: var(--text); }}
  .chart-wrap {{ position: relative; height: 220px; }}

  /* 統計表格 */
  .section-title {{ font-size: 1rem; font-weight: 600; color: var(--text); margin-bottom: .75rem; margin-top: 2rem; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 10px; overflow: hidden; border: 1px solid var(--border); }}
  thead {{ background: #12151f; }}
  th {{ padding: .75rem 1rem; text-align: right; font-size: .75rem; text-transform: uppercase; color: var(--muted); letter-spacing: .05em; white-space: nowrap; }}
  th:first-child {{ text-align: left; }}
  td {{ padding: .7rem 1rem; font-size: .875rem; text-align: right; border-top: 1px solid var(--border); }}
  td:first-child {{ text-align: left; font-weight: 600; }}
  tr:hover td {{ background: rgba(99,102,241,.06); }}
  .pill {{ display: inline-block; padding: .15em .6em; border-radius: 9999px; font-size: .75rem; font-weight: 600; }}
  .pill.good {{ background: rgba(34,197,94,.15); color: var(--green); }}
  .pill.warn {{ background: rgba(234,179,8,.15);  color: var(--yellow); }}
  .pill.bad  {{ background: rgba(239,68,68,.15);  color: var(--red); }}
  footer {{ margin-top: 3rem; text-align: center; color: var(--muted); font-size: .8rem; }}
</style>
</head>
<body>
<h1>⚡ PyLoad 負載測試報告</h1>
<div class="meta">產生時間：{generated_at} ｜ 執行時長：{elapsed_sec}s ｜ 目標：{host}</div>

<div class="kpi-grid">
  <div class="kpi"><div class="kpi-label">總請求數</div><div class="kpi-value neutral">{total_requests}</div></div>
  <div class="kpi"><div class="kpi-label">失敗數</div><div class="kpi-value {fail_class}">{total_failures}</div></div>
  <div class="kpi"><div class="kpi-label">錯誤率</div><div class="kpi-value {err_class}">{overall_error_rate}%</div></div>
  <div class="kpi"><div class="kpi-label">平均 RPS</div><div class="kpi-value neutral">{total_rps}</div></div>
  <div class="kpi"><div class="kpi-label">執行時長</div><div class="kpi-value neutral">{elapsed_sec}s</div></div>
</div>

<!-- 折線圖區 -->
<div class="charts-grid">
  <div class="chart-card">
    <div class="chart-title">Total Requests per Second</div>
    <div class="chart-wrap"><canvas id="chartRps"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="chart-title">Response Times (ms)</div>
    <div class="chart-wrap"><canvas id="chartRt"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="chart-title">Number of Users</div>
    <div class="chart-wrap"><canvas id="chartUsers"></canvas></div>
  </div>
</div>

<div class="section-title">📋 各 Task 詳細統計</div>
<table>
  <thead>
    <tr>
      <th>Task 名稱</th><th>請求數</th><th>失敗</th><th>錯誤率</th>
      <th>RPS</th><th>Avg (ms)</th><th>P50</th><th>P95</th><th>P99</th><th>Max</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

<footer>PyLoad — Python 輕量級負載測試工具 | {generated_at}</footer>

<script>
const ts = {timeseries_json};
const labels = ts.labels.map(t => t + 's');

const chartDefaults = {{
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  plugins: {{ legend: {{ labels: {{ color: '#94a3b8', boxWidth: 12, padding: 16 }} }} }},
  scales: {{
    x: {{ ticks: {{ color: '#64748b', maxTicksLimit: 12 }}, grid: {{ color: '#1e2235' }} }},
    y: {{ ticks: {{ color: '#64748b' }}, grid: {{ color: '#1e2235' }}, beginAtZero: true }}
  }}
}};

// 1. RPS + Failures/s
new Chart(document.getElementById('chartRps'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{ label: 'RPS', data: ts.rps, borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.08)',
         borderWidth: 2, pointRadius: 0, fill: true, tension: 0.3 }},
      {{ label: 'Failures/s', data: ts.failures_per_sec, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.08)',
         borderWidth: 2, pointRadius: 0, fill: true, tension: 0.3 }}
    ]
  }},
  options: chartDefaults
}});

// 2. P50 + P95 Response Time
new Chart(document.getElementById('chartRt'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{ label: 'P50 (ms)', data: ts.p50, borderColor: '#eab308', backgroundColor: 'rgba(234,179,8,0.08)',
         borderWidth: 2, pointRadius: 0, fill: false, tension: 0.3 }},
      {{ label: 'P95 (ms)', data: ts.p95, borderColor: '#a855f7', backgroundColor: 'rgba(168,85,247,0.08)',
         borderWidth: 2, pointRadius: 0, fill: false, tension: 0.3 }}
    ]
  }},
  options: chartDefaults
}});

// 3. Number of Users
new Chart(document.getElementById('chartUsers'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{ label: 'Users', data: ts.users, borderColor: '#06b6d4', backgroundColor: 'rgba(6,182,212,0.12)',
         borderWidth: 2, pointRadius: 0, fill: true, tension: 0.1, stepped: true }}
    ]
  }},
  options: chartDefaults
}});
</script>
</body>
</html>"""

_ROW_TEMPLATE = """<tr>
  <td>{name}</td><td>{total}</td><td>{failures}</td>
  <td><span class="pill {err_class}">{error_rate}%</span></td>
  <td>{rps}</td><td>{avg_ms}</td><td>{p50_ms}</td><td>{p95_ms}</td><td>{p99_ms}</td><td>{max_ms}</td>
</tr>"""


def _err_class(rate: float) -> str:
    if rate == 0:   return "good"
    if rate < 5:    return "warn"
    return "bad"


def save_html(
    stats: StatsCollector,
    path: str = "report.html",
    host: str = "",
    timeseries: Optional[TimeSeriesCollector] = None,
):
    snap = stats.snapshot()
    tasks = snap["tasks"]
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")

    rows_html = ""
    for t in tasks:
        rows_html += _ROW_TEMPLATE.format(
            name=t["name"], total=t["total"], failures=t["failures"],
            error_rate=t["error_rate"], err_class=_err_class(t["error_rate"]),
            rps=t["rps"], avg_ms=t["avg_ms"], p50_ms=t["p50_ms"],
            p95_ms=t["p95_ms"], p99_ms=t["p99_ms"], max_ms=t["max_ms"],
        )

    # 時間序列資料（若無則給空資料）
    if timeseries:
        ts_data = timeseries.chart_data()
    else:
        ts_data = {"labels": [], "rps": [], "failures_per_sec": [], "p50": [], "p95": [], "users": []}

    err_rate = snap["overall_error_rate"]
    html = _HTML_TEMPLATE.format(
        generated_at=generated_at,
        elapsed_sec=snap["elapsed_sec"],
        host=host or "(未指定)",
        total_requests=snap["total_requests"],
        total_failures=snap["total_failures"],
        fail_class=_err_class(err_rate),
        overall_error_rate=err_rate,
        err_class=_err_class(err_rate),
        total_rps=snap["total_rps"],
        rows=rows_html,
        timeseries_json=json.dumps(ts_data),
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[PyLoad] HTML 報告已儲存：{path}")