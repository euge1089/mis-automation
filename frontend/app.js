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
const resultsPreviewBody = document.getElementById("resultsPreviewBody");
const compBody = document.querySelector("#compTable tbody");
const searchBtn = document.getElementById("searchBtn");
const analyzeBtn = document.getElementById("analyzeListingBtn");
const fullListingsSection = document.getElementById("fullListingsSection");
const toggleFullListingsBtn = document.getElementById("toggleFullListings");
const listingCompsExpandBtn = document.getElementById("listing_comps_expand");
const compsLookbackEl = document.getElementById("comps_lookback");
const resultsFlowEl = document.getElementById("resultsFlow");
const preSearchOnboardingEl = document.getElementById("preSearchOnboarding");
const listingSelectionHintEl = document.getElementById("listingSelectionHint");
const listingAnalysisDetailsEl = document.getElementById("listingAnalysisDetails");
const panelCompsEl = document.getElementById("panelComps");
const listingLimitationsBoxEl = document.getElementById("listing_limitations_box");
const listingLimitationsTextEl = document.getElementById("listing_limitations_text");
const listingInsightsSectionEl = document.getElementById("listingInsights");
const listingInsightsLeadEl = document.getElementById("listingInsightsLead");
const financingPlaceholderEl = document.getElementById("financingPlaceholder");
const financingBodyEl = document.getElementById("financingBody");
const rentLookbackEl = document.getElementById("rent_lookback");

/** Area median sold price from last /sold-area-stats (for listing preview badges). */
let lastAreaSummary = null;

/** True after user runs a successful area search (ZIP/town). */
let hasCompletedAreaSearch = false;

const PREVIEW_ROWS = 8;
const COMP_PREVIEW_ROWS = 6;

function applyFlowDom(showResults) {
  if (resultsFlowEl) resultsFlowEl.hidden = !showResults;
  if (preSearchOnboardingEl) preSearchOnboardingEl.hidden = showResults;
}

function revealResultsAfterSearch() {
  hasCompletedAreaSearch = true;
  applyFlowDom(true);
  scheduleMapResize();
}

function hideResultsFlow() {
  hasCompletedAreaSearch = false;
  applyFlowDom(false);
}

function scheduleMapResize() {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      try {
        if (mapBackend.mode === "mapbox" && mapBackend.map) mapBackend.map.resize();
        if (mapBackend.mode === "leaflet" && mapBackend.map) mapBackend.map.invalidateSize();
      } catch (_) {
        /* ignore */
      }
    });
  });
}

