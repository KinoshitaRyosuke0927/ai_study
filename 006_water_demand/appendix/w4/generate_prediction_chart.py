"""
water_demand_model_per_emp.py の予測結果（社員×日ごとの消費量DataFrame）を基に、
翌月の消費量予測を可視化するHTML画面（prediction_chart.html）を生成する。

- 青色の折れ線・塗り: その日までの予測消費量の累積（実績未反映の当初予測）
- 赤色の直線        : モデルによる推奨注文量
- 緑色の折れ線      : 実績反映後の消費量の累積。実績がある日数分は実線、
                      実績が無くまだ再学習後モデルによる予測となっている日数分は破線で表示する
"""

import json
from pathlib import Path

import pandas as pd

import water_demand_model_per_emp as wdm

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output_data"
OUTPUT_DIR.mkdir(exist_ok=True)

# 当初予測（実績未反映、date_ym, emp_01, ..., emp_12）
prediction_df = wdm.prediction_df
if prediction_df is None:
    raise SystemExit("予測結果が算出できませんでした（出社・営業日カレンダー不足）。")

# 実績＋実績反映後の残り日数予測（同じ形式のDataFrame）
updated_df = wdm.updated_prediction_df

emp_cols = wdm.emp_cols
target_period = pd.Period(wdm.next_month_dt, "M")

# 当初予測：日ごとの合計消費量→累積
pred_dates = pd.to_datetime(prediction_df["date_ym"])
pred_daily_total = prediction_df[emp_cols].sum(axis=1)
days = pred_dates.dt.day.tolist()
predicted_cumulative = pred_daily_total.cumsum().round(2).tolist()

# モデルの推奨注文量（赤い直線の値）
order_quantity_line = round(float(wdm.prediction_rounded), 1)

# 実績反映後（実績＋残り日数予測）：日ごとの合計消費量→累積
updated_days = []
updated_cumulative = []
solid_until_day = 0
if updated_df is not None:
    updated_dates = pd.to_datetime(updated_df["date_ym"])
    updated_daily_total = updated_df[emp_cols].sum(axis=1)
    updated_days = updated_dates.dt.day.tolist()
    updated_cumulative = updated_daily_total.cumsum().round(2).tolist()

    # 実績データが存在する最終日（それ以前は実線＝実績、それ以降は破線＝予測として描画する）
    performance = wdm.water_demand_performance
    if len(performance):
        performance_dates = pd.to_datetime(performance["date_ym"])
        month_mask = performance_dates.dt.to_period("M") == target_period
        if month_mask.any():
            solid_until_day = int(performance_dates[month_mask].dt.day.max())

chart_data = {
    "targetMonthLabel": wdm.next_month_dt.strftime("%Y年%m月"),
    "days": days,
    "predictedCumulative": predicted_cumulative,
    "orderQuantityLine": order_quantity_line,
    "updatedDays": updated_days,
    "updatedCumulative": updated_cumulative,
    "solidUntilDay": solid_until_day,
}

