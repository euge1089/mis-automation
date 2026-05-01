const TZ = "America/New_York";

function fmtEt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", { timeZone: TZ });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function fmtBytes(n) {
  if (n == null || typeof n !== "number") return "—";
  const gb = n / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(2)} GB`;
  const mb = n / 1024 ** 2;
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  const kb = n / 1024;
  return `${kb.toFixed(0)} KB`;
}

function truncateErr(s, maxLen) {
  if (!s) return "";
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen) + "…";
}

let historyCountsCache = { sold: [], rented: [] };

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  return el;
}

function historyWindowRows(rows) {
  const sel = document.getElementById("historyMonthsWindow");
  const val = sel ? sel.value : "24";
  if (val === "all") return rows;
  const n = parseInt(val, 10);
  if (!Number.isFinite(n) || n <= 0) return rows;
  return rows.slice(-n);
}

function compactInt(n) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n || 0);
}

function formatMonthLabel(yyyyMm, { shortYear = false } = {}) {
  const m = /^(\d{4})-(\d{2})$/.exec(String(yyyyMm || ""));
  if (!m) return String(yyyyMm || "");
  const year = Number(m[1]);
  const month = Number(m[2]);
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) {
    return String(yyyyMm || "");
  }
  const d = new Date(Date.UTC(year, month - 1, 1));
  const monthName = d.toLocaleString("en-US", { month: "short", timeZone: "UTC" });
  const yearPart = shortYear ? String(year).slice(-2) : String(year);
  return `${monthName} ${yearPart}`;
}

function drawHistoryChart(svgId, hoverId, rows) {
  const svg = document.getElementById(svgId);
  const hover = document.getElementById(hoverId);
  if (!svg || !hover) return;
  svg.innerHTML = "";
  hover.textContent = "";

  const data = historyWindowRows(rows || []);
  const baseHeight = 340;
  const minWidth = 900;
  const pxPerBar = 42;
  const width = Math.max(minWidth, data.length * pxPerBar + 90);
  const height = baseHeight;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.style.width = `${width}px`;

  const margin = { top: 18, right: 12, bottom: 34, left: 44 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  if (!data.length) {
    const t = svgEl("text", { x: width / 2, y: height / 2, "text-anchor": "middle", class: "history-tick-label" });
    t.textContent = "No history rows yet";
    svg.appendChild(t);
    return;
  }

  const maxCount = Math.max(...data.map((d) => d.count || 0), 1);
  const yTicks = 4;

  for (let i = 0; i <= yTicks; i += 1) {
    const ratio = i / yTicks;
    const y = margin.top + plotH - ratio * plotH;
    const tickVal = Math.round(maxCount * ratio);
    svg.appendChild(svgEl("line", { x1: margin.left, y1: y, x2: margin.left + plotW, y2: y, class: "history-grid" }));
    const tickLabel = svgEl("text", {
      x: margin.left - 6,
      y: y + 3,
      "text-anchor": "end",
      class: "history-tick-label",
    });
    tickLabel.textContent = compactInt(tickVal);
    svg.appendChild(tickLabel);
  }

  const barW = Math.max(10, plotW / data.length);

  svg.appendChild(svgEl("line", { x1: margin.left, y1: margin.top + plotH, x2: margin.left + plotW, y2: margin.top + plotH, class: "history-axis" }));
  svg.appendChild(svgEl("line", { x1: margin.left, y1: margin.top, x2: margin.left, y2: margin.top + plotH, class: "history-axis" }));

  data.forEach((d, i) => {
    const count = d.count || 0;
    const h = (count / maxCount) * plotH;
    const x = margin.left + i * barW + 1;
    const y = margin.top + plotH - h;
    const w = Math.max(1.5, barW - 2);
    const rect = svgEl("rect", { x, y, width: w, height: Math.max(1, h), class: "history-bar" });
    rect.addEventListener("mouseenter", () => {
      hover.textContent = `${formatMonthLabel(d.month)}: ${count.toLocaleString()} listing(s)`;
    });
    rect.appendChild(svgEl("title"));
    rect.lastChild.textContent = `${formatMonthLabel(d.month)}: ${count.toLocaleString()}`;
    svg.appendChild(rect);

    const valLabel = svgEl("text", {
      x: x + w / 2,
      y: Math.max(margin.top + 8, y - 4),
      "text-anchor": "middle",
      class: "history-value-label",
    });
    valLabel.textContent = count.toLocaleString();
    if (w < 30) {
      valLabel.setAttribute("font-size", "7");
      valLabel.textContent = compactInt(count);
    }
    svg.appendChild(valLabel);

    const label = svgEl("text", {
      x: x + w / 2,
      y: margin.top + plotH + 12,
      "text-anchor": "middle",
      class: "history-tick-label",
    });
    label.textContent = formatMonthLabel(d.month, { shortYear: data.length > 24 });
    if (data.length > 18) {
      label.setAttribute("transform", `rotate(-45 ${x + w / 2} ${margin.top + plotH + 12})`);
      label.setAttribute("text-anchor", "end");
    }
    svg.appendChild(label);
  });
}

function renderHistoryCharts() {
  drawHistoryChart("soldMonthlyChart", "soldChartHover", historyCountsCache.sold);
  drawHistoryChart("rentedMonthlyChart", "rentedChartHover", historyCountsCache.rented);
}

async function loadHistoryMonthlyCounts() {
  const statusEl = document.getElementById("historyCountsStatus");
  if (!statusEl) return;
  statusEl.textContent = "Loading…";
  try {
    const r = await fetch("/ops/history-monthly-counts");
    if (!r.ok) throw new Error(r.statusText);
    const payload = await r.json();
    historyCountsCache = {
      sold: Array.isArray(payload.sold) ? payload.sold : [],
      rented: Array.isArray(payload.rented) ? payload.rented : [],
    };
    statusEl.textContent = "";
    renderHistoryCharts();
  } catch (e) {
    statusEl.textContent = "Could not load monthly history charts: " + e.message;
  }
}

async function loadAlerts() {
  const statusEl = document.getElementById("alertsStatus");
  const body = document.getElementById("alertsBody");
  statusEl.textContent = "Loading…";
  body.innerHTML = "";
  try {
    const r = await fetch("/ops/alerts");
    if (!r.ok) throw new Error(r.statusText);
    const bundle = await r.json();
    statusEl.textContent = "";

    const slackLine = bundle.slack_configured
      ? "Slack notifications are configured on this server (failures may post to your channel)."
      : "Slack notifications are not configured — use this page as the main place to review runs.";

    const drop = bundle.daily_active_drop;
    const dropClass =
      drop.status === "warn" ? "alert-drop warn" : drop.status === "ok" ? "alert-drop ok" : "alert-drop muted";

    const blurbs = bundle.alert_blurbs || {};
    const staticBits = [
      blurbs.slack ? `<p class="alert-static">${escapeHtml(blurbs.slack)}</p>` : "",
      blurbs.active_drop ? `<p class="alert-static">${escapeHtml(blurbs.active_drop)}</p>` : "",
      blurbs.sold_rent_min ? `<p class="alert-static">${escapeHtml(blurbs.sold_rent_min)}</p>` : "",
    ].join("");

    body.innerHTML = `
      <div class="alert-card">
        <p class="alert-title">Notifications</p>
        <p>${escapeHtml(slackLine)}</p>
      </div>
      <div class="alert-card ${dropClass}">
        <p class="alert-title">Active listings vs last success</p>
        <p class="alert-drop-msg">${escapeHtml(drop.message)}</p>
        <p class="ops-muted small">
          Sharp-drop warning threshold: ${bundle.active_drop_threshold_pct}%.
          Sold/rent quality checks may use a minimum of about ${bundle.sold_rent_min_rows} rows where configured.
        </p>
      </div>
      <div class="alert-card">
        <p class="alert-title">How to read these checks</p>
        ${staticBits}
      </div>
    `;
  } catch (e) {
    statusEl.textContent = "Could not load alerts: " + e.message;
  }
}

async function loadCatalog() {
  const statusEl = document.getElementById("catalogStatus");
  const body = document.getElementById("catalogBody");
  statusEl.textContent = "Loading…";
  body.innerHTML = "";
  try {
    const r = await fetch("/ops/catalog");
    if (!r.ok) throw new Error(r.statusText);
    const items = await r.json();
    statusEl.textContent = items.length ? "" : "No job descriptions available.";
    for (const item of items) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>
          <div class="cell-title">${escapeHtml(item.title)}</div>
          <div class="cell-meta"><code>${escapeHtml(item.job_key)}</code></div>
        </td>
        <td>${escapeHtml(item.what_it_does)}</td>
        <td>${escapeHtml(item.success_means)}</td>
        <td>${escapeHtml(item.schedule_hint)}</td>
      `;
      body.appendChild(tr);
    }
  } catch (e) {
    statusEl.textContent = "Could not load job descriptions: " + e.message;
  }
}

