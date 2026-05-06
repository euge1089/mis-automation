const statusEl = document.getElementById("status");

/**
 * API root for fetches. Empty = same origin (normal when FastAPI serves this HTML).
 * If the page is hosted separately, set data-api-base on the root html element to the API origin.
 */
function apiBase() {
  const fromDoc = document.documentElement?.dataset?.apiBase?.trim();
  if (fromDoc) return fromDoc.replace(/\/$/, "");
  const g = typeof window.__MLS_API_BASE__ === "string" ? window.__MLS_API_BASE__.trim() : "";
  if (g) return g.replace(/\/$/, "");
  return "";
}

function apiUrl(path) {
  const p = path.startsWith("/") ? path : `/${path}`;
  const b = apiBase();
  return b ? `${b}${p}` : p;
}
const loadingBarWrap = document.getElementById("loadingBarWrap");
const loadingBarFill = document.getElementById("loadingBarFill");
const resultsBody = document.querySelector("#resultsTable tbody");
const compBody = document.querySelector("#compTable tbody");
const searchBtn = document.getElementById("searchBtn");
const analyzeBtn = document.getElementById("analyzeListingBtn");
const listingCompsToggle = document.getElementById("listing_comps_toggle");

const AREA_METRIC_IDS = [
  "area_price_main",
  "area_price_range",
  "area_ppsf",
  "area_volume",
  "area_trend_summary",
  "area_active_summary",
  "area_active_note",
];

const LISTING_METRIC_IDS = [
  "listing_price_vs_area",
  "listing_price_band",
  "listing_ppsf",
  "listing_ppsf_note",
  "listing_payment",
  "listing_payment_note",
];

function showLoadingBarIndeterminate() {
  loadingBarWrap.hidden = false;
  loadingBarWrap.classList.add("indeterminate");
  loadingBarFill.style.width = "";
  loadingBarWrap.setAttribute("aria-valuenow", "0");
}

function setLoadingBarPercent(pct) {
  const p = Math.min(100, Math.max(0, Math.round(pct)));
  loadingBarWrap.classList.remove("indeterminate");
  loadingBarFill.style.width = `${p}%`;
  loadingBarWrap.hidden = false;
  loadingBarWrap.setAttribute("aria-valuenow", String(p));
}

function hideLoadingBar() {
  loadingBarWrap.hidden = true;
  loadingBarWrap.classList.remove("indeterminate");
  loadingBarFill.style.width = "0%";
  loadingBarWrap.setAttribute("aria-valuenow", "0");
}

function formatFreshness(date = new Date()) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function setFreshness(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value ? `Updated ${value}` : "";
}

function setQualityChip(id, label, tone = "neutral") {
  const el = document.getElementById(id);
  if (!el) return;
  if (!label) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `<span class="quality-chip quality-chip--${tone}">${escapeHtml(label)}</span>`;
}

function qualityFromCount(count, high = 30, medium = 12) {
  const n = Number(count || 0);
  if (n >= high) return { tone: "good", label: "High confidence" };
  if (n >= medium) return { tone: "medium", label: "Medium confidence" };
  if (n > 0) return { tone: "low", label: "Limited confidence" };
  return { tone: "neutral", label: "No confidence score yet" };
}

function setSkeletonState(ids, isLoading) {
  for (const id of ids) {
    const el = document.getElementById(id);
    if (!el) continue;
    if (isLoading) {
      el.classList.add("skeleton-block");
      if (!el.textContent.trim()) el.textContent = " ";
    } else {
      el.classList.remove("skeleton-block");
      if (el.textContent === " ") el.textContent = "";
    }
  }
}

function setTableSkeleton(selector, isLoading) {
  const el = document.querySelector(selector);
  if (!el) return;
  el.classList.toggle("table-skeleton", Boolean(isLoading));
}

