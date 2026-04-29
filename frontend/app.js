const statusEl = document.getElementById("status");
const loadingBarWrap = document.getElementById("loadingBarWrap");
const loadingBarFill = document.getElementById("loadingBarFill");
const resultsBody = document.querySelector("#resultsTable tbody");
const compBody = document.querySelector("#compTable tbody");

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

function finishLoadingBar() {
  setLoadingBarPercent(100);
  return new Promise((r) => setTimeout(r, 280)).then(() => {
    hideLoadingBar();
  });
}

const map = L.map("map").setView([42.3601, -71.0589], 9);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);
const markerLayer = L.featureGroup().addTo(map);

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
      option.textContent = `${row.mls_id} — ${addr}`;
      select.appendChild(option);
    }
    // try to preserve previous selection if still present
    if (current && lastListingRowsById.has(current)) {
      select.value = current;
    }
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    const onMap = hasLatLon(row) ? "Yes" : "No";
    const addr = row.full_address ?? row.address ?? "";
    const { taxDisp, piDisp, totalDisp } = formatCarryCells(row);
    tr.innerHTML = `
      <td>${escapeHtml(row.mls_id)}</td>
      <td>${escapeHtml(addr)}</td>
      <td>${escapeHtml(row.town)}</td>
      <td>${escapeHtml(row.zip_code)}</td>
      <td>${onMap}</td>
      <td>${escapeHtml(row.bedrooms)}</td>
      <td>${escapeHtml(row.total_baths)}</td>
      <td>${escapeHtml(row.square_feet)}</td>
      <td>${escapeHtml(formatMoney(row.list_price))}</td>
      <td>${escapeHtml(taxDisp)}</td>
      <td>${escapeHtml(piDisp)}</td>
      <td>${escapeHtml(totalDisp)}</td>
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

function renderMarkers(rows) {
  markerLayer.clearLayers();
  let count = 0;
  for (const row of rows) {
    const lat = toNumberOrNull(row.latitude);
    const lon = toNumberOrNull(row.longitude);
    if (lat == null || lon == null) continue;
    count += 1;
    L.marker([lat, lon]).bindPopup(buildCarryPopupHtml(row)).addTo(markerLayer);
  }
  if (count > 0) {
    const b = markerLayer.getBounds();
    if (b.isValid()) {
      map.fitBounds(b, { padding: [20, 20] });
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
      const res = await fetch("/geocode/active-listings", {
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
      renderMarkers(rows);
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
    compBody.innerHTML = "";
    const tr = document.createElement("tr");
    tr.innerHTML =
      '<td colspan="6" class="note">Enter a ZIP above, then search, to load rent comps for that area.</td>';
    compBody.appendChild(tr);
    return;
  }

  const minB = toNumberOrNull(document.getElementById("min_beds").value);
  const maxB = toNumberOrNull(document.getElementById("max_beds").value);
  if (minB != null) params.set("min_beds", String(minB));
  if (maxB != null) params.set("max_beds", String(maxB));

  try {
    const res = await fetch(`/analytics/rent-by-zip-bedroom?${params.toString()}`);
    if (!res.ok) throw new Error(`Rent comps failed (${res.status})`);
    const rows = await res.json();
    compBody.innerHTML = "";
    for (const row of rows.slice(0, 200)) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
      <td>${row.zip_code}</td>
      <td>${row.bedrooms}</td>
      <td>${formatMoney(row.median_rent)}</td>
      <td>${formatMoney(row.avg_rent)}</td>
      <td>${row.sample_size ?? ""}</td>
      <td>${row.confidence ?? ""}</td>
    `;
      compBody.appendChild(tr);
    }
  } catch (err) {
    compBody.innerHTML = "";
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="6" class="note">${err.message}</td>`;
    compBody.appendChild(tr);
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
    return;
  }

  try {
    const res = await fetch(`/sold-area-stats?${params.toString()}`);
    if (!res.ok) throw new Error(`Area stats failed (${res.status})`);
    const data = await res.json();
    const summary = data.summary;
    const trend = Array.isArray(data.trend_by_month) ? data.trend_by_month : [];
    const active = data.current_active_snapshot;

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
      return;
    }

    noteEl.textContent =
      "Based on roughly the last year of similar sales in this area. Individual homes can be above or below these ranges depending on condition, location, and features.";

    const pMed = summary.price_median;
    const p25 = summary.price_p25;
    const p75 = summary.price_p75;
    priceMainEl.textContent = pMed != null ? formatMoney(pMed) : "";
    if (p25 != null && p75 != null) {
      priceRangeEl.textContent = `Most similar homes in this area sold between ${formatMoney(
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
        trendSummaryEl.textContent = `Over the last year, prices here ${dir} about ${Math.abs(
          Number(changePct),
        )}% over the last ${trend.length} months.`;
      } else {
        trendSummaryEl.textContent = "";
      }
    } else {
      trendSummaryEl.textContent = "";
    }

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
    noteEl.textContent = String(err.message || err);
    priceMainEl.textContent = "";
    priceRangeEl.textContent = "";
    ppsfEl.textContent = "";
    volEl.textContent = "";
    trendSummaryEl.textContent = "";
    activeSummaryEl.textContent = "";
    activeNoteEl.textContent = "";
  }
}