async function loadSummary() {
  const el = document.getElementById("summaryStatus");
  const body = document.getElementById("summaryBody");
  el.textContent = "Loading…";
  body.innerHTML = "";
  try {
    const r = await fetch("/ops/summary");
    if (!r.ok) throw new Error(r.statusText);
    const rows = await r.json();
    el.textContent = rows.length ? "" : "No successful runs recorded yet.";
    for (const row of rows) {
      const tr = document.createElement("tr");
      const title = row.title || row.job_key;
      const sub = row.one_liner ? `<div class="cell-sub">${escapeHtml(row.one_liner)}</div>` : "";
      tr.innerHTML = `
        <td>
          <div class="cell-title">${escapeHtml(title)}</div>
          ${sub}
          <div class="cell-meta"><code>${escapeHtml(row.job_key)}</code></div>
        </td>
        <td>${fmtEt(row.last_success_at)}</td>
        <td>${escapeHtml(nextScheduledRunLabel(row.job_key))}</td>
        <td class="sha">${row.run_id != null ? String(row.run_id) : "—"}</td>
      `;
      body.appendChild(tr);
    }
  } catch (e) {
    el.textContent = "Could not load summary: " + e.message;
  }
}

function nextScheduledRunLabel(jobKey) {
  const key = String(jobKey || "");
  if (key === "daily-active") return "Daily (cron)";
  if (key === "weekly-sold-rented") return "Weekly (cron)";
  if (key === "monthly") return "Monthly (cron)";
  return "—";
}

