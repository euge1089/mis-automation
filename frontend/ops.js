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
    statusEl.textContent = "";
    for (const item of items) {
      const card = document.createElement("article");
      card.className = "catalog-card";
      card.innerHTML = `
        <p class="catalog-key"><code>${escapeHtml(item.job_key)}</code></p>
        <h3 class="catalog-title">${escapeHtml(item.title)}</h3>
        <p class="catalog-oneliner">${escapeHtml(item.one_liner)}</p>
        <p><strong>What it does:</strong> ${escapeHtml(item.what_it_does)}</p>
        <p><strong>When it succeeded:</strong> ${escapeHtml(item.success_means)}</p>
        <p class="ops-muted small">${escapeHtml(item.schedule_hint)}</p>
      `;
      body.appendChild(card);
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
        <td class="sha">${row.run_id != null ? String(row.run_id) : "—"}</td>
      `;
      body.appendChild(tr);
    }
  } catch (e) {
    el.textContent = "Could not load summary: " + e.message;
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
  const r = await fetch(
    `/ops/log-tail?job_key=${encodeURIComponent(jobKey)}&lines=${lines}`,
    { credentials: "same-origin" }
  );
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

async function loadRuns() {
  const el = document.getElementById("runsStatus");
  const body = document.getElementById("runsBody");
  el.textContent = "Loading…";
  body.innerHTML = "";
  try {
    const r = await fetch("/ops/runs?limit=50");
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
        ${metrics}
        <p class="run-actions">
          <button type="button" class="ops-btn-secondary" data-log-job="${escapeAttr(row.job_key)}">
            View rolling server log for this job type
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
  await Promise.all([loadAlerts(), loadCatalog(), loadSummary(), loadRuns()]);
}

document.getElementById("refreshBtn").addEventListener("click", refresh);

document.getElementById("runsBody").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-log-job]");
  if (!btn) return;
  openLogModal(btn.getAttribute("data-log-job"));
});

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