function renderTrendSparkline(rows) {
  const wrap = document.getElementById("area_trend_sparkline");
  if (!wrap) return;
  if (!Array.isArray(rows) || rows.length < 2) {
    wrap.innerHTML = "";
    return;
  }
  const values = rows.map((r) => toNumberOrNull(r.median_price)).filter((v) => v != null);
  if (values.length < 2) {
    wrap.innerHTML = "";
    return;
  }
  const width = 220;
  const height = 52;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(1, max - min);
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = height - ((v - min) / range) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const trendUp = values[values.length - 1] >= values[0];
  wrap.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Recent sale trend">
      <polyline points="${points.join(" ")}" fill="none" stroke="${trendUp ? "#0f766e" : "#b91c1c"}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
  `;
}

function syncListingCompsToggleForViewport() {
  if (!listingCompsToggle) return;
  const isSmall = window.matchMedia("(max-width: 760px)").matches;
  if (isSmall && !listingCompsToggle.dataset.userTouched) {
    listingCompsToggle.open = false;
  }
  if (!isSmall) {
    listingCompsToggle.open = true;
  }
}

function renderListingTakeaways(summary, subject, carry) {
  const panel = document.getElementById("listing_takeaways");
  const list = document.getElementById("listing_takeaways_list");
  if (!panel || !list) return;
  const takeaways = [];
  const diffPct = toNumberOrNull(summary.list_vs_median_pct);
  const median = toNumberOrNull(summary.median_price);
  const totalSet = toNumberOrNull(summary.total_comps_considered);
  if (diffPct != null) {
    const dir = Math.abs(diffPct) < 1 ? "right around" : diffPct > 0 ? "above" : "below";
    takeaways.push(`This asking price is ${dir} typical nearby sale prices (${Math.abs(diffPct).toFixed(1)}% difference).`);
  }
  if (median != null) {
    takeaways.push(`Typical nearby sold price is about ${formatMoney(median)} for similar homes.`);
  }
  if (carry && carry.total) {
    takeaways.push(`Estimated monthly carrying cost is around ${formatMoney(carry.total)} before one-time closing costs.`);
  }
  if (totalSet != null && totalSet > 0) {
    takeaways.push(`Comparison confidence is based on ${totalSet} matching sales in the full comp set.`);
  }
  if (!takeaways.length) {
    panel.hidden = true;
    list.innerHTML = "";
    return;
  }
  list.innerHTML = takeaways.slice(0, 3).map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  panel.hidden = false;
}

function clearListingTakeaways() {
  const panel = document.getElementById("listing_takeaways");
  const list = document.getElementById("listing_takeaways_list");
  if (!panel || !list) return;
  panel.hidden = true;
  list.innerHTML = "";
}

function finishLoadingBar() {
  setLoadingBarPercent(100);
  return new Promise((r) => setTimeout(r, 280)).then(() => {
    hideLoadingBar();
  });
}

/**
 * Map backend: Mapbox GL when MAPBOX_ACCESS_TOKEN is set, otherwise Leaflet + OSM.
 * @type {{ mode: "none" | "leaflet" | "mapbox", map?: any, markerLayer?: any, markers?: any[] }}
 */
let mapBackend = { mode: "none" };
let mapReadyPromise = null;

function updateMapNote(mode) {
  const el = document.getElementById("map_note");
  if (!el) return;
  const base =
    "Most pins come from listing coordinates. If a listing is missing coordinates, we try to place " +
    "it by street address (which can be slightly off). Use this map as a guide, then confirm details " +
    "in the listing.";
  if (mode === "mapbox") {
    el.textContent = `${base} Map © Mapbox © OpenStreetMap.`;
  } else {
    el.textContent = `${base} Map data © OpenStreetMap contributors.`;
  }
}

function initMapBackend() {
  if (!mapReadyPromise) {
    mapReadyPromise = doInitMapBackend();
  }
  return mapReadyPromise;
}

async function doInitMapBackend() {
  const container = document.getElementById("map");
  if (!container || mapBackend.mode !== "none") {
    return;
  }

  let cfg = { mapbox_access_token: "", map_style_url: "mapbox://styles/mapbox/streets-v12" };
  try {
    const res = await fetch(apiUrl("/api/map-config"));
    if (res.ok) {
      cfg = { ...cfg, ...(await res.json()) };
    }
  } catch {
    /* fall through to OSM */
  }

  const token = String(cfg.mapbox_access_token || "").trim();
  const styleUrl = String(cfg.map_style_url || "mapbox://styles/mapbox/streets-v12").trim();

  if (token && typeof mapboxgl !== "undefined") {
    try {
      mapboxgl.accessToken = token;
      const map = new mapboxgl.Map({
        container: "map",
        style: styleUrl,
        center: [-71.0589, 42.3601],
        zoom: 9,
      });
      map.addControl(new mapboxgl.NavigationControl({ visualizePitch: false }), "top-right");
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("Mapbox style load timeout")), 20000);
        map.once("load", () => {
          clearTimeout(timer);
          resolve();
        });
        map.once("error", (e) => {
          clearTimeout(timer);
          reject(e.error || e);
        });
      });
      mapBackend = { mode: "mapbox", map, markers: [] };
      updateMapNote("mapbox");
      return;
    } catch (err) {
      console.warn("Mapbox init failed; using OpenStreetMap tiles.", err);
      container.innerHTML = "";
    }
  }

  const map = L.map("map").setView([42.3601, -71.0589], 9);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  const markerLayer = L.featureGroup().addTo(map);
  mapBackend = { mode: "leaflet", map, markerLayer };
  updateMapNote("leaflet");
}

function clearMapMarkers() {
  if (mapBackend.mode === "leaflet" && mapBackend.markerLayer) {
    mapBackend.markerLayer.clearLayers();
  } else if (mapBackend.mode === "mapbox" && Array.isArray(mapBackend.markers)) {
    for (const m of mapBackend.markers) {
      m.remove();
    }
    mapBackend.markers = [];
  }
}

/** Last search results; used to refresh carry columns when financing inputs change. */
let lastListingRows = null;
let lastListingRowsById = new Map();

/** Max listings we look up on the map per search (keeps the page responsive). */
const MAX_AUTO_GEOCODE_LOOKUPS = 30;

/**
 * Illustrative APRs for demo (not live market data). User should replace with a real quote.
 * ARM rows use initial fixed-period rates; amortization is 30 years.
 */
const MORTGAGE_PRESETS = {
  "30fixed": { label: "30-year fixed", months: 360, defaultAprPercent: 6.5 },
  "15fixed": { label: "15-year fixed", months: 180, defaultAprPercent: 5.875 },
  "71arm": { label: "7/1 ARM", months: 360, defaultAprPercent: 6.125 },
  "51arm": { label: "5/1 ARM", months: 360, defaultAprPercent: 6.0 },
  custom: { label: "Custom term", months: null, defaultAprPercent: 6.5 },
};

function toNumberOrNull(value) {
  if (value === "" || value == null) return null;
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  const s = String(value).trim();
  if (s === "" || s.toLowerCase() === "null" || s.toLowerCase() === "nan") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function escapeHtml(text) {
  if (text == null) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function hasLatLon(row) {
  return toNumberOrNull(row.latitude) != null && toNumberOrNull(row.longitude) != null;
}

function formatMoney(value) {
  if (value == null || !Number.isFinite(value)) return "";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatMoneyCompact(value) {
  if (value == null || !Number.isFinite(value)) return "";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
    notation: "compact",
    compactDisplay: "short",
  }).format(value);
}

function normalizeUsZip5(raw) {
  const digits = String(raw || "").replace(/\D/g, "");
  if (!digits) return "";
  if (digits.length >= 9) return digits.slice(0, 5);
  if (digits.length > 5) return digits.slice(0, 5);
  return digits.padStart(5, "0");
}

function hasAreaScope(params) {
  return params.has("zip_code") || params.has("town");
}

function renderEmptyTableRow(tbody, colSpan, message) {
  tbody.innerHTML = "";
  const tr = document.createElement("tr");
  tr.innerHTML = `<td colspan="${colSpan}" class="note">${escapeHtml(message)}</td>`;
  tbody.appendChild(tr);
}

function formatConfidenceLabel(raw) {
  const value = String(raw || "").trim().toLowerCase();
  if (!value) return "";
  if (value === "high") return "High (many rentals)";
  if (value === "medium") return "Medium (some rentals)";
  if (value === "low") return "Low (few rentals)";
  return raw;
}

function formatDateShort(raw) {
  if (!raw) return "";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return String(raw);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** Fixed-rate monthly payment (principal + interest). rateAnnual is decimal, e.g. 0.065 */
function monthlyPI(principal, rateAnnual, numPayments) {
  if (principal <= 0 || numPayments <= 0) return 0;
  const r = rateAnnual / 12;
  if (r <= 0) return principal / numPayments;
  const pow = Math.pow(1 + r, numPayments);
  return (principal * r * pow) / (pow - 1);
}

function getFinancingInputs() {
  const downPct = toNumberOrNull(document.getElementById("fin_down_pct").value) ?? 20;
  const ratePct = toNumberOrNull(document.getElementById("fin_rate").value);
  const insurance = toNumberOrNull(document.getElementById("fin_insurance").value) ?? 0;
  const misc = toNumberOrNull(document.getElementById("fin_misc").value) ?? 0;
  const product = document.getElementById("fin_product").value;
  const preset = MORTGAGE_PRESETS[product];
  let months = preset.months;
  if (product === "custom" || months == null) {
    const years = toNumberOrNull(document.getElementById("fin_term_years").value) ?? 30;
    months = Math.max(1, Math.round(years * 12));
  }
  const rateDec = ratePct != null ? ratePct / 100 : 0.065;
  return {
    downPct: Math.min(100, Math.max(0, downPct)),
    rateDec,
    insurance: Math.max(0, insurance),
    misc: Math.max(0, misc),
    months,
  };
}

/**
 * @returns {{ pi: number, taxMo: number|null, insurance: number, misc: number, total: number } | null}
 */
function computeCarryForRow(row) {
  const price = toNumberOrNull(row.list_price);
  if (price == null || price <= 0) return null;
  const { downPct, rateDec, insurance, misc, months } = getFinancingInputs();
  const loan = price * (1 - downPct / 100);
  const pi = monthlyPI(loan, rateDec, months);
  const annualTax = toNumberOrNull(row.taxes);
  const taxMo =
    annualTax != null && annualTax > 0 ? annualTax / 12 : null;
  const taxPart = taxMo ?? 0;
  const total = pi + taxPart + insurance + misc;
  return { pi, taxMo, insurance, misc, total };
}

function formatTaxMoCell(row) {
  const annualTax = toNumberOrNull(row.taxes);
  if (annualTax == null || annualTax <= 0) return "—";
  return formatMoney(annualTax / 12);
}

function formatCarryCells(row) {
  const c = computeCarryForRow(row);
  if (!c) {
    return { taxDisp: formatTaxMoCell(row), piDisp: "—", totalDisp: "—" };
  }
  return {
    taxDisp: formatTaxMoCell(row),
    piDisp: formatMoney(c.pi),
    totalDisp: formatMoney(c.total),
  };
}

function applyMortgagePresetToForm() {
  const product = document.getElementById("fin_product").value;
  const preset = MORTGAGE_PRESETS[product];
  const rateEl = document.getElementById("fin_rate");
  const termEl = document.getElementById("fin_term_years");
  const hintEl = document.getElementById("fin_preset_hint");
  rateEl.value = String(preset.defaultAprPercent);
  if (preset.months != null) {
    termEl.value = String(preset.months / 12);
    termEl.disabled = true;
  } else {
    termEl.disabled = false;
  }
  hintEl.textContent =
    product === "custom"
      ? "Enter any term and APR you want to model."
      : `Preset APR ${preset.defaultAprPercent}% is illustrative only—replace with your lender’s quote. Product: ${preset.label}.`;
}

function getSearchParams() {
  const params = new URLSearchParams();
  const zipRaw = document.getElementById("zip_code").value.trim();
  if (zipRaw) {
    const z = normalizeUsZip5(zipRaw);
    if (z) params.set("zip_code", z);
  }
  const fields = ["town", "min_price", "max_price", "min_beds", "max_beds"];
  for (const id of fields) {
    const raw = document.getElementById(id).value.trim();
    if (!raw) continue;
    params.set(id, raw);
  }
  params.set("limit", "500");
  return params;
}

function renderListings(rows) {
  resultsBody.innerHTML = "";
  // update listing dropdown for "Check a specific home"
  const select = document.getElementById("listing_select");
  if (select) {
    const current = select.value;
    select.innerHTML =
      '<option value="">Run a search above, then pick a home…</option>';
    lastListingRowsById = new Map();
    for (const row of rows) {
      if (!row.mls_id) continue;
      lastListingRowsById.set(String(row.mls_id), row);
      const option = document.createElement("option");
      const addr = row.full_address ?? row.address ?? "(no address)";
      option.value = String(row.mls_id);
      option.textContent = `${addr} (${row.mls_id})`;
      select.appendChild(option);
    }
    // try to preserve previous selection if still present
    if (current && lastListingRowsById.has(current)) {
      select.value = current;
    }
  }

  if (!rows.length) {
    renderEmptyTableRow(
      resultsBody,
      12,
      "No homes match yet. Try this next: widen bedroom range, remove max price, or try a nearby ZIP/town.",
    );
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    const onMap = hasLatLon(row) ? "Yes" : "No";
    const addr = row.full_address ?? row.address ?? "";
    const { taxDisp, piDisp, totalDisp } = formatCarryCells(row);
    tr.innerHTML = `
      <td data-label="Listing ID">${escapeHtml(row.mls_id)}</td>
      <td data-label="Address">${escapeHtml(addr)}</td>
      <td data-label="Town">${escapeHtml(row.town)}</td>
      <td data-label="ZIP">${escapeHtml(row.zip_code)}</td>
      <td data-label="On map?">${onMap}</td>
      <td data-label="Beds">${escapeHtml(row.bedrooms)}</td>
      <td data-label="Baths">${escapeHtml(row.total_baths)}</td>
      <td data-label="Floorspace (sq ft)">${escapeHtml(row.square_feet)}</td>
      <td data-label="List Price">${escapeHtml(formatMoney(row.list_price))}</td>
      <td data-label="Monthly tax">${escapeHtml(taxDisp)}</td>
      <td data-label="Loan payment (P&I)">${escapeHtml(piDisp)}</td>
      <td data-label="Est. total monthly">${escapeHtml(totalDisp)}</td>
    `;
    resultsBody.appendChild(tr);
  }
}

function buildCarryPopupHtml(row) {
  const addr = escapeHtml(row.full_address ?? row.address ?? "Listing");
  const price = formatMoney(row.list_price);
  let html = `<strong>${addr}</strong><br/>List: ${price}`;
  const c = computeCarryForRow(row);
  if (!c) return html;
  const taxLine =
    c.taxMo == null ? "Tax/mo: — (no MLS tax)" : `Tax/mo: ${formatMoney(c.taxMo)}`;
  html += `<br/><hr style="margin:8px 0;border:none;border-top:1px solid #ccc"/>`;
  html += `<div style="font-size:13px;line-height:1.45">`;
  html += `P&amp;I: ${formatMoney(c.pi)}<br/>`;
  html += `${taxLine}<br/>`;
  html += `Insurance: ${formatMoney(c.insurance)} · Misc: ${formatMoney(c.misc)}<br/>`;
  html += `<strong>Est. carry/mo: ${formatMoney(c.total)}</strong>`;
  html += `</div>`;
  return html;
}

async function renderMarkers(rows) {
  await initMapBackend();
  clearMapMarkers();
  let count = 0;
  if (mapBackend.mode === "leaflet" && mapBackend.map && mapBackend.markerLayer) {
    for (const row of rows) {
      const lat = toNumberOrNull(row.latitude);
      const lon = toNumberOrNull(row.longitude);
      if (lat == null || lon == null) continue;
      count += 1;
      L.marker([lat, lon]).bindPopup(buildCarryPopupHtml(row)).addTo(mapBackend.markerLayer);
    }
    if (count > 0) {
      const b = mapBackend.markerLayer.getBounds();
      if (b.isValid()) {
        mapBackend.map.fitBounds(b, { padding: [20, 20] });
      }
    }
  } else if (mapBackend.mode === "mapbox" && mapBackend.map) {
    const bounds = new mapboxgl.LngLatBounds();
    for (const row of rows) {
      const lat = toNumberOrNull(row.latitude);
      const lon = toNumberOrNull(row.longitude);
      if (lat == null || lon == null) continue;
      count += 1;
      bounds.extend([lon, lat]);
      const popup = new mapboxgl.Popup({ offset: 24 }).setHTML(buildCarryPopupHtml(row));
      const marker = new mapboxgl.Marker().setLngLat([lon, lat]).setPopup(popup).addTo(mapBackend.map);
      mapBackend.markers.push(marker);
    }
    if (count === 1) {
      const c = bounds.getCenter();
      mapBackend.map.jumpTo({ center: c, zoom: 13 });
    } else if (count > 1) {
      mapBackend.map.fitBounds(bounds, { padding: 50, maxZoom: 14, duration: 0 });
    }
  }
}

function countPins(rows) {
  return rows.filter(hasLatLon).length;
}

/**
 * Looks up map locations for listings missing coordinates (capped per search).
 * @param {(pct: number) => void} [onBarPct] — overall progress 40–95 while geocoding
 * @returns {{ stillMissing: number, skippedDueToLimit: number }}
 */
async function geocodeMissingPins(rows, onBarPct) {
  const ids = rows.filter((r) => !hasLatLon(r)).map((r) => r.mls_id);
  if (!ids.length) {
    return { stillMissing: 0, skippedDueToLimit: 0, geocodeFailed: false };
  }

  const skippedDueToLimit = Math.max(0, ids.length - MAX_AUTO_GEOCODE_LOOKUPS);
  const idsToDo = ids.slice(0, MAX_AUTO_GEOCODE_LOOKUPS);
  const batchSize = 8;
  const totalThisRun = idsToDo.length;

  if (skippedDueToLimit > 0) {
    statusEl.textContent =
      `Still loading… we'll place up to ${MAX_AUTO_GEOCODE_LOOKUPS} listings on the map this time ` +
      `(${skippedDueToLimit} skipped so the page stays quick—use a narrower search to look up more).`;
  }

  for (let i = 0; i < idsToDo.length; i += batchSize) {
    const batch = idsToDo.slice(i, i + batchSize);
    const progress = Math.min(i + batch.length, totalThisRun);
    if (onBarPct && totalThisRun > 0) {
      onBarPct(40 + (progress / totalThisRun) * 55);
    }
    statusEl.textContent =
      `Still loading… placing listings on the map (${progress} of ${totalThisRun}). ` +
      `We're looking up addresses online—this usually takes under a minute.`;
    try {
      const res = await fetch(apiUrl("/geocode/active-listings"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mls_ids: batch }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || `HTTP ${res.status}`);
      }
      const updates = await res.json();
      for (const u of updates) {
        const row = rows.find((r) => r.mls_id === u.mls_id);
        if (row) {
          row.latitude = u.latitude;
          row.longitude = u.longitude;
        }
      }
      await renderMarkers(rows);
    } catch (err) {
      hideLoadingBar();
      statusEl.textContent =
        `We couldn't finish loading the map (${err.message}). Try searching again, or use a smaller area.`;
      return {
        stillMissing: rows.filter((r) => !hasLatLon(r)).length,
        skippedDueToLimit,
        geocodeFailed: true,
      };
    }
  }

  if (onBarPct) {
    onBarPct(95);
  }
  return {
    stillMissing: rows.filter((r) => !hasLatLon(r)).length,
    skippedDueToLimit,
    geocodeFailed: false,
  };
}

