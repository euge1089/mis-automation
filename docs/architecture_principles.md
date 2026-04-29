# Architecture Principles

## Goal

Keep today’s MLS scraping workflows productive while making a clean future transition to an MLS VOW feed and richer buyer-facing analytics.

## Core Boundaries

### Active Listing Source Adapter

Define active listing ingestion behind a source boundary:

- current adapter: MLS scraping (`scrape_mls_active.py`)
- future adapter: MLS VOW feed (with photos/media)

Everything downstream (cleaning, enrichment, analytics, API payload shaping) should operate on normalized listing records, not source-specific fields.

### Historical Sold/Rented Independence

Sold/rented history persistence and memorialization must remain independent from whichever active source is used.

This allows:
- stable comps and market-history analytics now
- unchanged analytics logic after VOW active-source swap

## Canonical Property Identity

Use a canonical property identity strategy so records can merge across sources:

- primary key candidates:
  - MLS listing ID (source-local)
  - normalized address key (cross-source helper)
- include source metadata and ingest timestamps for traceability.

When VOW arrives, map VOW listing identifiers into the same canonical model without breaking existing history/enrichment joins.

## Enrichment Strategy (Pre-VOW Priority)

Build enrichment as modular datasets that can be joined to normalized listings:

- schools:
  - district/school assignment
  - quality/ranking indicators
- healthcare:
  - nearest hospitals/clinics
  - travel-time or distance metrics
- finance:
  - rate provider abstraction:
    - current source: static/preset assumptions
    - future source: partner bank API

Each enrichment module should define:
- source of truth
- refresh cadence
- quality caveats/confidence
- join keys and fallbacks

## API and Product Surface Principles

- Keep API outputs explainable and client-safe.
- Expose reusable insight fields that support both:
  - property detail analysis UI
  - newsletter generation pipelines
- Prefer additive payload evolution so beta UI and future VOW UI can share response contracts.

## Operational Principles

- Continue daily active scraping and weekly sold/rented processing until VOW is available.
- Avoid introducing dependencies that assume VOW access.
- Keep scheduler and ingestion jobs source-agnostic where practical.

## Pre-VOW Enrichment Backlog (Recommended)

1. Define enrichment schemas and table contracts.
2. Add school-data ingestion + nearest-school metrics.
3. Add healthcare proximity ingestion + distance/travel metrics.
4. Add finance rate provider interface and swap-ready implementation.
5. Extend analytics API payloads with enrichment summary fields.
6. Add newsletter insight formatter based on shared analytics payloads.

## Future VOW Migration Checklist

1. Implement VOW active-listing adapter.
2. Map VOW fields/photos into normalized listing model.
3. Validate join continuity with sold/rented history and enrichment.
4. Run dual-source comparison period (scraper vs VOW) before cutover.
5. Cut over active source and retire scraper-only active path when stable.
