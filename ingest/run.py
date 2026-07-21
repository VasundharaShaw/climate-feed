"""Daily run entrypoint.

    python -m ingest.run                 # incremental, all sources
    python -m ingest.run --dry-run       # no writes
    python -m ingest.run --source arxiv  # one source

Each source is isolated: a failure in one is logged and the others still
run. The process exits non-zero if any source failed, so CI still reports
red — degraded, but not silently.
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from collections import Counter

from . import db, http
from .classify import classify_record
from .sources import arxiv, de_policy, openalex, policy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest")

# --- emissions coefficients ------------------------------------------
# Both are assumptions. The byte count they multiply is measured; these are
# not. Cite them, state their year and boundary, and do not present the
# product as a measurement.
#
# Aslan, J., Mayers, K., Koomey, J.G. & France, C. (2018). "Electricity
# Intensity of Internet Data Transmission: Untangling the Estimates."
# Journal of Industrial Ecology 22(4), 785-798. doi:10.1111/jiec.12630
#
# Their headline estimate is 0.06 kWh/GB for 2015, covering core and
# fixed-line access networks only -- not data centres, not end-user
# devices. Two caveats matter:
#
#   1. The same paper finds intensity has halved roughly every two years
#      since 2000 in developed countries. Applied unadjusted a decade
#      later, 0.06 is therefore an over-estimate, probably by an order of
#      magnitude. It is kept here as a deliberately conservative upper
#      bound rather than a best estimate.
#   2. Published estimates for this quantity span several orders of
#      magnitude depending on where the system boundary is drawn.
KWH_PER_GB = 0.06

# European Environment Agency, greenhouse gas emission intensity of
# electricity generation. The EU-27 average was about 230 gCO2e/kWh in 2020
# and has fallen since, so 250 is slightly high for the EU today.
# https://www.eea.europa.eu/en/analysis/indicators/greenhouse-gas-emission-intensity-of-1
#
# The average also conceals an enormous spread -- Poland was near 700
# gCO2e/kWh in 2020, Sweden and Norway near zero -- and this build runs on
# GitHub-hosted infrastructure whose location is not disclosed. Treat this
# as a placeholder for a figure that should really be measured.
GRID_INTENSITY = 250.0   # gCO2e/kWh


def run_openalex(conn, counts, args) -> None:
    state = db.get_state(conn, "openalex")
    since = args.since or (state["watermark"] if state else None)
    newest = since
    n = 0
    for rec in openalex.fetch(since=since):
        counts[db.upsert(conn, classify_record(rec))] += 1
        n += 1
        if rec["published_date"] and (not newest or rec["published_date"] > newest):
            newest = rec["published_date"]
    log.info("openalex: %d records processed", n)
    if not args.dry_run:
        db.set_state(conn, "openalex", watermark=newest)


def run_arxiv(conn, counts, args) -> None:
    state = db.get_state(conn, "arxiv")
    watermark = state["watermark"] if state else None
    newest = watermark
    n = 0
    for rec in arxiv.fetch(watermark=watermark):
        raw = rec.pop("_published_raw", None)
        counts[db.upsert(conn, classify_record(rec))] += 1
        n += 1
        if raw and (not newest or raw > newest):
            newest = raw
    log.info("arxiv: %d records processed", n)
    if not args.dry_run:
        db.set_state(conn, "arxiv", watermark=newest)


def run_de_policy(conn, counts, args) -> None:
    """German agencies, advisory councils, institutes and free journalism."""
    state = db.get_state(conn, "de_policy")
    watermark = state["watermark"] if state else None
    newest = watermark
    n = 0
    for rec in de_policy.fetch(watermark=watermark):
        counts[db.upsert(conn, classify_record(rec))] += 1
        n += 1
        d = rec["published_date"]
        if d and (not newest or d > newest):
            newest = d
    log.info("de_policy: %d records processed", n)
    if not args.dry_run:
        db.set_state(conn, "de_policy", watermark=newest)


def run_policy(conn, counts, args) -> None:
    """RSS feeds from analysis desks, think tanks and agencies."""
    state = db.get_state(conn, "policy")
    watermark = state["watermark"] if state else None
    newest = watermark
    n = 0
    for rec in policy.fetch(watermark=watermark):
        counts[db.upsert(conn, classify_record(rec))] += 1
        n += 1
        d = rec["published_date"]
        if d and (not newest or d > newest):
            newest = d
    log.info("policy: %d records processed", n)
    if not args.dry_run:
        db.set_state(conn, "policy", watermark=newest)


RUNNERS = {"openalex": run_openalex, "arxiv": run_arxiv,
           "policy": run_policy, "de_policy": run_de_policy}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO date override for OpenAlex")
    ap.add_argument("--source", choices=list(RUNNERS), action="append")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = args.source or list(RUNNERS)
    conn = db.connect()
    counts = Counter()
    failures = {}

    run_id = conn.execute(
        "INSERT INTO runs (started_at) VALUES (?)", (db.now(),)
    ).lastrowid

    for name in sources:
        log.info("--- %s ---", name)
        try:
            RUNNERS[name](conn, counts, args)
        except Exception as exc:                       # noqa: BLE001
            # Deliberately broad: one flaky upstream must not cost us the
            # others. The traceback is preserved for the log.
            failures[name] = exc
            log.error("%s failed: %s", name, exc)
            log.debug("%s", traceback.format_exc())
            conn.commit()   # keep whatever that source did manage

    gb = http.stats["bytes"] / 1e9
    kwh = gb * KWH_PER_GB
    conn.execute(
        """UPDATE runs SET finished_at = ?, http_requests = ?, bytes_in = ?,
           new_works = ?, merged_works = ?, energy_kwh = ?, co2e_g = ?
           WHERE id = ?""",
        (db.now(), http.stats["requests"], http.stats["bytes"],
         counts["new"], counts["merged"], kwh, kwh * GRID_INTENSITY, run_id),
    )

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()

    log.info(
        "new=%d merged=%d unchanged=%d | requests=%d retries=%d "
        "transferred=%.1f MB co2e=%.2f g",
        counts["new"], counts["merged"], counts["unchanged"],
        http.stats["requests"], http.stats["retries"],
        http.stats["bytes"] / 1e6, kwh * GRID_INTENSITY,
    )

    if failures:
        log.error("failed sources: %s", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