function scrollListingDealIntoView() {
  const el = listingInsightsSectionEl || document.getElementById("listingInsights");
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function syncPreviewRowHighlight() {
  const sel = document.getElementById("listing_select");
  const id = sel && sel.value;
  if (!resultsPreviewBody) return;
  for (const tr of resultsPreviewBody.querySelectorAll("tr.preview-listing-row")) {
    const rid = tr.getAttribute("data-mls-id");
    tr.classList.toggle("preview-listing-row--selected", Boolean(id && rid === id));
  }
}

function selectListingByMlsId(mlsId, options = {}) {
  const { scroll = false } = options;
  const id = String(mlsId || "").trim();
  if (!id || !lastListingRowsById.has(id)) return;
  const sel = document.getElementById("listing_select");
  if (!sel) return;
  sel.value = id;
  updateListingSelectionVisibility();
  updateCarryPanel();
  syncPreviewRowHighlight();
  if (scroll) scrollListingDealIntoView();
}

function updateListingSelectionVisibility() {
  const sel = document.getElementById("listing_select");
  const id = sel && sel.value;
  if (!listingSelectionHintEl || !listingAnalysisDetailsEl) return;
  if (id) {
    listingSelectionHintEl.hidden = true;
    listingAnalysisDetailsEl.hidden = false;
    const row = lastListingRowsById.get(id);
    if (row) populatePropertyCard(row);
  } else {
    listingSelectionHintEl.hidden = false;
    listingAnalysisDetailsEl.hidden = true;
  }
  const compact = !id;
  if (listingInsightsSectionEl) listingInsightsSectionEl.classList.toggle("listing-insights--compact", compact);
  if (listingInsightsLeadEl) listingInsightsLeadEl.hidden = compact;
  if (financingPlaceholderEl) financingPlaceholderEl.hidden = Boolean(id);
  if (financingBodyEl) financingBodyEl.hidden = !id;
}

function showListingLimitationsPlain(summary, fullSetCount) {
  if (!listingLimitationsBoxEl || !listingLimitationsTextEl) return;
  const n = Number(fullSetCount ?? summary?.total_comps_considered ?? summary?.num_comps ?? 0);
  let text =
    "This comparison uses recent closed sales matched by ZIP, bedrooms, and size—not distance from the home. ";
  if (n >= 35) {
    text += "The sample size here is relatively strong for a rough guide.";
  } else if (n >= 12) {
    text += "Sample size is moderate; treat ranges as directional.";
  } else if (n > 0) {
    text += "Fewer comparable sales means less statistical reliability.";
  }
  listingLimitationsTextEl.textContent = text.trim();
  listingLimitationsBoxEl.hidden = false;
}

function hideListingLimitations() {
  if (listingLimitationsBoxEl) listingLimitationsBoxEl.hidden = true;
  if (listingLimitationsTextEl) listingLimitationsTextEl.textContent = "";
  setQualityChip("listing_comp_confidence", "");
}

function clampCompsLookbackMonths(raw) {
  const n = Number(raw);
  if ([6, 12, 24, 36].includes(n)) return n;
  return 12;
}

function clampRentLookbackMonths(raw) {
  const n = Number(raw);
  if ([6, 12, 24].includes(n)) return n;
  return 12;
}

function clearListingCompsPeriodCopy() {
  const sampleEl = document.getElementById("listing_comps_sample_line");
  const sparseLine = document.getElementById("listing_comps_sparse_line");
  const expandRow = document.getElementById("listing_comps_expand_row");
  if (sampleEl) sampleEl.textContent = "";
  if (sparseLine) {
    sparseLine.hidden = true;
    sparseLine.textContent = "";
  }
  if (expandRow) expandRow.hidden = true;
}

/**
 * @param {number} numComps
 * @param {number} lookbackMonths
 */
function updateListingCompsPeriodCopy(numComps, lookbackMonths) {
  const sampleEl = document.getElementById("listing_comps_sample_line");
  const sparseLine = document.getElementById("listing_comps_sparse_line");
  const expandRow = document.getElementById("listing_comps_expand_row");
  const expandBtn = document.getElementById("listing_comps_expand_lookback_btn");
  const y = clampCompsLookbackMonths(lookbackMonths);
  const n = Math.max(0, Number(numComps || 0));
  if (sampleEl) {
    sampleEl.textContent =
      n > 0 ? `Based on ${n} similar sales from the last ${y} months.` : "";
  }
  if (!sparseLine || !expandRow || !expandBtn) return;
  const order = [6, 12, 24, 36];
  const idx = order.indexOf(y);
  const nextW = idx >= 0 && idx < order.length - 1 ? order[idx + 1] : null;
  if (n < 3) {
    sparseLine.hidden = false;
    sparseLine.textContent = `Only ${n} comparable sales found in the last ${y} months. Try a longer period for more context.`;
    if (nextW != null && nextW > y) {
      expandRow.hidden = false;
      expandBtn.textContent = `Expand to ${nextW} months`;
      expandBtn.onclick = () => {
        if (compsLookbackEl) compsLookbackEl.value = String(nextW);
        void analyzeSelectedListing();
      };
    } else {
      expandRow.hidden = true;
    }
  } else {
    sparseLine.hidden = true;
    sparseLine.textContent = "";
    expandRow.hidden = true;
  }
}

/** Listing-based PPSF + monthly carry — does not depend on comparable sales. */
function fillListingPpsfAndPaymentFromRow(row, compSummary) {
  const ppsfEl = document.getElementById("listing_ppsf");
  const ppsfNoteEl = document.getElementById("listing_ppsf_note");
  const payEl = document.getElementById("listing_payment");
  const payNoteEl = document.getElementById("listing_payment_note");
  if (!ppsfEl || !ppsfNoteEl || !payEl || !payNoteEl) return;

  const lp = row ? toNumberOrNull(row.list_price) : null;
  const sqft = row ? toNumberOrNull(row.square_feet) : null;

  if (lp != null && sqft != null && sqft > 0) {
    const subjPpsf = lp / sqft;
    ppsfEl.textContent = `${formatMoney(subjPpsf)} / sq ft`;
    const medPpsf = compSummary && toNumberOrNull(compSummary.median_ppsf);
    const poolN = compSummary ? Number(compSummary.total_comps_considered ?? compSummary.num_comps ?? 0) : 0;
    if (medPpsf != null && poolN > 0) {
      ppsfNoteEl.textContent = `Median among comparable sales was about ${formatMoney(medPpsf)} / sq ft.`;
      const bpsf = badgePpsf(subjPpsf, medPpsf, poolN);
      setInsightBadge("listing_badge_ppsf", bpsf.text, bpsf.variant);
    } else {
      ppsfNoteEl.textContent = "Based on this home’s list price and square footage.";
      setInsightBadge("listing_badge_ppsf", "", null);
    }
  } else {
    ppsfEl.textContent = "—";
    ppsfNoteEl.textContent =
      !row || sqft == null || sqft <= 0
        ? "Square footage isn’t available to calculate price per sq ft from the listing."
        : "";
    setInsightBadge("listing_badge_ppsf", "", null);
  }

  const carry = row ? computeCarryForRow(row) : null;
  if (carry) {
    payEl.textContent = formatMoney(carry.total);
    const parts = [`P&I ${formatMoney(carry.pi)}`];
    if (carry.taxMo != null) parts.push(`tax ${formatMoney(carry.taxMo)}/mo`);
    if (carry.insurance) parts.push(`insurance ${formatMoney(carry.insurance)}/mo`);
    if (carry.misc) parts.push(`HOA/other ${formatMoney(carry.misc)}/mo`);
    let note = `${parts.join(" · ")}. Illustrative—not a lender quote.`;
    if (carry.taxMo == null) {
      note = "Property tax not available; estimate may be incomplete. " + note;
    }
    payNoteEl.textContent = note;
    setInsightBadge("listing_badge_payment", "Rough estimate", "neutral");
  } else {
    payEl.textContent = "";
    payNoteEl.textContent =
      lp == null || lp <= 0 ? "We couldn’t compute a payment (missing list price)." : "";
    setInsightBadge("listing_badge_payment", "", null);
  }
}

function setListingCompsUnavailablePriceCards(kind) {
  const priceVsEl = document.getElementById("listing_price_vs_area");
  const priceBandEl = document.getElementById("listing_price_band");
  if (!priceVsEl || !priceBandEl) return;
  setInsightBadge("listing_badge_price", "", null);
  if (kind === "empty_pool") {
    priceVsEl.textContent = "Comparable sales are limited for this home.";
    priceBandEl.textContent =
      "Try another home or widen the search area. We can still estimate monthly cost from the list price.";
  } else if (kind === "sold_data") {
    priceVsEl.textContent = "Recent sale benchmarks are temporarily unavailable.";
    priceBandEl.textContent =
      "We can still review the listing and estimated monthly cost from the ask.";
  } else if (kind === "network") {
    priceVsEl.textContent = "Recent comparable sales didn’t load for this home.";
    priceBandEl.textContent =
      "We can still estimate monthly cost from the list price. Try again in a moment or pick another listing.";
  } else {
    priceVsEl.textContent = "Recent comparable sales didn’t load for this home.";
    priceBandEl.textContent =
      "We can still estimate monthly cost from the list price. Try another home or widen the search area.";
  }
}

function showListingLimitationsForListingOnlyAnalysis() {
  if (!listingLimitationsBoxEl || !listingLimitationsTextEl) return;
  listingLimitationsTextEl.textContent =
    "Recent comparable sales didn’t load for this home. We can still estimate monthly cost from the list price. Try another home or widen the search area.";
  listingLimitationsBoxEl.hidden = false;
}

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
  if (n >= high) return { tone: "good", label: "Stronger sample" };
  if (n >= medium) return { tone: "medium", label: "Moderate sample" };
  if (n > 0) return { tone: "low", label: "Limited sample" };
  return { tone: "neutral", label: "Not enough data yet" };
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
      <polyline points="${points.join(" ")}" fill="none" stroke="${trendUp ? "#059669" : "#b91c1c"}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
  `;
}

function renderListingTakeaways(summary, subject, carry) {
  const panel = document.getElementById("listing_takeaways");
  const list = document.getElementById("listing_takeaways_list");
  if (!panel || !list) return;
  const takeaways = [];
  const diffPct = toNumberOrNull(summary.list_vs_median_pct);
  const median = toNumberOrNull(summary.median_price);
  if (diffPct != null) {
    if (Math.abs(diffPct) < 1) {
      takeaways.push("This asking price is in line with typical nearby sale prices in this comp set.");
    } else {
      const dir = diffPct > 0 ? "above" : "below";
      takeaways.push(
        `This asking price is ${dir} typical nearby sale prices in this comp set (about ${Math.abs(diffPct).toFixed(1)}%).`,
      );
    }
  }
  if (median != null) {
    takeaways.push(`Typical nearby sold price for similar homes in this set is about ${formatMoney(median)}.`);
  }
  if (carry && carry.total) {
    takeaways.push(`Estimated monthly carrying cost is around ${formatMoney(carry.total)} before one-time closing costs (illustrative only).`);
  }

  const missingCompBenchmark =
    toNumberOrNull(summary && summary.median_price) == null &&
    toNumberOrNull(summary && summary.list_vs_median_pct) == null;
  if (missingCompBenchmark && carry && carry.total) {
    takeaways.push(
      "Comparable sale benchmarks weren’t available—use list price, size, and monthly cost as your guide.",
    );
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
    } catch {
      /* Prefer buyer-facing OSM fallback; avoid surfacing vendor/load errors in the console. */
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

function escapeRegExp(s) {
  return String(s || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Street / unit line for tables and cards—drops duplicated town + state + ZIP when those exist on the row. */
function formatListingStreetLine(row) {
  const raw = String(row.full_address || row.address || "").trim();
  if (!raw) return "";
  let s = raw.replace(/,\s*([A-Z]{2}),\s*\1(?=\s+\d)/g, ", $1");
  const town = String(row.town || "").trim();
  const zip =
    normalizeUsZip5(String(row.zip_code || "").trim()) || String(row.zip_code || "").trim();
  if (town && zip) {
    const tail = new RegExp(
      `,\\s*${escapeRegExp(town)}[^,]*,\\s*[A-Z]{2}\\s*${escapeRegExp(zip)}\\s*$`,
      "i",
    );
    const stripped = s.replace(tail, "").trim();
    if (stripped.length >= 3) return stripped.replace(/,\s*$/, "").trim();
  }
  return s;
}

function formatListingCityStateZip(row) {
  const town = String(row.town || "").trim();
  const st = String(row.state || "").trim();
  const zip =
    normalizeUsZip5(String(row.zip_code || "").trim()) || String(row.zip_code || "").trim();
  const right = [st, zip].filter(Boolean).join(" ").trim();
  if (town && right) return `${town}, ${right}`;
  return town || right || "";
}

function clientAreaStatsUnavailableNote() {
  return "Recent sale benchmarks are temporarily unavailable for this area. You can still browse active homes and estimate monthly payments.";
}

/** When ``active``, hide the four metric cards and show a single compact message instead. */
function setAreaSnapshotCompactMode(active, compactMessage = "") {
  const grid = document.getElementById("area_metric_grid");
  const compact = document.getElementById("area_snapshot_compact");
  const compactText = document.getElementById("area_snapshot_compact_text");
  const noteEl = document.getElementById("area_note");
  if (compactText && compactMessage) compactText.textContent = compactMessage;
  if (grid) grid.hidden = Boolean(active);
  if (compact) compact.hidden = !active;
  if (noteEl) noteEl.hidden = Boolean(active);
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

/** Parse min/max price fields — accepts plain digits or formatted currency. */
function parseSearchPriceValue(raw) {
  if (raw == null || String(raw).trim() === "") return null;
  const digits = String(raw).replace(/\D/g, "");
  if (!digits) return null;
  const n = Number(digits);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n);
}

function formatSearchPriceInput(el) {
  if (!el) return;
  const n = parseSearchPriceValue(el.value);
  el.value = n != null ? formatMoney(n) : "";
}

function normalizeSearchPriceInputForEdit(el) {
  if (!el) return;
  const n = parseSearchPriceValue(el.value);
  el.value = n != null ? String(n) : "";
}

function appendPriceParams(params) {
  const minEl = document.getElementById("min_price");
  const maxEl = document.getElementById("max_price");
  const minP = parseSearchPriceValue(minEl && minEl.value);
  const maxP = parseSearchPriceValue(maxEl && maxEl.value);
  if (minP != null) params.set("min_price", String(minP));
  if (maxP != null) params.set("max_price", String(maxP));
}

function appendBedsFilterParam(params) {
  const bf = document.getElementById("beds_filter");
  const v = toNumberOrNull(bf && bf.value);
  if (v != null) params.set("min_beds", String(v));
}

function clearSearchValidation() {
  const el = document.getElementById("searchValidation");
  if (!el) return;
  el.hidden = true;
  el.textContent = "";
}

function showSearchValidation(message) {
  const el = document.getElementById("searchValidation");
  if (!el) return;
  el.textContent = message;
  el.hidden = false;
}

function attachSearchFilterBehavior() {
  for (const id of ["min_price", "max_price"]) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.addEventListener("focus", () => normalizeSearchPriceInputForEdit(el));
    el.addEventListener("blur", () => formatSearchPriceInput(el));
  }
  const panel = document.querySelector(".panel--search");
  if (panel) {
    const maybeClear = (ev) => {
      const t = ev.target;
      if (
        t &&
        (t.id === "zip_code" ||
          t.id === "town" ||
          t.id === "min_price" ||
          t.id === "max_price" ||
          t.id === "beds_filter")
      ) {
        clearSearchValidation();
      }
    };
    panel.addEventListener("input", maybeClear);
    panel.addEventListener("change", maybeClear);
  }
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
  if (value === "high") return "Higher reliability";
  if (value === "medium") return "Moderate reliability";
  if (value === "low") return "Limited reliability";
  return "Estimate";
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
  const taxMo = annualTax != null && annualTax > 0 ? annualTax / 12 : null;
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
  const townRaw = document.getElementById("town").value.trim();
  if (townRaw) params.set("town", townRaw);
  appendPriceParams(params);
  appendBedsFilterParam(params);
  params.set("limit", "500");
  return params;
}

/** Preview insight vs area median (approximate when area stats loaded). */
function previewInsightClass(row) {
  const lp = toNumberOrNull(row.list_price);
  const med = lastAreaSummary && toNumberOrNull(lastAreaSummary.price_median);
  if (lp == null || med == null || med <= 0)
    return { cls: "preview-insight--neutral", label: "Limited context" };
  const pct = ((lp / med) - 1) * 100;
  if (Math.abs(pct) < 4) return { cls: "preview-insight--mid", label: "Near local median" };
  if (pct < 0) return { cls: "preview-insight--good", label: "Below similar homes" };
  return { cls: "preview-insight--mid", label: "Above recent comps" };
}

function clearPropertyCard() {
  const ids = [
    "listing_prop_address",
    "listing_prop_line2",
    "listing_prop_price",
    "listing_prop_beds_baths",
    "listing_prop_sqft",
    "listing_prop_type",
    "listing_prop_mls",
  ];
  for (const id of ids) {
    const el = document.getElementById(id);
    if (!el) continue;
    if (id === "listing_prop_address" || id === "listing_prop_line2") el.textContent = "";
    else el.textContent = "—";
  }
}

function populatePropertyCard(row) {
  if (!row) {
    clearPropertyCard();
    return;
  }
  const street = formatListingStreetLine(row);
  const line2 = formatListingCityStateZip(row);
  const line1 = street || line2 || "—";
  document.getElementById("listing_prop_address").textContent = line1;
  document.getElementById("listing_prop_line2").textContent = street && line2 ? line2 : "";
  document.getElementById("listing_prop_price").textContent = formatMoney(row.list_price) || "—";
  const beds = row.bedrooms != null ? String(row.bedrooms) : "—";
  const baths = row.total_baths != null ? String(row.total_baths) : "—";
  document.getElementById("listing_prop_beds_baths").textContent =
    beds !== "—" || baths !== "—" ? `${beds} / ${baths}` : "—";
  document.getElementById("listing_prop_sqft").textContent =
    row.square_feet != null ? String(Math.round(row.square_feet)) : "—";
  document.getElementById("listing_prop_type").textContent = row.property_type || "—";
  document.getElementById("listing_prop_mls").textContent = row.mls_id || "—";
}

function setInsightBadge(id, text, variant) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!text) {
    el.hidden = true;
    el.textContent = "";
    el.className = "insight-badge";
    return;
  }
  el.hidden = false;
  el.textContent = text;
  el.className = `insight-badge insight-badge--${variant || "neutral"}`;
}

function badgePriceVsComps(diffPct, compCount) {
  const n = Number(compCount || 0);
  if (n < 6) return { text: "Limited comp data", variant: "neutral" };
  if (diffPct == null || Math.abs(diffPct) < 3) return { text: "Near local median", variant: "medium" };
  if (diffPct < -3) return { text: "Below similar homes", variant: "good" };
  return { text: "Above recent comps", variant: "medium" };
}

function badgePpsf(subjPpsf, medianPpsf, compCount) {
  const n = Number(compCount || 0);
  if (n < 6 || medianPpsf == null || subjPpsf == null || subjPpsf <= 0)
    return { text: "Limited comp data", variant: "neutral" };
  const ratio = subjPpsf / medianPpsf - 1;
  if (Math.abs(ratio) < 0.07) return { text: "Near local median", variant: "medium" };
  if (ratio < 0) return { text: "Below similar homes", variant: "good" };
  return { text: "Above recent comps", variant: "medium" };
}

function updateCarryPanel() {
  const ctx = document.getElementById("fin_carry_context");
  const totalEl = document.getElementById("fin_carry_total");
  const piEl = document.getElementById("fin_carry_pi");
  const taxEl = document.getElementById("fin_carry_tax");
  const insEl = document.getElementById("fin_carry_insurance");
  const miscEl = document.getElementById("fin_carry_misc");
  const select = document.getElementById("listing_select");
  const mlsId = select && select.value;
  const row = mlsId ? lastListingRowsById.get(mlsId) : null;
  if (!row) {
    if (ctx) ctx.textContent = 'Select a home above and click "Analyze this home" to tie carry to a list price.';
    if (totalEl) totalEl.textContent = "";
    if (piEl) piEl.textContent = "—";
    if (taxEl) taxEl.textContent = "—";
    if (insEl) insEl.textContent = "—";
    if (miscEl) miscEl.textContent = "—";
    return;
  }
  const c = computeCarryForRow(row);
  if (!c) {
    if (ctx) ctx.textContent = "Missing list price on this row.";
    if (totalEl) totalEl.textContent = "";
    return;
  }
  if (ctx) ctx.textContent = "Based on the selected list price and your financing inputs.";
  if (totalEl) totalEl.textContent = formatMoney(c.total);
  if (piEl) piEl.textContent = formatMoney(c.pi);
  if (taxEl) taxEl.textContent = c.taxMo != null ? formatMoney(c.taxMo) : "—";
  if (insEl) insEl.textContent = formatMoney(c.insurance);
  if (miscEl) miscEl.textContent = formatMoney(c.misc);
}

function renderListings(rows) {
  resultsBody.innerHTML = "";
  if (resultsPreviewBody) resultsPreviewBody.innerHTML = "";

  const select = document.getElementById("listing_select");
  if (select) {
    const current = select.value;
    select.innerHTML = '<option value="">Select from your search results…</option>';
    lastListingRowsById = new Map();
    for (const row of rows) {
      if (!row.mls_id) continue;
      lastListingRowsById.set(String(row.mls_id), row);
      const option = document.createElement("option");
      const shortAddr = formatListingStreetLine(row) || row.full_address || row.address || "(no address)";
      option.value = String(row.mls_id);
      option.textContent = `${shortAddr} (${row.mls_id})`;
      select.appendChild(option);
    }
    if (current && lastListingRowsById.has(current)) {
      select.value = current;
    }
  }

  if (!rows.length) {
    renderEmptyTableRow(
      resultsBody,
      12,
      "No matching homes found. Try widening your price or bedroom filters.",
    );
    if (resultsPreviewBody) {
      renderEmptyTableRow(
        resultsPreviewBody,
        7,
        "No matching homes found. Try widening your price or bedroom filters.",
      );
    }
    if (toggleFullListingsBtn) {
      toggleFullListingsBtn.hidden = true;
      fullListingsSection.hidden = true;
    }
    updateListingSelectionVisibility();
    syncPreviewRowHighlight();
    updateCarryPanel();
    return;
  }

  const previewSlice = rows.slice(0, PREVIEW_ROWS);
  for (const row of previewSlice) {
    const tr = document.createElement("tr");
    tr.classList.add("preview-listing-row");
    if (row.mls_id != null) tr.setAttribute("data-mls-id", String(row.mls_id));
    const addr = formatListingStreetLine(row) || (row.full_address ?? row.address ?? "");
    const beds = row.bedrooms != null ? String(row.bedrooms) : "—";
    const baths = row.total_baths != null ? String(row.total_baths) : "—";
    const ins = previewInsightClass(row);
    const mid = escapeHtml(row.mls_id);
    tr.innerHTML = `
      <td data-label="Address">${escapeHtml(addr)}</td>
      <td data-label="Town">${escapeHtml(row.town)}</td>
      <td data-label="Price">${escapeHtml(formatMoney(row.list_price))}</td>
      <td data-label="Beds / baths">${escapeHtml(`${beds} / ${baths}`)}</td>
      <td data-label="Sq ft">${escapeHtml(row.square_feet != null ? String(Math.round(row.square_feet)) : "")}</td>
      <td data-label="Insight"><span class="preview-insight ${ins.cls}">${escapeHtml(ins.label)}</span></td>
      <td data-label="Analyze"><button type="button" class="btn-row-analyze" data-analyze-mls="${mid}">Analyze</button></td>
    `;
    if (resultsPreviewBody) resultsPreviewBody.appendChild(tr);
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    const onMap = hasLatLon(row) ? "Yes" : "No";
    const addr = formatListingStreetLine(row) || (row.full_address ?? row.address ?? "");
    const { taxDisp, piDisp, totalDisp } = formatCarryCells(row);
    tr.innerHTML = `
      <td data-label="Listing ID">${escapeHtml(row.mls_id)}</td>
      <td data-label="Address">${escapeHtml(addr)}</td>
      <td data-label="Town">${escapeHtml(row.town)}</td>
      <td data-label="ZIP">${escapeHtml(row.zip_code)}</td>
      <td data-label="On map?">${onMap}</td>
      <td data-label="Beds">${escapeHtml(row.bedrooms)}</td>
      <td data-label="Baths">${escapeHtml(row.total_baths)}</td>
      <td data-label="Sq ft">${escapeHtml(row.square_feet != null ? Math.round(row.square_feet) : "")}</td>
      <td data-label="List price">${escapeHtml(formatMoney(row.list_price))}</td>
      <td data-label="Monthly tax">${escapeHtml(taxDisp)}</td>
      <td data-label="Loan P&amp;I">${escapeHtml(piDisp)}</td>
      <td data-label="Est. total / mo">${escapeHtml(totalDisp)}</td>
    `;
    resultsBody.appendChild(tr);
  }

  if (toggleFullListingsBtn) {
    toggleFullListingsBtn.hidden = rows.length === 0;
    toggleFullListingsBtn.setAttribute("aria-expanded", fullListingsSection && !fullListingsSection.hidden ? "true" : "false");
  }
  updateListingSelectionVisibility();
  syncPreviewRowHighlight();
  updateCarryPanel();
}

function buildCarryPopupHtml(row) {
  const raw = formatListingStreetLine(row) || (row.full_address ?? row.address ?? "Listing");
  const addr = escapeHtml(raw);
  const price = formatMoney(row.list_price);
  const beds = row.bedrooms != null ? String(row.bedrooms) : "—";
  const baths = row.total_baths != null ? String(row.total_baths) : "—";
  const sqftRaw =
    row.square_feet != null && Number.isFinite(Number(row.square_feet))
      ? `${Math.round(Number(row.square_feet)).toLocaleString()} sq ft`
      : "";
  let meta = `${beds} bd / ${baths} ba`;
  if (sqftRaw) meta += ` · ${sqftRaw}`;
  let html = `<strong>${addr}</strong><br/>List: ${price}<br/><span class="map-popup-meta">${escapeHtml(meta)}</span>`;
  const c = computeCarryForRow(row);
  if (c) {
    const taxLine =
      c.taxMo == null ? "Tax/mo: — (no MLS tax)" : `Tax/mo: ${formatMoney(c.taxMo)}`;
    html += `<br/><hr style="margin:8px 0;border:none;border-top:1px solid #ccc"/>`;
    html += `<div style="font-size:13px;line-height:1.45">`;
    html += `P&amp;I: ${formatMoney(c.pi)}<br/>`;
    html += `${taxLine}<br/>`;
    html += `Insurance: ${formatMoney(c.insurance)} · Misc: ${formatMoney(c.misc)}<br/>`;
    html += `<strong>Est. carry/mo: ${formatMoney(c.total)}</strong>`;
    html += `</div>`;
  }
  const mid = escapeHtml(String(row.mls_id ?? ""));
  html += `<div class="map-popup-actions"><button type="button" class="map-popup-analyze-btn" data-map-analyze-mls="${mid}">Analyze this home</button></div>`;
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
        "We couldn’t finish placing every home on the map. Try your search again, or narrow your filters.";
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
  const aggregateNoteEl = document.getElementById("rent_aggregate_note");
  const sparseNoteEl = document.getElementById("rent_sparse_note");

  const params = new URLSearchParams();
  const zipRaw = document.getElementById("zip_code").value.trim();
  if (zipRaw) {
    const z = normalizeUsZip5(zipRaw);
    if (z) params.set("zip_code", z);
  }

  if (!params.has("zip_code")) {
    renderEmptyTableRow(compBody, 6, "Enter a ZIP above, then click “Show homes and insights” to load rental benchmarks.");
    setQualityChip("rent_quality_chip", "");
    if (aggregateNoteEl) aggregateNoteEl.textContent = "";
    if (sparseNoteEl) {
      sparseNoteEl.hidden = true;
      sparseNoteEl.textContent = "";
    }
    return;
  }

  appendBedsFilterParam(params);
  const rentMonths = clampRentLookbackMonths(rentLookbackEl ? rentLookbackEl.value : 12);
  params.set("months_back", String(rentMonths));

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
        "Rental benchmarks are limited for this ZIP and bedroom range. Try broadening bedrooms, a longer period, or a nearby ZIP.",
      );
      setQualityChip("rent_quality_chip", "Not enough data yet", "neutral");
      if (aggregateNoteEl) aggregateNoteEl.textContent = "";
      if (sparseNoteEl) {
        sparseNoteEl.hidden = false;
        sparseNoteEl.textContent =
          "Limited rental data for this period. Try a longer period for a more stable benchmark.";
      }
      return;
    }
    let maxSample = 0;
    let totalLeases = 0;
    for (const row of rows.slice(0, 200)) {
      maxSample = Math.max(maxSample, Number(row.sample_size || 0));
      totalLeases += Number(row.sample_size || 0);
      const tr = document.createElement("tr");
      tr.innerHTML = `
      <td data-label="ZIP">${row.zip_code}</td>
      <td data-label="Beds">${row.bedrooms}</td>
      <td data-label="Typical rent">${formatMoney(row.median_rent)}</td>
      <td data-label="Average rent">${formatMoney(row.avg_rent)}</td>
      <td data-label="Recent rentals">${row.sample_size ?? ""}</td>
      <td data-label="Confidence">${formatConfidenceLabel(row.confidence ?? "")}</td>
    `;
      compBody.appendChild(tr);
    }
    const rentQ = qualityFromCount(maxSample, 40, 12);
    setQualityChip("rent_quality_chip", `${rentQ.label} · leases`, rentQ.tone);
    if (aggregateNoteEl) {
      aggregateNoteEl.textContent = `Based on ${totalLeases} recent rental${totalLeases === 1 ? "" : "s"} from the last ${rentMonths} months.`;
    }
    if (sparseNoteEl) {
      if (totalLeases > 0 && totalLeases < 10) {
        sparseNoteEl.hidden = false;
        sparseNoteEl.textContent =
          "Limited rental data for this period. Try a longer period for a more stable benchmark.";
      } else {
        sparseNoteEl.hidden = true;
        sparseNoteEl.textContent = "";
      }
    }
  } catch (err) {
    renderEmptyTableRow(
      compBody,
      6,
      "We couldn't load rental benchmarks right now. Please try again in a moment.",
    );
    setQualityChip("rent_quality_chip", "Rental data unavailable", "neutral");
    if (aggregateNoteEl) aggregateNoteEl.textContent = "";
    if (sparseNoteEl) {
      sparseNoteEl.hidden = true;
      sparseNoteEl.textContent = "";
    }
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
  appendBedsFilterParam(params);

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
    setQualityChip("area_price_confidence", "");
    setQualityChip("area_trend_confidence", "");
    renderTrendSparkline([]);
    lastAreaSummary = null;
    setAreaSnapshotCompactMode(false);
    return;
  }

  try {
    setAreaSnapshotCompactMode(false);
    setSkeletonState(AREA_METRIC_IDS, true);
    async function fetchAreaStats(localParams) {
      const res = await fetch(apiUrl(`/sold-area-stats?${localParams.toString()}`));
      if (!res.ok) throw new Error("area_stats_unavailable");
      return await res.json();
    }

    let data = await fetchAreaStats(params);
    let summary = data.summary;
    let trend = Array.isArray(data.trend_by_month) ? data.trend_by_month : [];
    let active = data.current_active_snapshot;
    let fallbackNote = "";

    if (data.error) {
      noteEl.textContent = "";
      priceMainEl.textContent = "";
      priceRangeEl.textContent = "";
      ppsfEl.textContent = "";
      volEl.textContent = "";
      trendSummaryEl.textContent = "";
      activeSummaryEl.textContent = "";
      activeNoteEl.textContent = "";
      setQualityChip("area_price_confidence", "", "");
      setQualityChip("area_trend_confidence", "");
      renderTrendSparkline([]);
      lastAreaSummary = null;
      setAreaSnapshotCompactMode(true, clientAreaStatsUnavailableNote());
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
          "We widened the window to the last 24 months because the last 12 months had too few sales for a reliable read.";
      }
    }

    if (!summary || !summary.num_sales) {
      noteEl.textContent = "";
      priceMainEl.textContent = "";
      priceRangeEl.textContent = "";
      ppsfEl.textContent = "";
      volEl.textContent = "";
      trendSummaryEl.textContent = "";
      activeSummaryEl.textContent = "";
      activeNoteEl.textContent = "";
      setQualityChip("area_price_confidence", "", "");
      setQualityChip("area_trend_confidence", "");
      renderTrendSparkline([]);
      lastAreaSummary = null;
      setAreaSnapshotCompactMode(
        true,
        "Recent sale benchmarks are temporarily unavailable for this area. You can still browse active homes and estimate monthly payments.",
      );
      return;
    }

    lastAreaSummary = summary;
    setAreaSnapshotCompactMode(false);

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
      priceRangeEl.textContent = `About half of similar homes sold between ${formatMoney(p25)} and ${formatMoney(p75)}.`;
    } else {
      priceRangeEl.textContent = "";
    }

    ppsfEl.textContent =
      summary.price_sqft_median != null
        ? `${formatMoney(summary.price_sqft_median)} / sq ft`
        : "Not enough size data yet.";

    const numSales = summary.num_sales;
    volEl.textContent = `${numSales} recent sale${numSales === 1 ? "" : "s"} in this filter set.`;
    const salesQ = qualityFromCount(numSales, 35, 12);
    setQualityChip("area_price_confidence", `${salesQ.label}`, salesQ.tone);

    if (trend.length >= 2) {
      const first = trend[0];
      const last = trend[trend.length - 1];
      if (first.median_price != null && last.median_price != null && first.median_price > 0) {
        const changePct = ((last.median_price / first.median_price - 1) * 100).toFixed(1);
        const dir =
          Math.abs(Number(changePct)) < 1
            ? "mostly flat"
            : Number(changePct) > 0
              ? "up"
              : "down";
        trendSummaryEl.textContent = `From ${first.month} to ${last.month}, median sold prices moved ${dir} about ${Math.abs(Number(changePct))}% (where we have enough monthly sales).`;
      } else {
        trendSummaryEl.textContent = "";
      }
      const trendQ = qualityFromCount(
        trend.reduce((acc, cur) => acc + Number(cur.num_sales || 0), 0),
        120,
        45,
      );
      setQualityChip("area_trend_confidence", `${trendQ.label} · sales trend`, trendQ.tone);
    } else {
      trendSummaryEl.textContent = "";
      setQualityChip("area_trend_confidence", "Not enough history to chart", "neutral");
    }
    renderTrendSparkline(trend);

    if (active && active.num_active) {
      activeSummaryEl.textContent = `${active.num_active} active listing${active.num_active === 1 ? "" : "s"} match these filters.`;
      if (active.active_price_median != null && summary.price_median != null) {
        const diff = active.active_vs_sold_pct ?? 0;
        const aboveBelow =
          Math.abs(diff) < 1 ? "about in line with" : diff > 0 ? "above" : "below";
        activeNoteEl.textContent = `Asking prices are ${aboveBelow} recent sold prices for similar homes (about ${Math.abs(diff).toFixed(1)}% ${diff > 0 ? "higher" : "lower"} than the typical recent sale).`;
      } else {
        activeNoteEl.textContent =
          "We couldn’t compare asking prices to recent sales here; you can still use listings below.";
      }
    } else {
      activeSummaryEl.textContent = "No active listings match these filters right now.";
      activeNoteEl.textContent = "";
    }
  } catch (err) {
    noteEl.textContent = "";
    priceMainEl.textContent = "";
    priceRangeEl.textContent = "";
    ppsfEl.textContent = "";
    volEl.textContent = "";
    trendSummaryEl.textContent = "";
    activeSummaryEl.textContent = "";
    activeNoteEl.textContent = "";
    setQualityChip("area_price_confidence", "", "");
    setQualityChip("area_trend_confidence", "");
    renderTrendSparkline([]);
    lastAreaSummary = null;
    setAreaSnapshotCompactMode(true, clientAreaStatsUnavailableNote());
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
  clearSearchValidation();
  const minP = parseSearchPriceValue(document.getElementById("min_price").value);
  const maxP = parseSearchPriceValue(document.getElementById("max_price").value);
  if (minP != null && maxP != null && maxP < minP) {
    showSearchValidation("Max price should be greater than min price.");
    statusEl.textContent = "";
    return;
  }

  const params = getSearchParams();
  if (!hasAreaScope(params)) {
    hideResultsFlow();
    showSearchValidation("Enter a ZIP code or town to continue.");
    statusEl.textContent = "";
    await loadAreaStatsFromMainFilters();
    clearMapMarkers();
    lastListingRows = [];
    if (toggleFullListingsBtn) toggleFullListingsBtn.hidden = true;
    return;
  }

  try {
    revealResultsAfterSearch();
    showLoadingBarIndeterminate();
    statusEl.textContent = "Loading… fetching area stats and listings.";
    if (searchBtn) searchBtn.disabled = true;
    setTableSkeleton("#results_table_wrap", true);
    setTableSkeleton("#rent_table_wrap", true);

    await loadAreaStatsFromMainFilters();

    const res = await fetch(apiUrl(`/active-listings?${params.toString()}`));
    if (!res.ok) throw new Error("LISTINGS_UNAVAILABLE");
    const rows = await res.json();
    setLoadingBarPercent(22);
    lastListingRows = rows;
    renderListings(rows);
    await renderMarkers(rows);
    statusEl.textContent = `Loaded ${rows.length} listings (${countPins(rows)} on map).`;

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
  } catch (_err) {
    hideLoadingBar();
    statusEl.textContent =
      "We couldn’t load listings right now. Check your connection and try again.";
  } finally {
    if (searchBtn) searchBtn.disabled = false;
    setTableSkeleton("#results_table_wrap", false);
    setTableSkeleton("#rent_table_wrap", false);
  }
}

function formatSoldCompAddressLine(c) {
  const line = formatListingStreetLine({
    full_address: c.full_address,
    address: c.address,
    town: c.town,
    zip_code: c.zip_code,
  });
  return line || String(c.full_address ?? c.address ?? "").trim();
}

function renderComparableRows(compsBodyEl, comps) {
  compsBodyEl.innerHTML = "";
  const table = document.getElementById("listing_comps_table");
  if (table) table.classList.add("comps-collapsed");

  if (!comps.length) {
    if (listingCompsExpandBtn) listingCompsExpandBtn.hidden = true;
    return;
  }

  comps.forEach((c, idx) => {
    const tr = document.createElement("tr");
    if (idx >= COMP_PREVIEW_ROWS) tr.classList.add("comps-row--extra");
    tr.innerHTML = `
        <td data-label="Address">${escapeHtml(formatSoldCompAddressLine(c))}</td>
        <td data-label="Sold price">${formatMoney(c.sale_price)}</td>
        <td data-label="Beds">${escapeHtml(c.bedrooms ?? "")}</td>
        <td data-label="Baths">${escapeHtml(c.total_baths ?? "")}</td>
        <td data-label="Sq ft">${escapeHtml(c.square_feet ?? "")}</td>
        <td data-label="Sale date">${escapeHtml(formatDateShort(c.settled_date))}</td>
      `;
    compsBodyEl.appendChild(tr);
  });

  const extra = comps.length > COMP_PREVIEW_ROWS;
  if (listingCompsExpandBtn) {
    listingCompsExpandBtn.hidden = !extra;
    listingCompsExpandBtn.textContent =
      extra ? `View all ${comps.length} matching sales` : "View all matching sales";
  }
}

async function analyzeSelectedListing() {
  const select = document.getElementById("listing_select");
  const mlsId = select.value;
  const priceVsEl = document.getElementById("listing_price_vs_area");
  const priceBandEl = document.getElementById("listing_price_band");
  const ppsfEl = document.getElementById("listing_ppsf");
  const ppsfNoteEl = document.getElementById("listing_ppsf_note");
  const payEl = document.getElementById("listing_payment");
  const payNoteEl = document.getElementById("listing_payment_note");
  const compsBody = document.getElementById("listing_comps_body");
  const compsNoteEl = document.getElementById("listing_comps_note");

  setInsightBadge("listing_badge_price", "", null);
  setInsightBadge("listing_badge_ppsf", "", null);
  setInsightBadge("listing_badge_payment", "", null);

  if (!mlsId) {
    clearPropertyCard();
    if (panelCompsEl) panelCompsEl.hidden = true;
    hideListingLimitations();
    priceVsEl.textContent = "";
    priceBandEl.textContent = "";
    ppsfEl.textContent = "";
    ppsfNoteEl.textContent = "";
    payEl.textContent = "";
    payNoteEl.textContent = "";
    if (compsBody) compsBody.innerHTML = "";
    if (listingCompsExpandBtn) listingCompsExpandBtn.hidden = true;
    if (compsNoteEl) compsNoteEl.textContent = "";
    clearListingTakeaways();
    clearListingCompsPeriodCopy();
    syncPreviewRowHighlight();
    updateCarryPanel();
    return;
  }

  const row = lastListingRowsById.get(mlsId);
  populatePropertyCard(row);

  if (panelCompsEl) panelCompsEl.hidden = false;
  if (compsNoteEl) compsNoteEl.textContent = "";
  clearListingTakeaways();

  const preferredMonths = clampCompsLookbackMonths(compsLookbackEl?.value);

  try {
    hideListingLimitations();
    clearListingCompsPeriodCopy();
    setSkeletonState(LISTING_METRIC_IDS, true);
    setTableSkeleton("#listing_comps_wrap", true);
    if (analyzeBtn) {
      analyzeBtn.disabled = true;
      analyzeBtn.textContent = "Analyzing…";
    }

    const res = await fetch(
      apiUrl(`/sold-comps?mls_id=${encodeURIComponent(mlsId)}&months_back=${preferredMonths}`),
    );
    const data = await res.json().catch(() => ({}));

    const carryForUi = row ? computeCarryForRow(row) : null;

    function finishListingOnlyCompsPath(kind, compsTableMsg, limitationMode, lookbackFromApi) {
      const lb =
        lookbackFromApi != null && lookbackFromApi !== undefined
          ? clampCompsLookbackMonths(lookbackFromApi)
          : preferredMonths;
      setListingCompsUnavailablePriceCards(kind);
      fillListingPpsfAndPaymentFromRow(row, null);
      renderEmptyTableRow(compsBody, 6, compsTableMsg);
      if (compsNoteEl) compsNoteEl.textContent = "";
      if (limitationMode === "sold_data") {
        if (listingLimitationsTextEl) {
          listingLimitationsTextEl.textContent =
            "Recent sale benchmarks are temporarily unavailable. You can still review the listing and estimated monthly cost.";
          if (listingLimitationsBoxEl) listingLimitationsBoxEl.hidden = false;
        }
      } else {
        showListingLimitationsForListingOnlyAnalysis();
      }
      setQualityChip(
        "listing_comp_confidence",
        kind === "empty_pool" ? "Limited comp data" : "Unavailable",
        kind === "empty_pool" ? "low" : "neutral",
      );
      renderListingTakeaways({}, {}, carryForUi);
      updateListingCompsPeriodCopy(0, lb);
      updateCarryPanel();
      scrollListingDealIntoView();
    }

    if (!res.ok) {
      finishListingOnlyCompsPath(
        "network",
        "Recent comparable sales didn’t load. You can still use list price and monthly cost below.",
        "listing_only",
        undefined,
      );
      return;
    }

    if (data.error === "listing_not_found" || data.error === "mls_required") {
      finishListingOnlyCompsPath(
        "default",
        "We couldn’t match this listing for comparable sales. Try selecting the home again.",
        "listing_only",
        data.lookback_months,
      );
      return;
    }

    if (data.error === "sold_data_unavailable") {
      finishListingOnlyCompsPath(
        "sold_data",
        "Recent comparable sales didn’t load for this home.",
        "sold_data",
        data.lookback_months,
      );
      return;
    }

    if (data.error) {
      finishListingOnlyCompsPath(
        "default",
        "Recent comparable sales didn’t load for this home.",
        "listing_only",
        data.lookback_months,
      );
      return;
    }

    const subject = data.subject || {};
    const summary = data.summary || {};
    const comps = Array.isArray(data.comps) ? data.comps : [];
    const matchHint = typeof data.match_hint === "string" ? data.match_hint.trim() : "";

    if (!summary.num_comps) {
      finishListingOnlyCompsPath(
        "empty_pool",
        "No strong comparable sales were found for this home right now.",
        "listing_only",
        data.lookback_months,
      );
      return;
    }

    const med = summary.median_price;
    const p25 = summary.price_p25;
    const p75 = summary.price_p75;
    const listPrice = subject.list_price;
    const diffPct = summary.list_vs_median_pct;
    const fullSetCount = toNumberOrNull(summary.total_comps_considered);

    const bp = badgePriceVsComps(diffPct, fullSetCount ?? summary.num_comps);
    setInsightBadge("listing_badge_price", bp.text, bp.variant);

    if (med != null && listPrice != null) {
      const dir =
        diffPct == null || Math.abs(diffPct) < 1
          ? "in line with what similar homes have been selling for"
          : diffPct > 0
            ? "above what similar homes have been selling for"
            : "below what similar homes have been selling for";
      const pctText =
        diffPct == null || Math.abs(diffPct) < 1
          ? ""
          : ` (about ${Math.abs(diffPct).toFixed(1)}% ${diffPct > 0 ? "higher" : "lower"} than the median of this comp set)`;
      priceVsEl.textContent = `This asking price is ${dir}${pctText}.`;
    } else {
      priceVsEl.textContent = "";
    }

    if (p25 != null && p75 != null) {
      priceBandEl.textContent = `About half of similar nearby sales in this set closed between ${formatMoney(p25)} and ${formatMoney(p75)}.`;
    } else {
      priceBandEl.textContent = "";
    }

    fillListingPpsfAndPaymentFromRow(row, summary);

    const carry = row ? computeCarryForRow(row) : null;

    if (compsNoteEl && fullSetCount != null && fullSetCount > 0) {
      compsNoteEl.textContent = `This summary uses ${fullSetCount} recent sales that fit the match rules. The table shows the closest matches (up to ${comps.length}).`;
    } else if (compsNoteEl && comps.length) {
      compsNoteEl.textContent = `Showing ${comps.length} closest matching sales.`;
    }
    if (matchHint && compsNoteEl) {
      compsNoteEl.textContent = [compsNoteEl.textContent, matchHint].filter(Boolean).join(" ");
    }

    showListingLimitationsPlain(summary, fullSetCount);
    const compQ = qualityFromCount(fullSetCount ?? summary.num_comps, 35, 12);
    const poolN = fullSetCount ?? summary.num_comps;
    setQualityChip("listing_comp_confidence", `${compQ.label} · ${poolN} sales compared`, compQ.tone);
    renderListingTakeaways(summary, subject, carry);
    renderComparableRows(compsBody, comps);

    const yDisp = toNumberOrNull(data.lookback_months) ?? preferredMonths;
    updateListingCompsPeriodCopy(fullSetCount ?? summary.num_comps, yDisp);

    updateCarryPanel();
    scrollListingDealIntoView();
  } catch (err) {
    const carry = row ? computeCarryForRow(row) : null;
    setListingCompsUnavailablePriceCards("network");
    fillListingPpsfAndPaymentFromRow(row, null);
    renderEmptyTableRow(
      compsBody,
      6,
      "Recent comparable sales didn’t load. You can still use list price and monthly cost below.",
    );
    if (compsNoteEl) compsNoteEl.textContent = "";
    showListingLimitationsForListingOnlyAnalysis();
    setQualityChip("listing_comp_confidence", "Unavailable", "neutral");
    renderListingTakeaways({}, {}, carry);
    updateListingCompsPeriodCopy(0, preferredMonths);
    updateCarryPanel();
    scrollListingDealIntoView();
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
  for (const id of ["zip_code", "town", "min_price", "max_price", "beds_filter"]) {
    const el = document.getElementById(id);
    if (el) el.value = "";
  }
}

document.getElementById("searchBtn").addEventListener("click", searchListings);
document.getElementById("clearBtn").addEventListener("click", () => {
  clearSearchValidation();
  clearFilters();
  clearMapMarkers();
  lastListingRows = [];
  lastAreaSummary = null;
  hideResultsFlow();
  if (panelCompsEl) panelCompsEl.hidden = true;
  hideListingLimitations();
  renderListings([]);
  renderEmptyTableRow(resultsBody, 12, "Filters cleared. Add a ZIP code or town above to run a new search.");
  if (resultsPreviewBody) {
    renderEmptyTableRow(resultsPreviewBody, 7, "Run a search to see listings here.");
  }
  statusEl.textContent =
    "Filters cleared. Enter a ZIP code or town to start, then click “Show homes and insights”.";
  setQualityChip("area_price_confidence", "");
  setQualityChip("area_trend_confidence", "");
  setQualityChip("rent_quality_chip", "");
  setQualityChip("listing_comp_confidence", "");
  renderTrendSparkline([]);
  clearListingTakeaways();
  clearPropertyCard();
  if (fullListingsSection) fullListingsSection.hidden = true;
  if (toggleFullListingsBtn) {
    toggleFullListingsBtn.hidden = true;
    toggleFullListingsBtn.setAttribute("aria-expanded", "false");
  }
  loadAreaStatsFromMainFilters();
  loadCompsFromMainFilters();
  updateCarryPanel();
});

if (analyzeBtn) {
  analyzeBtn.addEventListener("click", analyzeSelectedListing);
}

if (compsLookbackEl) {
  compsLookbackEl.addEventListener("change", () => {
    const sel = document.getElementById("listing_select");
    if (sel && sel.value) analyzeSelectedListing();
  });
}

if (rentLookbackEl) {
  rentLookbackEl.addEventListener("change", () => void loadCompsFromMainFilters());
}

if (listingCompsExpandBtn) {
  listingCompsExpandBtn.addEventListener("click", () => {
    const table = document.getElementById("listing_comps_table");
    if (!table) return;
    const nowCollapsed = table.classList.toggle("comps-collapsed");
    listingCompsExpandBtn.textContent = nowCollapsed ? "View all matching sales" : "Show fewer rows";
  });
}

if (toggleFullListingsBtn && fullListingsSection) {
  toggleFullListingsBtn.addEventListener("click", () => {
    const wasHidden = fullListingsSection.hidden;
    fullListingsSection.hidden = !wasHidden;
    toggleFullListingsBtn.setAttribute("aria-expanded", wasHidden ? "true" : "false");
    toggleFullListingsBtn.textContent = wasHidden ? "Hide full listing table" : "See all active listings";
  });
}

document.getElementById("listing_select").addEventListener("change", () => {
  syncPreviewRowHighlight();
  updateListingSelectionVisibility();
  updateCarryPanel();
});

if (resultsPreviewBody) {
  resultsPreviewBody.addEventListener("click", (e) => {
    const analyzeEl = e.target.closest("[data-analyze-mls]");
    if (analyzeEl) {
      const id = analyzeEl.getAttribute("data-analyze-mls");
      if (!id) return;
      const sel = document.getElementById("listing_select");
      if (sel && lastListingRowsById.has(id)) {
        sel.value = id;
        updateListingSelectionVisibility();
        void analyzeSelectedListing();
      }
      return;
    }
    const tr = e.target.closest("tr.preview-listing-row[data-mls-id]");
    if (!tr) return;
    const id = tr.getAttribute("data-mls-id");
    if (!id || !lastListingRowsById.has(id)) return;
    selectListingByMlsId(id);
  });
}

document.body.addEventListener("click", (e) => {
  const btn = e.target.closest(".map-popup-analyze-btn[data-map-analyze-mls]");
  if (!btn) return;
  const id = btn.getAttribute("data-map-analyze-mls");
  if (!id || !lastListingRowsById.has(id)) return;
  e.preventDefault();
  const sel = document.getElementById("listing_select");
  if (sel) sel.value = id;
  updateListingSelectionVisibility();
  syncPreviewRowHighlight();
  updateCarryPanel();
  void analyzeSelectedListing();
});

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
    attachSearchFilterBehavior();
    applyFlowDom(false);
    updateListingSelectionVisibility();
    updateCarryPanel();
    statusEl.textContent = "Enter a ZIP code or town to start, then click “Show homes and insights”.";
  });
