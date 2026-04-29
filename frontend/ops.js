const TZ = "America/New_York";

function fmtEt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", { timeZone: TZ });
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
      tr.innerHTML = `
        <td><code>${escapeHtml(row.job_key)}</code></td>
        <td>${fmtEt(row.last_success_at)}</td>
        <td class="sha">${row.run_id != null ? String(row.run_id) : "—"}</td>
      `;
      body.appendChild(tr);
    }
  } catch (e) {
    el.textContent = "Could not load summary: " + e.message;
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
      const tr = document.createElement("tr");
      const ok = row.exit_code === 0;
      const exitClass = row.exit_code == null ? "" : ok ? "exit-ok" : "exit-fail";
      const exitText = row.exit_code == null ? "—" : String(row.exit_code);
      const sha = row.git_sha ? row.git_sha.slice(0, 7) : "—";
      tr.innerHTML = `
        <td>${row.id}</td>
        <td><code>${escapeHtml(row.job_key)}</code></td>
        <td>${fmtEt(row.started_at)}</td>
        <td>${fmtEt(row.finished_at)}</td>
        <td class="${exitClass}">${exitText}</td>
        <td>${escapeHtml(row.hostname || "—")}</td>
        <td class="sha" title="${escapeAttr(row.git_sha || "")}">${sha}</td>
      `;
      body.appendChild(tr);
    }
  } catch (e) {
    el.textContent = "Could not load runs: " + e.message;
  }
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

async function refresh() {
  await Promise.all([loadSummary(), loadRuns()]);
}

document.getElementById("refreshBtn").addEventListener("click", refresh);
refresh();