async function loadCompsFromMainFilters() {
  const params = new URLSearchParams();
  const zipRaw = document.getElementById("zip_code").value.trim();
  if (zipRaw) {
    const z = normalizeUsZip5(zipRaw);
    if (z) params.set("zip_code", z);
  }

  if (!params.has("zip_code")) {
    renderEmptyTableRow(compBody, 6, "Enter a ZIP above, then click “Show homes and insights” to load rental benchmarks.");
    setFreshness("rent_freshness", "");
    setQualityChip("rent_quality_chip", "");
    return;
  }

  const minB = toNumberOrNull(document.getElementById("min_beds").value);
  const maxB = toNumberOrNull(document.getElementById("max_beds").value);
  if (minB != null) params.set("min_beds", String(minB));
  if (maxB != null) params.set("max_beds", String(maxB));

  try {
    setTableSkeleton("#rent_table_wrap", true);
    const res = await fetch(apiUrl(`/analytics/rent-by-zip-bedroom?${params.toString()}`));
    if (!res.ok) throw new Error("We couldn't load rental benchmarks right now.");
    const rows = await res.json();
    compBody.innerHTML = "";
    if (!rows.length) {
      renderEmptyTableRow(
        compBody,
        6,
        "No rental benchmarks found. Try this next: broaden bedroom filters or test a nearby ZIP.",
      );
      setFreshness("rent_freshness", formatFreshness());
      setQualityChip("rent_quality_chip", "No benchmark confidence yet", "neutral");
      return;
    }
    let maxSample = 0;
    for (const row of rows.slice(0, 200)) {
      maxSample = Math.max(maxSample, Number(row.sample_size || 0));
      const tr = document.createElement("tr");
      tr.innerHTML = `
      <td data-label="ZIP">${row.zip_code}</td>
      <td data-label="Beds">${row.bedrooms}</td>
      <td data-label="Typical rent (median)">${formatMoney(row.median_rent)}</td>
      <td data-label="Average rent">${formatMoney(row.avg_rent)}</td>
      <td data-label="Recent rentals">${row.sample_size ?? ""}</td>
      <td data-label="Confidence level">${formatConfidenceLabel(row.confidence ?? "")}</td>
    `;
      compBody.appendChild(tr);
    }
    const rentQ = qualityFromCount(maxSample, 40, 12);
    setQualityChip("rent_quality_chip", `${rentQ.label} (rental sample depth)`, rentQ.tone);
    setFreshness("rent_freshness", formatFreshness());
  } catch (err) {
    renderEmptyTableRow(
      compBody,
      6,
      "We couldn't load rental benchmarks right now. Please try again in a moment.",
    );
    setQualityChip("rent_quality_chip", "Rental confidence unavailable", "neutral");
  } finally {
    setTableSkeleton("#rent_table_wrap", false);
  }
}