HTML_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>水消費量 予測グラフ</title>
<style>
  :root {
    color-scheme: light dark;
    --surface: #ffffff;
    --ink-primary: #1a1f2b;
    --ink-secondary: #5b6472;
    --ink-muted: #8b93a1;
    --grid: #e4e8ee;
    --blue-line: #1f8fd4;
    --blue-fill: rgba(31, 143, 212, 0.16);
    --red-line: #d64545;
    --green-line: #2f9e58;
    --card-border: #e4e8ee;
    --tooltip-bg: #202430;
    --tooltip-ink: #f5f7fa;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --surface: #14171f;
      --ink-primary: #eef1f6;
      --ink-secondary: #a7afbd;
      --ink-muted: #6f7786;
      --grid: #2a2f3a;
      --blue-line: #57b3ea;
      --blue-fill: rgba(87, 179, 234, 0.18);
      --red-line: #ef6a6a;
      --green-line: #52c281;
      --card-border: #2a2f3a;
      --tooltip-bg: #eef1f6;
      --tooltip-ink: #14171f;
    }
  }
  :root[data-theme="dark"] {
    --surface: #14171f;
    --ink-primary: #eef1f6;
    --ink-secondary: #a7afbd;
    --ink-muted: #6f7786;
    --grid: #2a2f3a;
    --blue-line: #57b3ea;
    --blue-fill: rgba(87, 179, 234, 0.18);
    --red-line: #ef6a6a;
    --green-line: #52c281;
    --card-border: #2a2f3a;
    --tooltip-bg: #eef1f6;
    --tooltip-ink: #14171f;
  }
  :root[data-theme="light"] {
    --surface: #ffffff;
    --ink-primary: #1a1f2b;
    --ink-secondary: #5b6472;
    --ink-muted: #8b93a1;
    --grid: #e4e8ee;
    --blue-line: #1f8fd4;
    --blue-fill: rgba(31, 143, 212, 0.16);
    --red-line: #d64545;
    --green-line: #2f9e58;
    --card-border: #e4e8ee;
    --tooltip-bg: #202430;
    --tooltip-ink: #f5f7fa;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: "Hiragino Sans", "Yu Gothic", "Segoe UI", system-ui, sans-serif;
    background: var(--surface);
    color: var(--ink-primary);
    padding: 24px;
  }
  .card {
    max-width: 920px;
    margin: 0 auto;
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 20px 24px 24px;
  }
  h1 {
    font-size: 1.15rem;
    margin: 0 0 4px;
  }
  .subtitle {
    color: var(--ink-secondary);
    font-size: 0.85rem;
    margin: 0 0 18px;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    margin-bottom: 8px;
    font-size: 0.82rem;
    color: var(--ink-secondary);
  }
  .legend-item { display: flex; align-items: center; gap: 6px; }
  .swatch { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
  .swatch.dot { width: 9px; height: 9px; border-radius: 50%; }
  .swatch.dashed {
    height: 0;
    border-top: 2px dashed currentColor;
    border-radius: 0;
    background: none !important;
    color: inherit;
  }
  .chart-wrap { position: relative; }
  svg { width: 100%; height: auto; display: block; overflow: visible; }
  .axis-label { fill: var(--ink-muted); font-size: 11px; }
  .grid-line { stroke: var(--grid); stroke-width: 1; }
  .tick-label { fill: var(--ink-muted); font-size: 10.5px; }
  .crosshair { stroke: var(--ink-muted); stroke-width: 1; stroke-dasharray: 3 3; opacity: 0; }
  .hover-dot { opacity: 0; }
  .tooltip {
    position: absolute;
    pointer-events: none;
    background: var(--tooltip-bg);
    color: var(--tooltip-ink);
    font-size: 0.78rem;
    padding: 8px 10px;
    border-radius: 8px;
    line-height: 1.5;
    transform: translate(-50%, -110%);
    white-space: nowrap;
    opacity: 0;
    transition: opacity 0.08s ease;
    z-index: 5;
  }
  .tooltip b { font-weight: 600; }
  .row-blue { color: var(--blue-line); }
  .row-red { color: var(--red-line); }
  .row-green { color: var(--green-line); }
  .toolbar {
    display: flex;
    justify-content: flex-end;
    margin-top: 10px;
  }
  button.toggle {
    background: transparent;
    border: 1px solid var(--card-border);
    color: var(--ink-secondary);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 0.78rem;
    cursor: pointer;
  }
  button.toggle:hover { border-color: var(--ink-muted); }
  table.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
    margin-top: 12px;
    display: none;
  }
  table.data-table.show { display: table; }
  table.data-table th, table.data-table td {
    text-align: right;
    padding: 4px 8px;
    border-bottom: 1px solid var(--grid);
  }
  table.data-table th:first-child, table.data-table td:first-child { text-align: left; }
  .empty-note {
    color: var(--ink-muted);
    font-size: 0.78rem;
    margin-top: 8px;
  }
