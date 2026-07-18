"""Daily run entrypoint.

    python -m ingest.run              # incremental, both sources
    python -m ingest.run --since 2026-01-01 --source openalex

Designed to be idempotent: running it twice in a day costs a handful of
requests and inserts nothing.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from . import db, http
from .sources import arxiv, openalex

# gCO2e per kWh. European grid average; adjust to your runner's region.
GRID_INTENSITY = 250.0
# Rough energy cost of moving a GB across the network, kWh/GB.
KWH_PER_GB = 0.06


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO date override for OpenAlex")
    ap.add_argument("--source", choices=["openalex", "arxiv"], action="append")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = args.source or ["openalex", "arxiv"]
    conn = db.connect()
    counts = Counter()

    run_id = conn.execute(
        "INSERT INTO runs (started_at) VALUES (?)", (db.now(),)
    ).lastrowid

    if "openalex" in sources:
        state = db.get_state(conn, "openalex")
        since = args.since or (state["watermark"] if state else None)
        newest = since
        for rec in openalex.fetch(since=since):
            counts[db.upsert(conn, rec)] += 1
            if rec["published_date"] and (not newest or rec["published_date"] > newest):
                newest = rec["published_date"]
        if not args.dry_run:
            db.set_state(conn, "openalex", watermark=newest)

    if "arxiv" in sources:
        state = db.get_state(conn, "arxiv")
        watermark = state["watermark"] if state else None
        newest = watermark
        for rec in arxiv.fetch(watermark=watermark):
            raw = rec.pop("_published_raw", None)
            counts[db.upsert(conn, rec)] += 1
            if raw and (not newest or raw > newest):
                newest = raw
        if not args.dry_run:
            db.set_state(conn, "arxiv", watermark=newest)

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

    print(
        f"new={counts['new']} merged={counts['merged']} "
        f"unchanged={counts['unchanged']} "
        f"requests={http.stats['requests']} "
        f"transferred={http.stats['bytes'] / 1e6:.1f} MB "
        f"co2e={kwh * GRID_INTENSITY:.2f} g"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
