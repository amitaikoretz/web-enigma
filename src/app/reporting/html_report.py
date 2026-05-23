from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from app.output.models import BacktestReport


def _safe_json_for_script(value: Any) -> str:
    # Prevent accidental script tag termination when embedding JSON in HTML.
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _extract_timestamps(run: dict[str, Any]) -> list[str]:
    timestamps: list[str] = []
    timestamps.extend(p["datetime"] for p in run.get("equity_curve", []) if p.get("datetime"))
    timestamps.extend(o["datetime"] for o in run.get("orders", []) if o.get("datetime"))
    timestamps.extend(t["datetime"] for t in run.get("trades", []) if t.get("datetime"))
    return sorted(set(timestamps))


def _build_view_model(report: BacktestReport) -> dict[str, Any]:
    successful = [r for r in report.results if r.status == "success" and r.summary is not None]
    failed = [r for r in report.results if r.status == "failed"]

    returns = [r.summary.return_pct for r in successful if r.summary is not None]
    drawdowns = [
        r.summary.max_drawdown_pct
        for r in successful
        if r.summary is not None and r.summary.max_drawdown_pct is not None
    ]
    sharpes = [
        r.summary.sharpe_ratio
        for r in successful
        if r.summary is not None and r.summary.sharpe_ratio is not None
    ]
    total_trades = sum((r.summary.total_trades for r in successful if r.summary is not None), start=0)
    won_trades = sum((r.summary.won_trades for r in successful if r.summary is not None), start=0)
    lost_trades = sum((r.summary.lost_trades for r in successful if r.summary is not None), start=0)

    run_cards: list[dict[str, Any]] = []
    for run in report.results:
        summary = run.summary
        run_dict = {
            "equity_curve": [p.model_dump() for p in run.equity_curve],
            "orders": [o.model_dump() for o in run.orders],
            "trades": [t.model_dump() for t in run.trades],
        }
        timestamps = _extract_timestamps(run_dict)
        run_cards.append(
            {
                "run_id": run.run_id,
                "name": run.name,
                "status": run.status,
                "strategy": run.strategy,
                "data_source": run.data_source,
                "return_pct": None if summary is None else summary.return_pct,
                "start_value": None if summary is None else summary.start_value,
                "end_value": None if summary is None else summary.end_value,
                "max_drawdown_pct": None if summary is None else summary.max_drawdown_pct,
                "sharpe_ratio": None if summary is None else summary.sharpe_ratio,
                "total_trades": None if summary is None else summary.total_trades,
                "won_trades": None if summary is None else summary.won_trades,
                "lost_trades": None if summary is None else summary.lost_trades,
                "start_datetime": timestamps[0] if timestamps else None,
                "stop_datetime": timestamps[-1] if timestamps else None,
                **run_dict,
                "error": None if run.error is None else run.error.model_dump(),
            }
        )

    return {
        "meta": {
            "generated_at": report.generated_at.isoformat(),
            "app_version": report.app_version,
            "config_sha256": report.config_sha256,
            "input_config_path": report.input_config_path,
            "status": report.status,
        },
        "input_config": report.input_config,
        "aggregate": {
            "total_runs": report.total_runs,
            "successful_runs": report.successful_runs,
            "failed_runs": report.failed_runs,
            "avg_return_pct": mean(returns) if returns else None,
            "best_return_pct": max(returns) if returns else None,
            "worst_return_pct": min(returns) if returns else None,
            "avg_drawdown_pct": mean(drawdowns) if drawdowns else None,
            "avg_sharpe_ratio": mean(sharpes) if sharpes else None,
            "total_trades": total_trades,
            "won_trades": won_trades,
            "lost_trades": lost_trades,
            "win_rate_pct": (won_trades / total_trades * 100.0) if total_trades else None,
            "failed_run_ids": [r.run_id for r in failed],
        },
        "runs": run_cards,
    }


