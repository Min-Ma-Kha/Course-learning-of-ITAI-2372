/*
  charts.js - tiny hand-made charts (no libraries needed).
  Course: ITAI 2372 - Module 04 | Project: NextDollar Compass

  Charts.money(x)         -> "$1,234"
  Charts.bars(el, rows)   -> horizontal bar list   rows: [{label, value, color}]
  Charts.stack(el, segs)  -> one stacked bar       segs: [{label, value, color}]
  Charts.lines(el, opts)  -> line chart over months (SVG)
*/
(function () {
  const fmt0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

  function money(x) {
    if (x === null || x === undefined || isNaN(x)) return "-";
    return fmt0.format(Math.round(x));
  }
  function short(x) {
    const a = Math.abs(x);
    if (a >= 1e6) return "$" + (x / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (a >= 1e3) return "$" + Math.round(x / 1e3) + "k";
    return "$" + Math.round(x);
  }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function bars(el, rows, opts = {}) {
    const max = Math.max(1, ...rows.map(r => r.value));
    el.innerHTML = rows.map(r => `
      <div class="bar-row" title="${esc(r.label)}: ${money(r.value)}">
        <span class="lab">${esc(r.label)}</span>
        <span class="track"><span class="fill" style="width:${(100 * r.value / max).toFixed(1)}%;background:${r.color}"></span></span>
        <span class="val">${money(r.value)}${opts.suffix || ""}</span>
      </div>`).join("");
  }

  function stack(el, segs, opts = {}) {
    const total = segs.reduce((s, x) => s + Math.max(0, x.value), 0) || 1;
    el.innerHTML = segs.filter(s => s.value > 0).map(s => {
      const pct = 100 * s.value / total;
      const text = pct >= 9 ? `${esc(s.short || s.label)} ${Math.round(pct)}%` : "";
      return `<span style="flex:${s.value} 1 0;background:${s.color}" title="${esc(s.label)}: ${money(s.value)} (${pct.toFixed(0)}%)">${text}</span>`;
    }).join("");
    if (opts.legend) {
      const lg = document.createElement("p");
      lg.className = "legend";
      lg.innerHTML = segs.filter(s => s.value > 0).map(s => `<span><i style="background:${s.color}"></i>${esc(s.label)} ${money(s.value)}</span>`).join("");
      opts.legend.innerHTML = "";
      opts.legend.appendChild(lg);
    }
  }

  // Line chart: series = [{name, color, values:[...] }], one value per month.
  function lines(el, { series, startDate = new Date(), height = 260, markers = [] }) {
    const W = 760, H = height, L = 56, R = 16, T = 14, B = 34;
    const n = Math.max(...series.map(s => s.values.length), 2);
    const maxY = Math.max(1, ...series.flatMap(s => s.values));
    const niceMax = niceCeil(maxY);
    const x = i => L + (W - L - R) * (i / (n - 1));
    const y = v => T + (H - T - B) * (1 - v / niceMax);
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Balances over time">`;
    for (let k = 0; k <= 4; k++) {
      const v = niceMax * k / 4, yy = y(v);
      svg += `<line class="grid" x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}"/>`;
      svg += `<text x="${L - 8}" y="${yy + 4}" text-anchor="end">${short(v)}</text>`;
    }
    const years = Math.ceil(n / 12);
    const stepYears = years > 20 ? 5 : years > 8 ? 2 : 1;
    for (let yr = 0; yr <= years; yr += stepYears) {
      const i = Math.min(n - 1, yr * 12);
      const label = startDate.getFullYear() + yr;
      svg += `<text x="${x(i)}" y="${H - 10}" text-anchor="middle">${label}</text>`;
    }
    markers.forEach(m => {
      if (m.month < 1 || m.month > n) return;
      const xx = x(m.month - 1);
      svg += `<line x1="${xx}" x2="${xx}" y1="${T}" y2="${H - B}" stroke="${m.color}" stroke-dasharray="3 4" opacity=".7"/>`;
    });
    series.forEach(s => {
      if (!s.values.length) return;
      const pts = s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
      svg += `<polyline fill="none" stroke="${s.color}" stroke-width="2.5" stroke-linejoin="round" points="${pts}"/>`;
    });
    svg += `</svg>`;
    const legend = `<p class="legend">${series.map(s => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}</p>`;
    el.innerHTML = svg + legend;
  }

  function niceCeil(v) {
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }

  window.Charts = { money, short, esc, bars, stack, lines };
})();