async function loadAreaStatsFromMainFilters() {
  const noteEl = document.getElementById("area_note");
  const priceMainEl = document.getElementById("area_price_main");
  const priceRangeEl = document.getElementById("area_price_range");
  const ppsfEl = document.getElementById("area_ppsf");
  const volEl = document.getElementById("area_volume");
  const trendSummaryEl = document.getElementById("area_trend_summary");
  const activeSummaryEl = document.getElementById("area_active_summary");
  const activeNoteEl = document.getElementById("area_active_note");

  const params = new URLSearchParams();
  const zipRaw = document.getElementById("zip_code").value.trim();
  const townRaw = document.getElementById("town").value.trim();
  if (zipRaw) {
    const z = normalizeUsZip5(zipRaw);
    if (z) params.set("zip_code", z);
  }
  if (townRaw) {
    params.set("town", townRaw);
  }
  const minB = toNumberOrNull(document.getElementById("min_beds").value);
  const maxB = toNumberOrNull(document.getElementById("max_beds").value);
  if (minB != null) params.set("min_beds", String(minB));
  if (maxB != null) params.set("max_beds", String(maxB));

  if (!params.has("zip_code") && !params.has("town")) {
    noteEl.textContent =
      "Enter a ZIP (and optionally town and bedrooms) above, then click “Show homes and insights”.";
    priceMainEl.textContent = "";
    priceRangeEl.textContent = "";
    ppsfEl.textContent = "";
    volEl.textContent = "";
    trendSummaryEl.textContent = "";
    activeSummaryEl.textContent = "";
    activeNoteEl.textContent = "";
    setFreshness("area_freshness", "");
    setQualityChip("area_price_confidence", "");
    setQualityChip("area_trend_confidence", "");
    renderTrendSparkline([]);
    return;
  }

  try {
    setSkeletonState(AREA_METRIC_IDS, true);
    async function fetchAreaStats(localParams) {
      const res = await fetch(apiUrl(`/sold-area-stats?${localParams.toString()}`));
      if (!res.ok) throw new Error(`Area stats failed (${res.status})`);
      return await res.json();
    }

    let data = await fetchAreaStats(params);
    let summary = data.summary;
    let trend = Array.isArray(data.trend_by_month) ? data.trend_by_month : [];
    let active = data.current_active_snapshot;
    let fallbackNote = "";

    if (data.error) {
      noteEl.textContent = `We couldn't load sold comps yet: ${data.error}`;
      priceMainEl.textContent = "";
      priceRangeEl.textContent = "";
      ppsfEl.textContent = "";
      volEl.textContent = "";
      trendSummaryEl.textContent = "";
      activeSummaryEl.textContent = "";
      activeNoteEl.textContent = "";
      setQualityChip("area_price_confidence", "Area confidence unavailable", "neutral");
      setQualityChip("area_trend_confidence", "");
      renderTrendSparkline([]);
      return;
    }

    if ((!summary || !summary.num_sales) && !params.has("months_back")) {
      const expanded = new URLSearchParams(params);
      expanded.set("months_back", "24");
      const expandedData = await fetchAreaStats(expanded);
      if (!expandedData.error && expandedData.summary && expandedData.summary.num_sales) {
        data = expandedData;
        summary = data.summary;
        trend = Array.isArray(data.trend_by_month) ? data.trend_by_month : [];
        active = data.current_active_snapshot;
        fallbackNote =
          "There were no matching sold comps in the last 12 months, so we expanded to the last 24 months for context.";
      }
    }

    if (!summary || !summary.num_sales) {
      noteEl.textContent =
        "We didn’t find enough recent sales that match these filters here. Try broadening the search (for example, fewer bedroom filters or only ZIP).";
      priceMainEl.textContent = "";
      priceRangeEl.textContent = "";
      ppsfEl.textContent = "";
      volEl.textContent = "";
      trendSummaryEl.textContent = "";
      activeSummaryEl.textContent = "";
      activeNoteEl.textContent = "";
      setFreshness("area_freshness", formatFreshness());
      setQualityChip("area_price_confidence", "Low confidence (not enough similar sales)", "low");
      setQualityChip("area_trend_confidence", "");
      renderTrendSparkline([]);
      return;
    }

    noteEl.textContent =
      "Based on roughly the last year of similar sales in this area. Individual homes can be above or below these ranges depending on condition, location, and features.";
    if (fallbackNote) {
      noteEl.textContent = `${noteEl.textContent} ${fallbackNote}`;
    }

    const pMed = summary.price_median;
    const p25 = summary.price_p25;
    const p75 = summary.price_p75;
    priceMainEl.textContent = pMed != null ? formatMoney(pMed) : "";
    if (p25 != null && p75 != null) {
      priceRangeEl.textContent = `About half of similar homes in this area sold between ${formatMoney(
        p25,
      )} and ${formatMoney(p75)}.`;
    } else {
      priceRangeEl.textContent = "";
    }

    ppsfEl.textContent =
      summary.price_sqft_median != null
        ? `${formatMoney(summary.price_sqft_median)} per sq ft`
        : "Not enough size data to show yet.";

    const numSales = summary.num_sales;
    volEl.textContent = `About ${numSales} home${numSales === 1 ? "" : "s"} like this sold in the past year here.`;
    const salesQ = qualityFromCount(numSales, 35, 12);
    setQualityChip("area_price_confidence", `${salesQ.label} (${numSales} similar sales)`, salesQ.tone);

    if (trend.length >= 2) {
      const first = trend[0];
      const last = trend[trend.length - 1];
      if (first.median_price != null && last.median_price != null && first.median_price > 0) {
        const changePct = ((last.median_price / first.median_price - 1) * 100).toFixed(1);
        const dir =
          Math.abs(Number(changePct)) < 1
            ? "have been mostly flat"
            : Number(changePct) > 0
            ? "have gone up"
            : "have gone down";
        trendSummaryEl.textContent = `From ${first.month} to ${last.month}, prices here ${dir} about ${Math.abs(
          Number(changePct),
        )}%. This is based on months with enough recorded sales.`;
      } else {
        trendSummaryEl.textContent = "";
      }
      const trendQ = qualityFromCount(
        trend.reduce((acc, cur) => acc + Number(cur.num_sales || 0), 0),
        120,
        45,
      );
      setQualityChip("area_trend_confidence", `${trendQ.label} (trend reliability)`, trendQ.tone);
    } else {
      trendSummaryEl.textContent = "";
      setQualityChip("area_trend_confidence", "Trend confidence unavailable", "neutral");
    }
    renderTrendSparkline(trend);
    setFreshness("area_freshness", formatFreshness());

    if (active && active.num_active) {
      activeSummaryEl.textContent = `${active.num_active} active listing${
        active.num_active === 1 ? "" : "s"
      } match these filters.`;
      if (active.active_price_median != null && summary.price_median != null) {
        const diff = active.active_vs_sold_pct ?? 0;
        const aboveBelow =
          Math.abs(diff) < 1 ? "about the same as" : diff > 0 ? "above" : "below";
        activeNoteEl.textContent = `Their asking prices are ${aboveBelow} recent sale prices for similar homes (about ${Math.abs(
          diff.toFixed(1),
        )}% ${diff > 0 ? "higher" : "lower"} than the typical recent sale).`;
      } else {
        activeNoteEl.textContent =
          "We couldn’t compare asking prices to recent sales here, but you can still use the listing table and map below.";
      }
    } else {
      activeSummaryEl.textContent = "No active listings currently match these filters.";
      activeNoteEl.textContent = "";
    }
  } catch (err) {
    noteEl.textContent =
      "We couldn't load area snapshot data right now. Please try again in a moment.";
    priceMainEl.textContent = "";
    priceRangeEl.textContent = "";
    ppsfEl.textContent = "";
    volEl.textContent = "";
    trendSummaryEl.textContent = "";
    activeSummaryEl.textContent = "";
    activeNoteEl.textContent = "";
    setQualityChip("area_price_confidence", "Area confidence unavailable", "neutral");
    setQualityChip("area_trend_confidence", "");
    renderTrendSparkline([]);
  } finally {
    setSkeletonState(AREA_METRIC_IDS, false);
  }
}

