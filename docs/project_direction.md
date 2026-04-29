# Project Direction

## Mission

Build a brokerage platform where buyers can evaluate homes with transparent analytics, financing context, and location intelligence.

The long-term listing source is an MLS VOW feed (including photos). Until that is available, the current MLS scraping pipeline remains the active listing source and testing backbone.

## Current State vs Target State

- Current active listing source:
  - MLS browser scraping (`scrape_mls_active.py`)
- Target active listing source:
  - MLS VOW listing feed + listing photos
- Current analytics foundation:
  - sold/rented history, area stats, comps, carry estimate, rent models
- Target analytics experience:
  - enriched property scoring and insights in buyer workflows and newsletters

## Product Phases

### Phase 0 (Now): MLS Foundation

- Maintain weekly sold/rented and daily active MLS workflows.
- Keep historical memorialization policy and API outputs stable.
- Continue beta testing analytics/UI layouts on scraped active data.

### Phase 1 (Pre-VOW): Enrichment Layers

- Add school system/ranking enrichment.
- Add healthcare/hospital proximity enrichment.
- Add pluggable finance-rate provider contract (current static presets, future partner bank API).
- Make enrichment outputs reusable in API responses and newsletter generation.

### Phase 2 (Pre-VOW): Buyer Insight Surfaces

- Expand property-level insight blocks in dashboard/UI.
- Add newsletter-ready insight fields per listing:
  - pricing context
  - finance carry estimate
  - school and healthcare context
- Harden scoring logic and explainability for beta users.

### Phase 3 (Later): VOW Feed Integration

- Introduce VOW-backed active listing source adapter.
- Preserve existing analytics/enrichment layers; swap only active listing source.
- Integrate listing photos/media in API + buyer UI.

### Phase 4: Brokerage Platform Expansion

- Buyer account workflows and saved preferences.
- Insight-driven notifications and campaign tooling.
- Transaction process support after client selection.

## Directional Principles

- Source-agnostic architecture:
  - analytics and enrichment must not depend on scraper internals.
- Property-centric modeling:
  - normalize identity/address joins early to support source swaps.
- Incremental delivery:
  - ship enrichment and insight value before VOW is available.
- Explainable analytics:
  - keep metrics interpretable for clients and agents.

## Near-Term Non-Goals

- Do not block roadmap progress waiting for VOW access.
- Do not couple new enrichment logic directly to scraper-specific CSV structure where avoidable.

## Immediate Planning Focus

1. Keep active MLS scrape as the beta listing backbone.
2. Build enrichment layers next (schools, healthcare, finance provider abstraction).
3. Prepare adapter boundaries so VOW becomes a listing-source swap later, not a platform rewrite.