function cardLast(label, snap, hint) {
  const fin = snap && snap.finished_at ? fmtEt(snap.finished_at) : "—";
  const rid = snap && snap.run_id != null ? `#${snap.run_id}` : "—";
  return `
    <article class="overview-card" title="${escapeAttr(hint)}">
      <p class="overview-card-label">${escapeHtml(label)}</p>
      <p class="overview-card-main">${fin}</p>
      <p class="overview-card-meta">Run ${escapeHtml(rid)}</p>
    </article>
  `;
}

async function loadOverview() {
  const el = document.getElementById("overviewStatus");
  const strip = document.getElementById("overviewStrip");
  const fresh = document.getElementById("overviewFreshness");
  el.textContent = "Loading…";
  strip.innerHTML = "";
  fresh.textContent = "";
  try {
    const r = await fetch("/ops/overview");
    if (!r.ok) throw new Error(r.statusText);
    const o = await r.json();
    el.textContent = "";
    strip.innerHTML = [
      cardLast(
        "Daily listings job",
        o.last_success_daily_active,
        "Last time the daily active listings pipeline finished without errors."
      ),
      cardLast(
        "Weekly sold & rented job",
        o.last_success_weekly,
        "Last time the weekly sold/rented pipeline finished without errors."
      ),
      cardLast(
        "Load database job",
        o.last_success_load_db,
        "Last time load-db finished OK (if you run it on its own schedule)."
      ),
    ].join("");
    const fr = o.active_listings_freshness || {};
    fresh.innerHTML = `<p class="overview-fresh">${escapeHtml(fr.message || "")}</p>`;
    if (o.extended_host_metrics && Object.keys(o.extended_host_metrics).length) {
      const bits = Object.entries(o.extended_host_metrics)
        .map(([k, v]) => `${k}: ${escapeHtml(String(v))}`)
        .join(" · ");
      fresh.innerHTML += `<p class="ops-muted small">${bits}</p>`;
    }
  } catch (e) {
    el.textContent = "Could not load overview: " + e.message;
  }
}