function refreshListingDisplays() {
  if (lastListingRows) {
    renderListings(lastListingRows);
    renderMarkers(lastListingRows);
  }
}

async function searchListings() {
  try {
    showLoadingBarIndeterminate();
    statusEl.textContent = "Loading… fetching area stats and listings.";
    const params = getSearchParams();

    // Load area stats first so we can talk about “what’s normal” for this area.
    await loadAreaStatsFromMainFilters();

    const res = await fetch(`/active-listings?${params.toString()}`);
    if (!res.ok) throw new Error(`Failed to load listings (${res.status})`);
    const rows = await res.json();
    setLoadingBarPercent(22);
    lastListingRows = rows;
    renderListings(rows);
    renderMarkers(rows);
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
  } catch (err) {
    hideLoadingBar();
    statusEl.textContent = err.message;
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
    compsBody.innerHTML = "";
    return;
  }

  const row = lastListingRowsById.get(mlsId);
  const addr = row ? row.full_address ?? row.address ?? "" : "";
  headlineEl.textContent = addr ? "How does this home compare?" : "How does this home compare?";
  subEl.textContent =
    "We’ll look at roughly the last year of similar sales nearby to see what’s typical, then show a rough monthly payment using the financing settings above.";

  try {
    const res = await fetch(`/sold-comps?mls_id=${encodeURIComponent(mlsId)}`);
    if (!res.ok) throw new Error(`Comps lookup failed (${res.status})`);
    const data = await res.json();

    if (data.error) {
      priceVsEl.textContent = "";
      priceBandEl.textContent = "";
      ppsfEl.textContent = "";
      ppsfNoteEl.textContent = "";
      payEl.textContent = "";
      payNoteEl.textContent = data.error;
      compsBody.innerHTML = "";
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
      compsBody.innerHTML = "";
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
      priceBandEl.textContent = `Recently, most similar homes nearby sold between ${formatMoney(
        p25,
      )} and ${formatMoney(p75)} in the last year or so.`;
    } else {
      priceBandEl.textContent = "";
    }

    if (summary.median_ppsf != null && listPrice != null && subject.square_feet) {
      const subjPpsf = listPrice / subject.square_feet;
      ppsfEl.textContent = `${formatMoney(subjPpsf)} per sq ft (this home)`;
      ppsfNoteEl.textContent = `Similar recent sales averaged around ${formatMoney(
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
    for (const c of comps) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(c.full_address ?? "")}</td>
        <td>${formatMoney(c.sale_price)}</td>
        <td>${escapeHtml(c.bedrooms ?? "")}</td>
        <td>${escapeHtml(c.total_baths ?? "")}</td>
        <td>${escapeHtml(c.square_feet ?? "")}</td>
        <td>${escapeHtml(c.settled_date ?? "")}</td>
      `;
      compsBody.appendChild(tr);
    }
  } catch (err) {
    priceVsEl.textContent = "";
    priceBandEl.textContent = "";
    ppsfEl.textContent = "";
    ppsfNoteEl.textContent = "";
    payEl.textContent = "";
    payNoteEl.textContent = String(err.message || err);
    compsBody.innerHTML = "";
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
  searchListings();
});

const analyzeBtn = document.getElementById("analyzeListingBtn");
if (analyzeBtn) {
  analyzeBtn.addEventListener("click", analyzeSelectedListing);
}

document.getElementById("fin_product").addEventListener("change", () => {
  applyMortgagePresetToForm();
  refreshListingDisplays();
});

for (const id of ["fin_down_pct", "fin_rate", "fin_term_years", "fin_insurance", "fin_misc"]) {
  document.getElementById(id).addEventListener("input", refreshListingDisplays);
}

applyMortgagePresetToForm();
loadCompsFromMainFilters();
statusEl.textContent = "Set filters and click Search Listings.";