async function refreshListingDisplays() {
  if (lastListingRows) {
    renderListings(lastListingRows);
    await renderMarkers(lastListingRows);
  }
}

async function searchListings() {
  const params = getSearchParams();
  if (!hasAreaScope(params)) {
    statusEl.textContent =
      "Add at least a ZIP code or town, then click “Show homes and insights” so we can keep results focused.";
    await loadAreaStatsFromMainFilters();
    renderEmptyTableRow(
      resultsBody,
      12,
      "Add a ZIP code or town above to start your search. Next step: try ZIP first, then add beds/price.",
    );
    renderEmptyTableRow(
      compBody,
      6,
      "Add a ZIP code above to load rental benchmarks. Next step: start with one ZIP, then refine bedrooms.",
    );
    clearMapMarkers();
    lastListingRows = [];
    setFreshness("listings_freshness", "");
    return;
  }

  try {
    showLoadingBarIndeterminate();
    statusEl.textContent = "Loading… fetching area stats and listings.";
    if (searchBtn) searchBtn.disabled = true;
    setTableSkeleton("#results_table_wrap", true);
    setTableSkeleton("#rent_table_wrap", true);

    // Load area stats first so we can talk about “what’s normal” for this area.
    await loadAreaStatsFromMainFilters();

    const res = await fetch(apiUrl(`/active-listings?${params.toString()}`));
    if (!res.ok) throw new Error(`Failed to load listings (${res.status})`);
    const rows = await res.json();
    setLoadingBarPercent(22);
    lastListingRows = rows;
    renderListings(rows);
    await renderMarkers(rows);
    statusEl.textContent = `Loaded ${rows.length} listings (${countPins(rows)} on map).`;
    setFreshness("listings_freshness", formatFreshness());

    setLoadingBarPercent(34);
    await loadCompsFromMainFilters();

    const missingCount = rows.filter((r) => !hasLatLon(r)).length;
    if (missingCount > 0) {
      setLoadingBarPercent(40);
      const geo = await geocodeMissingPins(rows, setLoadingBarPercent);
      renderListings(rows);

      let msg = `Done. Showing ${rows.length} listings; ${countPins(rows)} appear on the map.`;
      if (geo.skippedDueToLimit > 0) {
        msg +=
          ` To keep things fast, we only looked up the first ${MAX_AUTO_GEOCODE_LOOKUPS} addresses that were missing a map location. ` +
          `${geo.skippedDueToLimit} others were skipped—try a narrower search (for example add town, price range, or beds) and search again to load more pins.`;
      }
      if (geo.stillMissing > 0) {
        msg += ` ${geo.stillMissing} listing(s) still have no pin (address not found, or not looked up yet).`;
      }
      statusEl.textContent = msg;
      if (!geo.geocodeFailed) {
        await finishLoadingBar();
      }
    } else {
      let msg = `Done. Showing ${rows.length} listings; ${countPins(rows)} appear on the map.`;
      statusEl.textContent = msg;
      setLoadingBarPercent(100);
      await finishLoadingBar();
    }
  } catch (err) {
    hideLoadingBar();
    const msg = err && err.message ? String(err.message) : "";
    const net =
      /load failed|failed to fetch|networkerror|cannot connect/i.test(msg) ||
      (typeof TypeError !== "undefined" && err instanceof TypeError);
    statusEl.textContent = net
      ? "We could not reach the API from this page. Open the buyer tool from the same address as the server (for example your tunnel to port 8000), or set data-api-base on the page to your API URL."
      : "We couldn't load homes right now. Please try again in a moment.";
  } finally {
    if (searchBtn) searchBtn.disabled = false;
    setTableSkeleton("#results_table_wrap", false);
    setTableSkeleton("#rent_table_wrap", false);
  }
}