async function loadDisk() {
  const el = document.getElementById("diskStatus");
  const box = document.getElementById("diskCard");
  el.textContent = "Loading…";
  box.innerHTML = "";
  try {
    const r = await fetch("/ops/disk");
    if (!r.ok) throw new Error(r.statusText);
    const d = await r.json();
    el.textContent = "";
    const pct = d.filesystem_used_pct;
    const heavy = d.heavy_dirs_bytes || {};
    const heavyLines = ["downloads", "history", "logs"]
      .filter((k) => Object.prototype.hasOwnProperty.call(heavy, k))
      .map((k) => {
        const b = heavy[k];
        return `<li><code>${escapeHtml(k)}</code>: ${b != null ? escapeHtml(fmtBytes(b)) : "—"}</li>`;
      })
      .join("");
    box.innerHTML = `
      <p class="disk-line"><strong>${pct}%</strong> of disk in use on this server’s project volume.</p>
      <p class="disk-line">About <strong>${fmtBytes(d.filesystem_free_bytes)}</strong> free of ${fmtBytes(
        d.filesystem_total_bytes
      )} total.</p>
      <p class="ops-muted small">Heavy folders under the project (approximate size):</p>
      <ul class="disk-heavy">${heavyLines}</ul>
    `;
  } catch (e) {
    el.textContent = "Could not load disk info: " + e.message;
  }
}

async function loadBackup() {
  const el = document.getElementById("backupStatus");
  const box = document.getElementById("backupCard");
  el.textContent = "Loading…";
  box.innerHTML = "";
  try {
    const r = await fetch("/ops/backup-status");
    if (!r.ok) throw new Error(r.statusText);
    const b = await r.json();
    el.textContent = "";
    const pathLine = b.heartbeat_path
      ? `<p class="ops-muted small">File: ${escapeHtml(b.heartbeat_path)}</p>`
      : "";
    box.innerHTML = `
      <p>${escapeHtml(b.message)}</p>
      <p class="disk-line"><strong>Last backup (UTC):</strong> ${escapeHtml(b.last_backup_utc || "—")}</p>
      ${pathLine}
    `;
  } catch (e) {
    el.textContent = "Could not load backup status: " + e.message;
  }
}

async function loadSchedule() {
  const el = document.getElementById("scheduleStatus");
  const body = document.getElementById("scheduleBody");
  el.textContent = "Loading…";
  body.innerHTML = "";
  try {
    const r = await fetch("/ops/schedule-status");
    if (!r.ok) throw new Error(r.statusText);
    const rows = await r.json();
    el.textContent = rows.length ? "" : "No jobs in catalog.";
    for (const row of rows) {
      const tr = document.createElement("tr");
      const exit = row.last_run_exit_code;
      const exitLabel =
        exit == null ? "—" : exit === 0 ? "OK" : `Exit ${exit}`;
      tr.innerHTML = `
        <td>
          <div class="cell-title">${escapeHtml(row.title)}</div>
          <div class="cell-meta"><code>${escapeHtml(row.job_key)}</code></div>
          <div class="cell-sub">${escapeHtml(row.schedule_hint)}</div>
        </td>
        <td>${fmtEt(row.last_run_started_at)}</td>
        <td>${escapeHtml(exitLabel)}</td>
        <td>${fmtEt(row.last_success_at)}</td>
      `;
      body.appendChild(tr);
    }
  } catch (e) {
    el.textContent = "Could not load schedule table: " + e.message;
  }
}