</style>
</head>
<body>
  <div class="card">
    <h1 id="title">水消費量予測</h1>
    <p class="subtitle" id="subtitle"></p>

    <div class="legend" id="legend"></div>

    <div class="chart-wrap">
      <svg id="chart" viewBox="0 0 760 380" preserveAspectRatio="xMidYMid meet"></svg>
      <div class="tooltip" id="tooltip"></div>
    </div>

    <div class="toolbar">
      <button class="toggle" id="toggleTable">表で見る</button>
    </div>
    <table class="data-table" id="dataTable">
      <thead>
        <tr><th>日</th><th>当初予測（累積 L）</th><th>実績/実績反映後予測（累積 L）</th><th>区分</th><th>推奨注文量 L</th></tr>
      </thead>
      <tbody id="dataTableBody"></tbody>
    </table>
  </div>

<script>
const DATA = __CHART_DATA__;

(function render(data) {
  const svg = document.getElementById("chart");
  const tooltip = document.getElementById("tooltip");
  const legend = document.getElementById("legend");
  const title = document.getElementById("title");
  const subtitle = document.getElementById("subtitle");

  title.textContent = `${data.targetMonthLabel} の水消費量予測`;
  subtitle.textContent = "当初予測（累積） / 推奨注文量 / 実績＋実績反映後の予測（累積）の比較";

  const W = 760, H = 380;
  const M = { top: 34, right: 20, bottom: 34, left: 54 };
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;

  const days = data.days;
  const maxDay = Math.max(...days, ...(data.updatedDays.length ? data.updatedDays : [0]));
  const rawMax = Math.max(
    data.orderQuantityLine,
    ...data.predictedCumulative,
    ...(data.updatedCumulative.length ? data.updatedCumulative : [0])
  ) * 1.12;

  // Y軸目盛りは20の倍数に固定する（目盛り数がおよそ8本以下になるよう刻み幅を20刻みで調整）
  let yStep = 20;
  while (rawMax / yStep > 8) yStep += 20;
  const maxVal = Math.ceil(rawMax / yStep) * yStep;
  const yTicks = maxVal / yStep;

  const x = (day) => M.left + ((day - 1) / Math.max(maxDay - 1, 1)) * plotW;
  const y = (val) => M.top + plotH - (val / maxVal) * plotH;

  const ns = "http://www.w3.org/2000/svg";
  function el(tag, attrs) {
    const e = document.createElementNS(ns, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  // --- グリッド線・Y軸目盛り（20の倍数固定）---
  for (let i = 0; i <= yTicks; i++) {
    const val = yStep * i;
    const gy = y(val);
    svg.appendChild(el("line", { x1: M.left, x2: W - M.right, y1: gy, y2: gy, class: "grid-line" }));
    const label = el("text", { x: M.left - 10, y: gy + 3, class: "tick-label", "text-anchor": "end" });
    label.textContent = val;
    svg.appendChild(label);
  }
  const yAxisLabel = el("text", {
    x: M.left, y: M.top - 16, class: "axis-label", "text-anchor": "start"
  });
  yAxisLabel.textContent = "水の消費量 (L)";
  svg.appendChild(yAxisLabel);

  // --- X軸目盛り（5日おき＋最終日）---
  const xTickDays = [];
  for (let d = 1; d <= maxDay; d += 5) xTickDays.push(d);
  if (xTickDays[xTickDays.length - 1] !== maxDay) xTickDays.push(maxDay);
  xTickDays.forEach((d) => {
    const gx = x(d);
    const label = el("text", { x: gx, y: H - M.bottom + 16, class: "tick-label", "text-anchor": "middle" });
    label.textContent = d;
    svg.appendChild(label);
  });
  const xAxisLabel = el("text", {
    x: W - M.right, y: H - 4, class: "axis-label", "text-anchor": "end"
  });
  xAxisLabel.textContent = "予測月の日数 (日)";
  svg.appendChild(xAxisLabel);

  // --- 予測の累積：塗り＋線 ---
  const predPoints = days.map((d, i) => [x(d), y(data.predictedCumulative[i])]);
  const areaPath = [
    `M ${x(days[0])} ${y(0)}`,
    ...predPoints.map((p) => `L ${p[0]} ${p[1]}`),
    `L ${x(days[days.length - 1])} ${y(0)}`,
    "Z",
  ].join(" ");
  svg.appendChild(el("path", { d: areaPath, fill: "var(--blue-fill)", stroke: "none" }));
  const predLine = predPoints.map((p, i) => (i === 0 ? "M" : "L") + ` ${p[0]} ${p[1]}`).join(" ");
  svg.appendChild(el("path", {
    d: predLine, fill: "none", stroke: "var(--blue-line)", "stroke-width": 2,
    "stroke-linecap": "round", "stroke-linejoin": "round",
  }));

  // --- 推奨注文量：赤い直線 ---
  const orderY = y(data.orderQuantityLine);
  svg.appendChild(el("line", {
    x1: M.left, x2: W - M.right, y1: orderY, y2: orderY,
    stroke: "var(--red-line)", "stroke-width": 2,
  }));

  // --- 実績＋実績反映後の予測：実績部分は実線、予測部分は破線で描画（同じ累積線をつなげる）---
  if (data.updatedDays.length) {
    const solidUntil = data.solidUntilDay;
    const points = data.updatedDays.map((d, i) => [d, x(d), y(data.updatedCumulative[i])]);
    const solidPoints = points.filter((p) => p[0] <= solidUntil);
    // 境界日を両方のセグメントに含めることで、実線と破線が視覚的につながるようにする
    const dashedPoints = points.filter((p) => p[0] >= solidUntil);

    if (solidPoints.length) {
      const solidPath = solidPoints.map((p, i) => (i === 0 ? "M" : "L") + ` ${p[1]} ${p[2]}`).join(" ");
      svg.appendChild(el("path", {
        d: solidPath, fill: "none", stroke: "var(--green-line)", "stroke-width": 2,
        "stroke-linecap": "round", "stroke-linejoin": "round",
      }));
    }
    if (dashedPoints.length > 1) {
      const dashedPath = dashedPoints.map((p, i) => (i === 0 ? "M" : "L") + ` ${p[1]} ${p[2]}`).join(" ");
      svg.appendChild(el("path", {
        d: dashedPath, fill: "none", stroke: "var(--green-line)", "stroke-width": 2,
        "stroke-linecap": "round", "stroke-linejoin": "round", "stroke-dasharray": "6 5",
      }));
    }
  }

  // --- 凡例 ---
  const legendItems = [
    { color: "var(--blue-line)", label: "当初予測（累積）" },
    { color: "var(--red-line)", label: "推奨注文量" },
  ];
  if (data.solidUntilDay > 0) {
    legendItems.push({ color: "var(--green-line)", label: "実績（累積）", dashed: false });
  }
  if (data.updatedDays.length && data.solidUntilDay < Math.max(...data.updatedDays)) {
    legendItems.push({ color: "var(--green-line)", label: "実績反映後の予測（累積）", dashed: true });
  }
  legendItems.forEach((it) => {
    const item = document.createElement("span");
    item.className = "legend-item";
    const swatchClass = it.dashed ? "swatch dashed" : "swatch";
    const swatchStyle = it.dashed ? `color:${it.color}` : `background:${it.color}`;
    item.innerHTML = `<span class="${swatchClass}" style="${swatchStyle}"></span>${it.label}`;
    legend.appendChild(item);
  });
  if (!data.solidUntilDay) {
    const note = document.createElement("div");
    note.className = "empty-note";
    note.textContent = "※ この予測対象月の実績データはまだ蓄積されていません。";
    legend.parentElement.insertBefore(note, legend.nextSibling);
  }

  // --- ホバー用クロスヘア・ツールチップ ---
  const crosshair = el("line", { x1: 0, x2: 0, y1: M.top, y2: H - M.bottom, class: "crosshair" });
  svg.appendChild(crosshair);
  const hoverDotPred = el("circle", { r: 4, fill: "var(--blue-line)", class: "hover-dot" });
  svg.appendChild(hoverDotPred);
  const hoverDotActual = el("circle", { r: 4, fill: "var(--green-line)", class: "hover-dot" });
  svg.appendChild(hoverDotActual);

  const hitArea = el("rect", {
    x: M.left, y: M.top, width: plotW, height: plotH, fill: "transparent",
  });
  svg.appendChild(hitArea);

  const updatedByDay = {};
  data.updatedDays.forEach((d, i) => {
    updatedByDay[d] = { value: data.updatedCumulative[i], isActual: d <= data.solidUntilDay };
  });

  function nearestDay(mouseX) {
    const ratio = (mouseX - M.left) / plotW;
    const day = Math.round(1 + ratio * (maxDay - 1));
    return Math.min(Math.max(day, 1), maxDay);
  }

  hitArea.addEventListener("mousemove", (evt) => {
    const rect = svg.getBoundingClientRect();
    const scale = W / rect.width;
    const mouseX = (evt.clientX - rect.left) * scale;
    const day = nearestDay(mouseX);
    const idx = days.indexOf(day);
    if (idx === -1) return;

    const gx = x(day);
    crosshair.setAttribute("x1", gx);
    crosshair.setAttribute("x2", gx);
    crosshair.style.opacity = 1;

    const predVal = data.predictedCumulative[idx];
    hoverDotPred.setAttribute("cx", gx);
    hoverDotPred.setAttribute("cy", y(predVal));
    hoverDotPred.style.opacity = 1;

    let updatedLine = "";
    if (updatedByDay[day] !== undefined) {
      const info = updatedByDay[day];
      hoverDotActual.setAttribute("cx", x(day));
      hoverDotActual.setAttribute("cy", y(info.value));
      hoverDotActual.style.opacity = 1;
      const label = info.isActual ? "実績" : "実績反映後の予測";
      updatedLine = `<div class="row-green">${label}: <b>${info.value.toFixed(1)} L</b></div>`;
    } else {
      hoverDotActual.style.opacity = 0;
    }

    tooltip.innerHTML = `
      <div><b>${day}日目</b></div>
      <div class="row-blue">当初予測: <b>${predVal.toFixed(1)} L</b></div>
      ${updatedLine}
      <div class="row-red">推奨注文量: <b>${data.orderQuantityLine.toFixed(1)} L</b></div>
    `;
    const rectWrap = svg.parentElement.getBoundingClientRect();
    tooltip.style.left = `${((gx / W) * rectWrap.width)}px`;
    tooltip.style.top = `${(y(predVal) / H) * rectWrap.height}px`;
    tooltip.style.opacity = 1;
  });

  hitArea.addEventListener("mouseleave", () => {
    crosshair.style.opacity = 0;
    hoverDotPred.style.opacity = 0;
    hoverDotActual.style.opacity = 0;
    tooltip.style.opacity = 0;
  });

  // --- テーブル表示（アクセシビリティ用の代替表示） ---
  const tbody = document.getElementById("dataTableBody");
  days.forEach((d, i) => {
    const tr = document.createElement("tr");
    const info = updatedByDay[d];
    tr.innerHTML = `
      <td>${d}</td>
      <td>${data.predictedCumulative[i].toFixed(1)}</td>
      <td>${info !== undefined ? info.value.toFixed(1) : "-"}</td>
      <td>${info !== undefined ? (info.isActual ? "実績" : "予測") : "-"}</td>
      <td>${data.orderQuantityLine.toFixed(1)}</td>
    `;
    tbody.appendChild(tr);
  });
  document.getElementById("toggleTable").addEventListener("click", (evt) => {
    const table = document.getElementById("dataTable");
    table.classList.toggle("show");
    evt.target.textContent = table.classList.contains("show") ? "グラフで見る" : "表で見る";
  });
})(DATA);
</script>
</body>
</html>
"""

html_out = HTML_TEMPLATE.replace("__CHART_DATA__", json.dumps(chart_data, ensure_ascii=False))
out_path = OUTPUT_DIR / "prediction_chart.html"
out_path.write_text(html_out, encoding="utf-8")
print(f"グラフ画面を書き出しました: {out_path}")