async function analyzeSelectedListing() {
  const select = document.getElementById("listing_select");
  const mlsId = select.value;
  const headlineEl = document.getElementById("listing_headline");
  const subEl = document.getElementById("listing_subheadline");
  const priceVsEl = document.getElementById("listing_price_vs_area");
  const priceBandEl = document.getElementById("listing_price_band");
  const ppsfEl = document.getElementById("listing_ppsf");
  const ppsfNoteEl = document.getElementById("listing_ppsf_note");
  const payEl = document.getElementById("listing_payment");
  const payNoteEl = document.getElementById("listing_payment_note");
  const compsBody = document.getElementById("listing_comps_body");
  const compsNoteEl = document.getElementById("listing_comps_note");

  if (!mlsId) {
    headlineEl.textContent = "";
    subEl.textContent =
      "Choose a home from your latest search above to see how its price compares to recent nearby sales, plus a rough monthly payment.";
    priceVsEl.textContent = "";
    priceBandEl.textContent = "";
    ppsfEl.textContent = "";
    ppsfNoteEl.textContent = "";
    payEl.textContent = "";
    payNoteEl.textContent = "";
    renderEmptyTableRow(
      compsBody,
      6,
      "Pick a home above, then click “Analyze this home” to load comparable recent sales.",
    );
    if (compsNoteEl) compsNoteEl.textContent = "";
    setFreshness("comps_freshness", "");
    setQualityChip("listing_comp_confidence", "");
    clearListingTakeaways();
    return;
  }

  const row = lastListingRowsById.get(mlsId);
  const addr = row ? row.full_address ?? row.address ?? "" : "";
  headlineEl.textContent = addr ? "How does this home compare?" : "How does this home compare?";
  subEl.textContent =
    "We’ll look at roughly the last year of similar sales nearby to see what’s typical, then show a rough monthly payment using the financing settings above.";
  if (compsNoteEl) compsNoteEl.textContent = "";
  clearListingTakeaways();

  try {
    setSkeletonState(LISTING_METRIC_IDS, true);
    setTableSkeleton("#listing_comps_wrap", true);
    if (analyzeBtn) {
      analyzeBtn.disabled = true;
      analyzeBtn.textContent = "Analyzing…";
    }
    async function fetchListingComps(monthsBack = 12) {
      const res = await fetch(
        apiUrl(`/sold-comps?mls_id=${encodeURIComponent(mlsId)}&months_back=${monthsBack}`),
      );
      if (!res.ok) throw new Error("We couldn't load similar recent sales right now.");
      return await res.json();
    }

    let data = await fetchListingComps(12);
    let expandedWindowUsed = false;
    if (!data.error) {
      const baseSummary = data.summary || {};
      if (!baseSummary.num_comps) {
        const expandedData = await fetchListingComps(24);
        const expandedSummary = (expandedData || {}).summary || {};
        if (!expandedData.error && expandedSummary.num_comps) {
          data = expandedData;
          expandedWindowUsed = true;
        }
      }
    }

    if (data.error) {
      priceVsEl.textContent = "";
      priceBandEl.textContent = "";
      ppsfEl.textContent = "";
      ppsfNoteEl.textContent = "";
      payEl.textContent = "";
      payNoteEl.textContent = "We couldn't analyze this home yet. Please try another listing.";
      renderEmptyTableRow(compsBody, 6, "No comparable sales available for this listing.");
      if (compsNoteEl) compsNoteEl.textContent = "";
      setQualityChip("listing_comp_confidence", "Comp confidence unavailable", "neutral");
      return;
    }

    const subject = data.subject || {};
    const summary = data.summary || {};
    const comps = Array.isArray(data.comps) ? data.comps : [];

    if (!summary.num_comps) {
      priceVsEl.textContent = "Not enough similar recent sales to compare.";
      priceBandEl.textContent =
        "We couldn’t find a good set of nearby sales that match this home’s size and bedroom count. Try checking a different area or using the filters above to broaden the search.";
      ppsfEl.textContent = "";
      ppsfNoteEl.textContent = "";
      payEl.textContent = "";
      payNoteEl.textContent = "";
      renderEmptyTableRow(
        compsBody,
        6,
        "No strong comparable sales were found. Try a nearby listing or a broader area search.",
      );
      if (compsNoteEl) compsNoteEl.textContent = "";
      setQualityChip("listing_comp_confidence", "Limited confidence (few matching comps)", "low");
      return;
    }

    const med = summary.median_price;
    const p25 = summary.price_p25;
    const p75 = summary.price_p75;
    const listPrice = subject.list_price;
    const diffPct = summary.list_vs_median_pct;

    if (med != null && listPrice != null) {
      const dir =
        diffPct == null || Math.abs(diffPct) < 1
          ? "right around what similar homes have been selling for"
          : diffPct > 0
          ? "a bit above what similar homes have been selling for"
          : "a bit below what similar homes have been selling for";
      const pctText =
        diffPct == null || Math.abs(diffPct) < 1
          ? ""
          : ` (about ${Math.abs(diffPct).toFixed(1)}% ${
              diffPct > 0 ? "higher" : "lower"
            } than the typical recent sale)`;
      priceVsEl.textContent = `This asking price is ${dir}${pctText}.`;
    } else {
      priceVsEl.textContent = "";
    }

    if (p25 != null && p75 != null) {
      priceBandEl.textContent = `Recently, about half of similar homes nearby sold between ${formatMoney(
        p25,
      )} and ${formatMoney(p75)} in the last year or so.`;
    } else {
      priceBandEl.textContent = "";
    }

    if (summary.median_ppsf != null && listPrice != null && subject.square_feet) {
      const subjPpsf = listPrice / subject.square_feet;
      ppsfEl.textContent = `${formatMoney(subjPpsf)} per sq ft (this home)`;
      ppsfNoteEl.textContent = `Similar recent sales had a typical (median) value near ${formatMoney(
        summary.median_ppsf,
      )} per sq ft.`;
    } else {
      ppsfEl.textContent = "";
      ppsfNoteEl.textContent =
        "Price-per-square-foot isn’t shown because we’re missing size data for this home or most comps.";
    }

    // Monthly payment estimate for this home using current financing settings.
    const carry = row ? computeCarryForRow(row) : null;
    if (carry) {
      payEl.textContent = formatMoney(carry.total);
      const parts = [`Loan payment (principal & interest): ${formatMoney(carry.pi)}`];
      if (carry.taxMo != null) parts.push(`Estimated property tax: ${formatMoney(carry.taxMo)}/mo`);
      if (carry.insurance) parts.push(`Insurance: ${formatMoney(carry.insurance)}/mo`);
      if (carry.misc) parts.push(`Misc: ${formatMoney(carry.misc)}/mo`);
      payNoteEl.textContent =
        parts.join(" · ") +
        ". This is a rough planning number, not a quote—your lender, taxes, and insurance can change it a lot.";
    } else {
      payEl.textContent = "";
      payNoteEl.textContent =
        "We couldn’t compute a payment estimate for this home (missing list price).";
    }

    // Render comps table.
    compsBody.innerHTML = "";
    const fullSetCount = toNumberOrNull(summary.total_comps_considered);
    if (compsNoteEl && fullSetCount != null && fullSetCount > 0) {
      compsNoteEl.textContent = `These summary numbers use ${fullSetCount} matching sales. The table shows up to ${
        comps.length
      } closest matches for quick review.`;
    } else if (compsNoteEl && comps.length) {
      compsNoteEl.textContent = `Showing ${comps.length} closest matching sales.`;
    }
    if (expandedWindowUsed && compsNoteEl) {
      compsNoteEl.textContent = `${compsNoteEl.textContent} We expanded the sold-comp lookback from 12 to 24 months because recent matches were limited.`;
    }
    const compQ = qualityFromCount(fullSetCount ?? summary.num_comps, 35, 12);
    setQualityChip(
      "listing_comp_confidence",
      `${compQ.label} (${fullSetCount ?? summary.num_comps} matching sales)`,
      compQ.tone,
    );
    setFreshness("comps_freshness", formatFreshness());
    renderListingTakeaways(summary, subject, carry);
    for (const c of comps) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td data-label="Address">${escapeHtml(c.full_address ?? "")}</td>
        <td data-label="Sold price">${formatMoney(c.sale_price)}</td>
        <td data-label="Beds">${escapeHtml(c.bedrooms ?? "")}</td>
        <td data-label="Baths">${escapeHtml(c.total_baths ?? "")}</td>
        <td data-label="Sq ft">${escapeHtml(c.square_feet ?? "")}</td>
        <td data-label="Sale date">${escapeHtml(formatDateShort(c.settled_date))}</td>
      `;
      compsBody.appendChild(tr);
    }
    if (!comps.length) {
      renderEmptyTableRow(compsBody, 6, "No comparable sales are available to display.");
    }
  } catch (err) {
    priceVsEl.textContent = "";
    priceBandEl.textContent = "";
    ppsfEl.textContent = "";
    ppsfNoteEl.textContent = "";
    payEl.textContent = "";
    payNoteEl.textContent = "We couldn't load this analysis right now. Please try again in a moment.";
    renderEmptyTableRow(compsBody, 6, "Comparable sales are temporarily unavailable.");
    if (compsNoteEl) compsNoteEl.textContent = "";
    setQualityChip("listing_comp_confidence", "Comp confidence unavailable", "neutral");
    clearListingTakeaways();
  } finally {
    setSkeletonState(LISTING_METRIC_IDS, false);
    setTableSkeleton("#listing_comps_wrap", false);
    if (analyzeBtn) {
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = "Analyze this home";
    }
  }
}

function clearFilters() {
  for (const id of ["zip_code", "town", "min_price", "max_price", "min_beds", "max_beds"]) {
    document.getElementById(id).value = "";
  }
}

document.getElementById("searchBtn").addEventListener("click", searchListings);
document.getElementById("clearBtn").addEventListener("click", () => {
  clearFilters();
  clearMapMarkers();
  lastListingRows = [];
  renderEmptyTableRow(resultsBody, 12, "Filters cleared. Add a ZIP code or town above to run a new search.");
  renderEmptyTableRow(compBody, 6, "Add a ZIP code above to load rental benchmarks.");
  statusEl.textContent = "Filters cleared. Start with a ZIP code or town, then click “Show homes and insights”.";
  setFreshness("listings_freshness", "");
  setFreshness("area_freshness", "");
  setFreshness("rent_freshness", "");
  setFreshness("comps_freshness", "");
  setQualityChip("area_price_confidence", "");
  setQualityChip("area_trend_confidence", "");
  setQualityChip("rent_quality_chip", "");
  setQualityChip("listing_comp_confidence", "");
  renderTrendSparkline([]);
  clearListingTakeaways();
  loadAreaStatsFromMainFilters();
});

if (analyzeBtn) {
  analyzeBtn.addEventListener("click", analyzeSelectedListing);
}
if (listingCompsToggle) {
  listingCompsToggle.addEventListener("toggle", () => {
    listingCompsToggle.dataset.userTouched = "1";
  });
}
window.addEventListener("resize", syncListingCompsToggleForViewport);

document.getElementById("fin_product").addEventListener("change", () => {
  applyMortgagePresetToForm();
  void refreshListingDisplays();
});

for (const id of ["fin_down_pct", "fin_rate", "fin_term_years", "fin_insurance", "fin_misc"]) {
  document.getElementById(id).addEventListener("input", () => void refreshListingDisplays());
}

initMapBackend()
  .catch((err) => console.warn("Map init:", err))
  .finally(() => {
    applyMortgagePresetToForm();
    loadCompsFromMainFilters();
    syncListingCompsToggleForViewport();
    statusEl.textContent = "Set your area filters, then click “Show homes and insights”.";
  });