def _render_html(view: dict[str, Any], title: str) -> str:
    payload = _safe_json_for_script(view)
    page_title = title or "Backtest Report"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{page_title}</title>
  <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ background: linear-gradient(145deg, #eceff1 0%, #fafafa 55%, #f1f8e9 100%); font-family: Roboto, sans-serif; }}
    nav {{ background: linear-gradient(90deg, #1565c0 0%, #00897b 100%); }}
    .container-wide {{ width: 94%; margin: 18px auto 48px auto; }}
    .card.metric .card-content {{ min-height: 100px; padding: 16px 18px; }}
    .metric-value {{ font-size: 1.5rem; font-weight: 500; margin-top: 6px; color: #1b5e20; }}
    .metric-label {{ color: #607d8b; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05rem; }}
    .widget-card {{ border-radius: 14px; overflow: hidden; }}
    .plot-wrapper {{ width: 100%; min-height: 380px; }}
    .plot-wrapper.compact {{ min-height: 220px; }}
    .small-note {{ color: #546e7a; font-size: 0.86rem; }}
    .run-detail-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-top: 8px; }}
    .run-detail-item {{ background: #f7fafb; border: 1px solid #dde7ea; border-radius: 8px; padding: 10px; }}
    .run-detail-key {{ font-size: 0.7rem; color: #607d8b; text-transform: uppercase; letter-spacing: 0.05rem; }}
    .run-detail-val {{ font-size: 0.98rem; color: #263238; margin-top: 4px; }}
    .config-root-note {{ margin-bottom: 10px; }}
    .config-widget {{ border: 1px solid #d7e5ea; border-radius: 10px; background: #fbfdfe; margin: 8px 0; }}
    .config-widget-header {{ padding: 10px 12px; border-bottom: 1px solid #e3edf0; font-weight: 500; color: #375a64; }}
    .config-widget-body {{ padding: 8px 12px; }}
    .config-entry {{ display: grid; grid-template-columns: 190px 1fr; gap: 8px; padding: 6px 0; border-bottom: 1px dashed #e6eef1; }}
    .config-entry:last-child {{ border-bottom: none; }}
    .config-key {{ color: #607d8b; font-size: 0.84rem; }}
    .config-val {{ color: #1f2d33; word-break: break-word; }}
    .config-pill {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.76rem; background: #edf4f7; color: #47606a; margin-left: 6px; }}
    .chip.status-success {{ background-color: #dcedc8; color: #33691e; }}
    .chip.status-failed {{ background-color: #ffcdd2; color: #b71c1c; }}
    table.striped > tbody > tr:nth-child(odd) {{ background-color: rgba(0, 150, 136, 0.06); }}
  </style>
</head>
<body>
  <nav>
    <div class="nav-wrapper">
      <a class="brand-logo center" href="#!">{page_title}</a>
    </div>
  </nav>

  <div class="container-wide">
    <div class="row" id="metrics-row"></div>

    <div class="row">
      <div class="col s12 m7 l8">
        <div class="card widget-card">
          <div class="card-content">
            <span class="card-title">Run Selector</span>
            <div class="input-field">
              <select id="run-select"></select>
              <label>Choose Run</label>
            </div>
            <p class="small-note" id="run-meta"></p>
            <div id="run-details" class="run-detail-grid"></div>
          </div>
        </div>
      </div>
      <div class="col s12 m5 l4">
        <div class="card widget-card">
          <div class="card-content">
            <span class="card-title">Status Overview</span>
            <div id="status-pie" class="plot-wrapper compact"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="card widget-card">
      <div class="card-content">
        <span class="card-title">Input Definition</span>
        <p class="small-note config-root-note" id="input-config-meta"></p>
        <ul class="collapsible" id="input-config-collapsible"></ul>
      </div>
    </div>

    <div class="card widget-card">
      <div class="card-content">
        <ul class="tabs">
          <li class="tab col s2"><a class="active" href="#tab-equity">Equity Curve</a></li>
          <li class="tab col s2"><a href="#tab-returns">Returns Across Runs</a></li>
          <li class="tab col s2"><a href="#tab-metrics">Run Metrics</a></li>
          <li class="tab col s3"><a href="#tab-orders">Order Examples</a></li>
          <li class="tab col s3"><a href="#tab-trades">Trade Open/Close Examples</a></li>
          <li class="tab col s3"><a href="#tab-candlestick">Example Candlestick (Trading Day)</a></li>
        </ul>
      </div>
      <div id="tab-equity" class="col s12">
        <div id="equity-plot" class="plot-wrapper"></div>
      </div>
      <div id="tab-returns" class="col s12">
        <div id="returns-plot" class="plot-wrapper"></div>
      </div>
      <div id="tab-metrics" class="col s12">
        <div class="card-content">
          <table class="striped responsive-table">
            <thead>
              <tr><th>Metric</th><th>Value</th></tr>
            </thead>
            <tbody id="run-metrics-body"></tbody>
          </table>
        </div>
      </div>
      <div id="tab-orders" class="col s12">
        <div class="card-content">
          <table class="striped responsive-table">
            <thead>
              <tr><th>Datetime</th><th>Action</th><th>Status</th><th>Size</th><th>Price</th><th>Value</th><th>Commission</th></tr>
            </thead>
            <tbody id="orders-body"></tbody>
          </table>
        </div>
      </div>
      <div id="tab-trades" class="col s12">
        <div class="card-content">
          <table class="striped responsive-table">
            <thead>
              <tr><th>Datetime</th><th>Size</th><th>Price</th><th>Value</th><th>PnL</th><th>PnL (net)</th><th>Type (proxy)</th></tr>
            </thead>
            <tbody id="trades-body"></tbody>
          </table>
        </div>
      </div>
      <div id="tab-candlestick" class="col s12">
        <div id="candlestick-plot" class="plot-wrapper"></div>
      </div>
    </div>
  </div>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/js/materialize.min.js"></script>
  <script id="report-data" type="application/json">{payload}</script>
  <script>
    const data = JSON.parse(document.getElementById("report-data").textContent);

    function fmtNumber(v, digits = 2) {{
      if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
      return Number(v).toLocaleString(undefined, {{ maximumFractionDigits: digits }});
    }}

    function fmtPct(v) {{
      if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
      return `${{Number(v).toFixed(2)}}%`;
    }}

    function metricCard(label, value) {{
      return `
        <div class="col s12 m6 l2">
          <div class="card metric">
            <div class="card-content">
              <div class="metric-label">${{label}}</div>
              <div class="metric-value">${{value}}</div>
            </div>
          </div>
        </div>`;
    }}

    function renderMetrics() {{
      const a = data.aggregate;
      const row = document.getElementById("metrics-row");
      row.innerHTML = [
        metricCard("Total Runs", fmtNumber(a.total_runs, 0)),
        metricCard("Successful Runs", fmtNumber(a.successful_runs, 0)),
        metricCard("Average Return", fmtPct(a.avg_return_pct)),
        metricCard("Win Rate", fmtPct(a.win_rate_pct)),
        metricCard("Best Return", fmtPct(a.best_return_pct)),
        metricCard("Worst Return", fmtPct(a.worst_return_pct)),
        metricCard("Avg Drawdown", fmtPct(a.avg_drawdown_pct)),
        metricCard("Total Trades", fmtNumber(a.total_trades, 0)),
      ].join("");
    }}

    function escapeHtml(s) {{
      return String(s)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }}

    function isPlainObject(v) {{
      return v !== null && typeof v === "object" && !Array.isArray(v);
    }}

    function renderScalar(v) {{
      if (v === null) return '<span class="config-val">null</span>';
      if (typeof v === "boolean") return `<span class="config-val">${{v ? "true" : "false"}}</span>`;
      if (typeof v === "number") return `<span class="config-val">${{v}}</span>`;
      return `<span class="config-val">${{escapeHtml(String(v))}}</span>`;
    }}

    function renderConfigNode(title, node) {{
      if (isPlainObject(node)) {{
        const entries = Object.entries(node);
        return `
          <div class="config-widget">
            <div class="config-widget-header">${{escapeHtml(title)}}<span class="config-pill">object</span></div>
            <div class="config-widget-body">
              ${{entries.length ? entries.map(([k, v]) => `
                <div class="config-entry">
                  <div class="config-key">${{escapeHtml(k)}}</div>
                  <div class="config-val">
                    ${{(isPlainObject(v) || Array.isArray(v)) ? renderConfigNode(k, v) : renderScalar(v)}}
                  </div>
                </div>
              `).join("") : '<div class="config-entry"><div class="config-key">empty</div><div class="config-val">-</div></div>'}}
            </div>
          </div>
        `;
      }}
      if (Array.isArray(node)) {{
        return `
          <div class="config-widget">
            <div class="config-widget-header">${{escapeHtml(title)}}<span class="config-pill">list (${{node.length}})</span></div>
            <div class="config-widget-body">
              ${{node.length ? node.map((item, idx) => `
                <div class="config-entry">
                  <div class="config-key">#${{idx + 1}}</div>
                  <div class="config-val">
                    ${{(isPlainObject(item) || Array.isArray(item)) ? renderConfigNode(`${{title}}[${{idx}}]`, item) : renderScalar(item)}}
                  </div>
                </div>
              `).join("") : '<div class="config-entry"><div class="config-key">empty</div><div class="config-val">-</div></div>'}}
            </div>
          </div>
        `;
      }}
      return `
        <div class="config-widget">
          <div class="config-widget-header">${{escapeHtml(title)}}<span class="config-pill">value</span></div>
          <div class="config-widget-body">${{renderScalar(node)}}</div>
        </div>
      `;
    }}

    function renderInputConfig() {{
      const path = data.meta.input_config_path ? fmtRaw(data.meta.input_config_path) : "N/A";
      document.getElementById("input-config-meta").innerText = `Source YAML: ${{path}}`;
      const root = data.input_config || {{}};
      const sections = Object.keys(root).length ? Object.entries(root) : [["config", root]];
      const host = document.getElementById("input-config-collapsible");
      host.innerHTML = sections.map(([key, value], idx) => `
        <li class="${{idx === 0 ? "active" : ""}}">
          <div class="collapsible-header">${{escapeHtml(key)}}</div>
          <div class="collapsible-body">${{renderConfigNode(key, value)}}</div>
        </li>
      `).join("");
      M.Collapsible.init(host);
    }}

    function renderStatusPie() {{
      Plotly.newPlot("status-pie", [{{
        values: [data.aggregate.successful_runs, data.aggregate.failed_runs],
        labels: ["Successful", "Failed"],
        type: "pie",
        marker: {{ colors: ["#43a047", "#e53935"] }},
        textinfo: "label+percent"
      }}], {{
        margin: {{ t: 8, r: 8, b: 8, l: 8 }},
        height: 220,
      }}, {{ responsive: true }});
    }}

    function renderReturnsBar() {{
      const runs = data.runs.filter(r => r.return_pct !== null);
      Plotly.newPlot("returns-plot", [{{
        x: runs.map(r => r.run_id),
        y: runs.map(r => r.return_pct),
        type: "bar",
        marker: {{
          color: runs.map(r => (r.return_pct >= 0 ? "#00acc1" : "#f4511e"))
        }},
        hovertemplate: "<b>%{{x}}</b><br>Return: %{{y:.2f}}%<extra></extra>",
      }}], {{
        title: "Run Return Comparison",
        xaxis: {{ title: "Run ID" }},
        yaxis: {{ title: "Return (%)" }},
        margin: {{ t: 45, r: 25, b: 75, l: 60 }},
      }}, {{ responsive: true }});
    }}

    function renderExampleCandlestick() {{
      const x = [
        "2026-01-05T09:30:00",
        "2026-01-05T10:00:00",
        "2026-01-05T10:30:00",
        "2026-01-05T11:00:00",
        "2026-01-05T11:30:00",
        "2026-01-05T12:00:00",
        "2026-01-05T12:30:00",
        "2026-01-05T13:00:00",
        "2026-01-05T13:30:00",
        "2026-01-05T14:00:00",
        "2026-01-05T14:30:00",
        "2026-01-05T15:00:00",
        "2026-01-05T15:30:00",
        "2026-01-05T16:00:00",
      ];
      const open = [100.2, 100.8, 101.4, 101.1, 101.6, 102.0, 101.7, 101.4, 101.9, 102.3, 102.0, 102.6, 102.2, 102.8];
      const high = [101.0, 101.7, 101.9, 101.8, 102.2, 102.5, 102.1, 102.0, 102.7, 102.9, 102.8, 103.0, 102.9, 103.4];
      const low = [99.8, 100.5, 100.9, 100.8, 101.2, 101.5, 101.1, 101.0, 101.5, 101.9, 101.8, 102.1, 101.9, 102.4];
      const close = [100.8, 101.4, 101.1, 101.6, 102.0, 101.7, 101.4, 101.9, 102.3, 102.0, 102.6, 102.2, 102.8, 103.1];

      Plotly.newPlot("candlestick-plot", [{{
        type: "candlestick",
        x,
        open,
        high,
        low,
        close,
        increasing: {{ line: {{ color: "#2e7d32" }}, fillcolor: "#66bb6a" }},
        decreasing: {{ line: {{ color: "#c62828" }}, fillcolor: "#ef5350" }},
        hovertemplate: "<b>%{{x}}</b><br>O: %{{open:.2f}}<br>H: %{{high:.2f}}<br>L: %{{low:.2f}}<br>C: %{{close:.2f}}<extra></extra>",
      }}], {{
        title: "Example Intraday Candlestick (Trading Day)",
        xaxis: {{
          title: "Time",
          rangeslider: {{ visible: false }},
          type: "date",
        }},
        yaxis: {{ title: "Price" }},
        margin: {{ t: 50, r: 25, b: 65, l: 70 }},
      }}, {{ responsive: true }});
    }}

    function pickTradeType(trade) {{
      return trade.pnl >= 0 ? "Close (profit proxy)" : "Close (loss proxy)";
    }}

    function fmtRaw(v) {{
      return (v === null || v === undefined || v === "") ? "N/A" : String(v);
    }}

    function fmtDateTime(v) {{
      if (v === null || v === undefined || v === "") return "N/A";
      const s = String(v);
      if (s.endsWith("T00:00:00")) return s.slice(0, 10);
      if (s.endsWith(" 00:00:00")) return s.slice(0, 10);
      return s.replace("T", " ");
    }}

    function renderRunDetails(run) {{
      const details = [
        ["Start", fmtRaw(run.start_datetime)],
        ["Stop", fmtRaw(run.stop_datetime)],
        ["Start Equity", fmtNumber(run.start_value, 2)],
        ["End Equity", fmtNumber(run.end_value, 2)],
        ["Return", fmtPct(run.return_pct)],
        ["Max Drawdown", fmtPct(run.max_drawdown_pct)],
        ["Sharpe", fmtNumber(run.sharpe_ratio, 3)],
        ["Trades", fmtNumber(run.total_trades, 0)],
      ];
      document.getElementById("run-details").innerHTML = details.map(([k, v]) => `
        <div class="run-detail-item">
          <div class="run-detail-key">${{k}}</div>
          <div class="run-detail-val">${{v}}</div>
        </div>
      `).join("");
    }}


    function renderRunMetricsTable(run) {{
      const rows = [
        ["Run ID", fmtRaw(run.run_id)],
        ["Name", fmtRaw(run.name)],
        ["Status", fmtRaw(run.status)],
        ["Strategy", fmtRaw(run.strategy)],
        ["Data Source", fmtRaw(run.data_source)],
        ["Start Datetime", fmtRaw(run.start_datetime)],
        ["Stop Datetime", fmtRaw(run.stop_datetime)],
        ["Start Equity", fmtNumber(run.start_value, 2)],
        ["End Equity", fmtNumber(run.end_value, 2)],
        ["Return (%)", fmtPct(run.return_pct)],
        ["Max Drawdown (%)", fmtPct(run.max_drawdown_pct)],
        ["Sharpe Ratio", fmtNumber(run.sharpe_ratio, 3)],
        ["Total Trades", fmtNumber(run.total_trades, 0)],
        ["Won Trades", fmtNumber(run.won_trades, 0)],
        ["Lost Trades", fmtNumber(run.lost_trades, 0)],
      ];
      const body = document.getElementById("run-metrics-body");
      body.innerHTML = rows.map(([k, v]) => `
        <tr>
          <td><strong>${{k}}</strong></td>
          <td>${{v}}</td>
        </tr>
      `).join("");
    }}

    function renderRun(run) {{
      document.getElementById("run-meta").innerText =
        `Strategy=${{run.strategy}} | Data=${{run.data_source}} | Status=${{run.status}} | Start=${{fmtRaw(run.start_datetime)}} | Stop=${{fmtRaw(run.stop_datetime)}}`;
      renderRunDetails(run);

      const curve = run.equity_curve || [];
      Plotly.newPlot("equity-plot", [{{
        x: curve.map(p => p.datetime),
        y: curve.map(p => p.value),
        type: "scatter",
        mode: "lines+markers",
        line: {{ color: "#3949ab", width: 3 }},
        marker: {{ size: 5 }},
        hovertemplate: "%{{x}}<br>Equity: %{{y:.2f}}<extra></extra>",
      }}], {{
        title: `Equity Curve - ${{run.run_id}}`,
        xaxis: {{ title: "Datetime" }},
        yaxis: {{ title: "Portfolio Value" }},
        margin: {{ t: 50, r: 25, b: 65, l: 70 }},
      }}, {{ responsive: true }});
      renderRunMetricsTable(run);

      const ordersBody = document.getElementById("orders-body");
      const sampleOrders = (run.orders || []).slice(0, 20);
      ordersBody.innerHTML = sampleOrders.length
        ? sampleOrders.map(o => `
          <tr>
            <td>${{fmtDateTime(o.datetime)}}</td>
            <td><span class="chip">${{o.is_buy ? "BUY" : "SELL"}}</span></td>
            <td>${{o.status}}</td>
            <td>${{fmtNumber(o.size, 4)}}</td>
            <td>${{fmtNumber(o.price, 4)}}</td>
            <td>${{fmtNumber(o.value, 2)}}</td>
            <td>${{fmtNumber(o.commission, 4)}}</td>
          </tr>`).join("")
        : `<tr><td colspan="7">No order data for this run.</td></tr>`;

      const tradesBody = document.getElementById("trades-body");
      const sampleTrades = (run.trades || []).slice(0, 20);
      tradesBody.innerHTML = sampleTrades.length
        ? sampleTrades.map(t => `
          <tr>
            <td>${{fmtDateTime(t.datetime)}}</td>
            <td>${{fmtNumber(t.size, 4)}}</td>
            <td>${{fmtNumber(t.price, 4)}}</td>
            <td>${{fmtNumber(t.value, 2)}}</td>
            <td>${{fmtNumber(t.pnl, 2)}}</td>
            <td>${{fmtNumber(t.pnlcomm, 2)}}</td>
            <td>${{pickTradeType(t)}}</td>
          </tr>`).join("")
        : `<tr><td colspan="7">No trade data for this run.</td></tr>`;
    }}

    function renderRunSelector() {{
      const select = document.getElementById("run-select");
      select.innerHTML = data.runs.map((run, idx) => {{
        const statusClass = run.status === "success" ? "status-success" : "status-failed";
        return `<option value="${{idx}}">${{run.run_id}} (${{run.status}})</option>`;
      }}).join("");
      M.FormSelect.init(select);

      select.addEventListener("change", (e) => {{
        const idx = Number(e.target.value);
        renderRun(data.runs[idx]);
      }});
      renderRun(data.runs[0]);
    }}

    document.addEventListener("DOMContentLoaded", function() {{
      M.AutoInit();
      renderMetrics();
      renderInputConfig();
      renderStatusPie();
      renderReturnsBar();
      renderExampleCandlestick();
      if (data.runs.length > 0) renderRunSelector();
    }});
  </script>
</body>
</html>
"""


def generate_html_report(input_json: Path, output_html: Path, title: str = "Backtest Report") -> None:
    report = BacktestReport.model_validate_json(input_json.read_text(encoding="utf-8"))
    view = _build_view_model(report)
    html = _render_html(view, title)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html, encoding="utf-8")