function runCardClass(row) {
  if (row.exit_code == null) return "run-card unknown";
  return row.exit_code === 0 ? "run-card ok" : "run-card bad";
}

function technicalDetails(row) {
  const detail = row.detail_json;
  if (!detail || typeof detail !== "object") return "";
  const pretty = escapeHtml(JSON.stringify(detail, null, 2));
  return `
    <details class="run-tech">
      <summary>Technical details (JSON)</summary>
      <pre class="run-pre">${pretty}</pre>
    </details>
  `;
}

async function fetchLogTail(jobKey, lines = 320) {
  const r = await fetch(`/ops/log-tail?job_key=${encodeURIComponent(jobKey)}&lines=${lines}`, {
    credentials: "same-origin",
  });
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

async function openLogModal(jobKey) {
  const modal = document.getElementById("logModal");
  const title = document.getElementById("logModalTitle");
  const pathEl = document.getElementById("logModalPath");
  const body = document.getElementById("logModalBody");
  title.textContent = jobKey;
  pathEl.textContent = "Loading…";
  body.textContent = "";
  if (typeof modal.showModal === "function") modal.showModal();
  try {
    const data = await fetchLogTail(jobKey);
    pathEl.textContent = data.resolved_path ? data.resolved_path : "—";
    if (data.error) {
      body.textContent = `${data.content || ""}\n\n---\n${data.error}`;
    } else {
      body.textContent = data.content || "(empty)";
    }
  } catch (e) {
    pathEl.textContent = "";
    body.textContent = "Could not load log: " + e.message;
  }
}

async function openRunExcerptModal(runId) {
  const modal = document.getElementById("logModal");
  const title = document.getElementById("logModalTitle");
  const pathEl = document.getElementById("logModalPath");
  const body = document.getElementById("logModalBody");
  title.textContent = `Log excerpt · run #${runId}`;
  pathEl.textContent = "Loading…";
  body.textContent = "";
  if (typeof modal.showModal === "function") modal.showModal();
  try {
    const r = await fetch(`/ops/runs/${encodeURIComponent(runId)}/log-excerpt?max_lines=250`, {
      credentials: "same-origin",
    });
    if (!r.ok) throw new Error(r.statusText);
    const data = await r.json();
    pathEl.textContent = data.resolved_path ? data.resolved_path : "—";
    let text = data.content || "(empty)";
    if (data.note) text += `\n\n---\n${data.note}`;
    body.textContent = text;
  } catch (e) {
    pathEl.textContent = "";
    body.textContent = "Could not load log excerpt: " + e.message;
  }
}

function runsQueryParams() {
  const status = document.getElementById("runsStatusFilter")?.value || "all";
  const sort = document.getElementById("runsSortSelect")?.value || "recent";
  return new URLSearchParams({ limit: "50", status, sort });
}

async function loadRuns() {
  const el = document.getElementById("runsStatus");
  const body = document.getElementById("runsBody");
  el.textContent = "Loading…";
  body.innerHTML = "";
  try {
    const r = await fetch(`/ops/runs?${runsQueryParams()}`);
    if (!r.ok) throw new Error(r.statusText);
    const rows = await r.json();
    el.textContent = rows.length ? "" : "No runs yet — run a pipeline or wait for cron.";
    for (const row of rows) {
      const article = document.createElement("article");
      article.className = runCardClass(row);
      const sha = row.git_sha ? row.git_sha.slice(0, 7) : "—";
      const metrics =
        row.metric_lines && row.metric_lines.length
          ? `<ul class="run-metrics">${row.metric_lines.map((ln) => `<li>${escapeHtml(ln)}</li>`).join("")}</ul>`
          : '<p class="ops-muted small">No saved counts for this job type yet (older runs or jobs without file metrics).</p>';

      const errBlock = row.error_summary
        ? `<p class="run-err" title="${escapeAttr(row.error_summary)}"><strong>Error:</strong> ${escapeHtml(
            truncateErr(row.error_summary, 200)
          )}</p>`
        : "";

      article.innerHTML = `
        <header class="run-head">
          <div>
            <p class="run-id">Run #${row.id} · <code>${escapeHtml(row.job_key)}</code></p>
            <h3 class="run-title">${escapeHtml(row.title)}</h3>
            <p class="run-oneliner">${escapeHtml(row.one_liner)}</p>
          </div>
          <span class="run-badge">${escapeHtml(row.headline_status)}</span>
        </header>
        <p class="run-success">${escapeHtml(row.success_message)}</p>
        ${errBlock}
        ${metrics}
        <p class="run-actions run-actions-row">
          <button type="button" class="ops-btn-secondary" data-run-excerpt="${row.id}">
            Log lines for this run
          </button>
          <button type="button" class="ops-btn-secondary" data-log-job="${escapeAttr(row.job_key)}">
            Rolling log (whole file tail)
          </button>
        </p>
        <p class="run-meta">
          Started ${fmtEt(row.started_at)} · Finished ${fmtEt(row.finished_at)}
          · Host ${escapeHtml(row.hostname || "—")}
          · Git <span class="sha" title="${escapeAttr(row.git_sha || "")}">${sha}</span>
        </p>
        ${technicalDetails(row)}
      `;
      body.appendChild(article);
    }
  } catch (e) {
    el.textContent = "Could not load runs: " + e.message;
  }
}

async function refresh() {
  await Promise.all([
    loadOverview(),
    loadHistoryMonthlyCounts(),
    loadDisk(),
    loadBackup(),
    loadAlerts(),
    loadCatalog(),
    loadSummary(),
    loadSchedule(),
    loadRuns(),
  ]);
}

document.getElementById("refreshBtn").addEventListener("click", refresh);

document.getElementById("runsBody").addEventListener("click", (e) => {
  const ex = e.target.closest("[data-run-excerpt]");
  if (ex) {
    openRunExcerptModal(parseInt(ex.getAttribute("data-run-excerpt"), 10));
    return;
  }
  const btn = e.target.closest("[data-log-job]");
  if (!btn) return;
  openLogModal(btn.getAttribute("data-log-job"));
});

document.getElementById("runsStatusFilter").addEventListener("change", () => {
  loadRuns();
});
document.getElementById("runsSortSelect").addEventListener("change", () => {
  loadRuns();
});

const historySel = document.getElementById("historyMonthsWindow");
if (historySel) {
  historySel.addEventListener("change", () => renderHistoryCharts());
}

document.getElementById("logModalClose").addEventListener("click", () => {
  const modal = document.getElementById("logModal");
  if (typeof modal.close === "function") modal.close();
});

document.getElementById("logViewerBtn").addEventListener("click", async () => {
  const jobKey = document.getElementById("logJobSelect").value;
  const pathEl = document.getElementById("logViewerPath");
  const pre = document.getElementById("logViewerPre");
  pathEl.textContent = "Loading…";
  pre.hidden = true;
  try {
    const data = await fetchLogTail(jobKey, 400);
    pathEl.textContent = data.resolved_path ? data.resolved_path : "—";
    pre.textContent = data.error ? `${data.content || ""}\n\n---\n${data.error}` : data.content || "(empty)";
    pre.hidden = false;
  } catch (e) {
    pathEl.textContent = "";
    pre.textContent = "Error: " + e.message;
    pre.hidden = false;
  }
});

refresh();
