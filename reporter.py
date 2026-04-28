"""
reporter.py — HTML + JSON 報告產生器
使用 Canvas 原生 API 畫折線圖，不依賴任何外部套件或 CDN
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

_HTML = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PyLoad 負載測試報告</title>
<style>
  :root {{
    --bg:#0f1117;--surface:#1a1d27;--border:#2a2d3e;
    --text:#e2e8f0;--muted:#64748b;--accent:#6366f1;
    --green:#22c55e;--yellow:#eab308;--red:#ef4444;--cyan:#06b6d4;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;padding:2rem}}
  h1{{font-size:1.8rem;font-weight:700;color:var(--accent);margin-bottom:.25rem}}
  .meta{{color:var(--muted);font-size:.85rem;margin-bottom:2rem}}
  .kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin-bottom:2.5rem}}
  .kpi{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.2rem 1.5rem}}
  .kpi-label{{font-size:.75rem;text-transform:uppercase;color:var(--muted);letter-spacing:.05em}}
  .kpi-value{{font-size:2rem;font-weight:700;margin-top:.25rem}}
  .neutral{{color:var(--cyan)}}.good{{color:var(--green)}}.warn{{color:var(--yellow)}}.bad{{color:var(--red)}}
  .charts-grid{{display:grid;grid-template-columns:1fr;gap:1.5rem;margin-bottom:2.5rem}}
  .chart-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem}}
  .chart-title{{font-size:1rem;font-weight:600;margin-bottom:1rem}}
  canvas{{width:100%!important;display:block}}
  .legend{{display:flex;gap:1.2rem;margin-top:.6rem;flex-wrap:wrap}}
  .legend-item{{display:flex;align-items:center;gap:.4rem;font-size:.78rem;color:var(--muted)}}
  .legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
  .section-title{{font-size:1rem;font-weight:600;margin-bottom:.75rem;margin-top:2rem}}
  table{{width:100%;border-collapse:collapse;background:var(--surface);border-radius:10px;overflow:hidden;border:1px solid var(--border)}}
  thead{{background:#12151f}}
  th{{padding:.75rem 1rem;text-align:right;font-size:.75rem;text-transform:uppercase;color:var(--muted);letter-spacing:.05em;white-space:nowrap}}
  th:first-child{{text-align:left}}
  td{{padding:.7rem 1rem;font-size:.875rem;text-align:right;border-top:1px solid var(--border)}}
  td:first-child{{text-align:left;font-weight:600}}
  tr:hover td{{background:rgba(99,102,241,.06)}}
  .pill{{display:inline-block;padding:.15em .6em;border-radius:9999px;font-size:.75rem;font-weight:600}}
  .pill.good{{background:rgba(34,197,94,.15);color:var(--green)}}
  .pill.warn{{background:rgba(234,179,8,.15);color:var(--yellow)}}
  .pill.bad{{background:rgba(239,68,68,.15);color:var(--red)}}
  footer{{margin-top:3rem;text-align:center;color:var(--muted);font-size:.8rem}}
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

<div class="charts-grid">
  <div class="chart-card">
    <div class="chart-title">Total Requests per Second</div>
    <canvas id="c1" height="200"></canvas>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div>RPS</div>
      <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div>Failures/s</div>
    </div>
  </div>
  <div class="chart-card">
    <div class="chart-title">Response Times (ms)</div>
    <canvas id="c2" height="200"></canvas>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#eab308"></div>P50</div>
      <div class="legend-item"><div class="legend-dot" style="background:#a855f7"></div>P95</div>
    </div>
  </div>
  <div class="chart-card">
    <div class="chart-title">Number of Users</div>
    <canvas id="c3" height="200"></canvas>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#06b6d4"></div>Users</div>
    </div>
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
const TS = {timeseries_json};

// ── 純 Canvas 折線圖 ────────────────────────────────────────────────────────
function drawChart(canvasId, datasets, opts) {{
  const canvas = document.getElementById(canvasId);
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.parentElement.clientWidth - 48;  // padding
  const H = parseInt(canvas.getAttribute('height'));
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width  = W + 'px';
  canvas.style.height = H + 'px';

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const PAD = {{ top: 16, right: 20, bottom: 36, left: 52 }};
  const pw = W - PAD.left - PAD.right;
  const ph = H - PAD.top  - PAD.bottom;

  // 合併所有資料求 max/min
  const allVals = datasets.flatMap(d => d.data).filter(v => v != null);
  if (!allVals.length) {{
    ctx.fillStyle = '#64748b';
    ctx.font = '13px system-ui';
    ctx.textAlign = 'center';
    ctx.fillText('（無資料）', W/2, H/2);
    return;
  }}
  const yMin = 0;
  const yMax = Math.max(...allVals) * 1.15 || 1;
  const n    = TS.labels.length;

  function toX(i)   {{ return PAD.left + (i / Math.max(n - 1, 1)) * pw; }}
  function toY(v)   {{ return PAD.top  + (1 - (v - yMin) / (yMax - yMin)) * ph; }}

  // 格線
  ctx.strokeStyle = '#1e2235';
  ctx.lineWidth = 1;
  const gridLines = 5;
  for (let g = 0; g <= gridLines; g++) {{
    const y = PAD.top + (g / gridLines) * ph;
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + pw, y); ctx.stroke();
    const val = yMax - (g / gridLines) * (yMax - yMin);
    ctx.fillStyle = '#64748b';
    ctx.font = '11px system-ui';
    ctx.textAlign = 'right';
    ctx.fillText(val >= 1000 ? (val/1000).toFixed(1)+'k' : val.toFixed(val < 10 ? 1 : 0), PAD.left - 6, y + 4);
  }}

  // X 軸標籤（最多 10 個）
  ctx.fillStyle = '#64748b';
  ctx.font = '11px system-ui';
  ctx.textAlign = 'center';
  const step = Math.max(1, Math.floor(n / 10));
  for (let i = 0; i < n; i += step) {{
    ctx.fillText(TS.labels[i] + 's', toX(i), H - PAD.bottom + 16);
  }}

  // 各資料集
  datasets.forEach(ds => {{
    if (!ds.data.length) return;

    // fill
    if (ds.fill) {{
      ctx.beginPath();
      ctx.moveTo(toX(0), toY(ds.data[0]));
      for (let i = 1; i < n; i++) ctx.lineTo(toX(i), toY(ds.data[i]));
      ctx.lineTo(toX(n-1), PAD.top + ph);
      ctx.lineTo(toX(0),   PAD.top + ph);
      ctx.closePath();
      ctx.fillStyle = ds.fillColor || 'rgba(255,255,255,0.04)';
      ctx.fill();
    }}

    // line
    ctx.beginPath();
    ctx.strokeStyle = ds.color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    if (ds.stepped) {{
      for (let i = 0; i < n; i++) {{
        if (i === 0) ctx.moveTo(toX(i), toY(ds.data[i]));
        else {{
          ctx.lineTo(toX(i), toY(ds.data[i-1]));
          ctx.lineTo(toX(i), toY(ds.data[i]));
        }}
      }}
    }} else {{
      ctx.moveTo(toX(0), toY(ds.data[0]));
      for (let i = 1; i < n; i++) ctx.lineTo(toX(i), toY(ds.data[i]));
    }}
    ctx.stroke();
  }});

  // 外框
  ctx.strokeStyle = '#2a2d3e';
  ctx.lineWidth = 1;
  ctx.strokeRect(PAD.left, PAD.top, pw, ph);
}}

drawChart('c1', [
  {{ data: TS.rps,              color: '#22c55e', fill: true, fillColor: 'rgba(34,197,94,0.08)' }},
  {{ data: TS.failures_per_sec, color: '#ef4444', fill: true, fillColor: 'rgba(239,68,68,0.08)' }},
]);
drawChart('c2', [
  {{ data: TS.p50, color: '#eab308' }},
  {{ data: TS.p95, color: '#a855f7' }},
]);
drawChart('c3', [
  {{ data: TS.users, color: '#06b6d4', fill: true, fillColor: 'rgba(6,182,212,0.10)', stepped: true }},
]);
</script>
</body>
</html>"""

_ROW_TEMPLATE = """<tr>
  <td>{name}</td><td>{total}</td><td>{failures}</td>
  <td><span class="pill {err_class}">{error_rate}%</span></td>
  <td>{rps}</td><td>{avg_ms}</td><td>{p50_ms}</td><td>{p95_ms}</td><td>{p99_ms}</td><td>{max_ms}</td>
</tr>"""


def _err_class(rate: float) -> str:
    if rate == 0: return "good"
    if rate < 5:  return "warn"
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

    if timeseries:
        ts_data = timeseries.chart_data()
    else:
        ts_data = {"labels": [], "rps": [], "failures_per_sec": [], "p50": [], "p95": [], "users": []}

    err_rate = snap["overall_error_rate"]
    html = _HTML.format(
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