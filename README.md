# climate-feed

Daily aggregation of climate science research and policy documents.

## Design constraints

Built to run on free-tier infrastructure with a minimal footprint:

- **No servers.** One scheduled GitHub Action per day; static output on
  Cloudflare Pages. Nothing draws power between runs.
- **Incremental by default.** Every source is watermarked. A steady-state
  run makes tens of requests, not thousands.
- **Minimal payloads.** OpenAlex `select=` cuts per-record transfer by ~90%.
- **SQLite as the artefact.** The database is committed, so the corpus is
  versioned and citable, and there is no database server.
- **Measured, not asserted.** Each run records request count, bytes
  transferred, and an estimated CO2e in the `runs` table.

## Layout

    schema.sql              tables, FTS5 index, source watermarks
    ingest/normalise.py     DOI/arXiv/title normalisation + dedup rules
    ingest/db.py            upsert-with-merge semantics
    ingest/http.py          shared session, rate limiting, byte accounting
    ingest/sources/         one module per source
    ingest/run.py           orchestrator

## Usage

    pip install -r requirements.txt
    python -m ingest.run --dry-run          # no writes
    python -m ingest.run                    # incremental
    python -m ingest.run --since 2026-01-01 --source openalex

## Deduplication

A preprint and its published version must collapse to one row. Tests run
cheapest-first: normalised DOI, then arXiv id, then normalised title, then
(first-author surname + year) blocking with a 0.75 Jaccard threshold on
title tokens. When versions merge, a placeholder venue like "arXiv" is
upgraded to the real journal name; other populated fields are never
clobbered.

## Not yet built

- Classifier (keyword prefilter -> embedding similarity -> LLM on the
  uncertain band only)
- Policy sources (Climate Policy Radar bulk dataset, UNFCCC, EEA)
- `site_build` static renderer
