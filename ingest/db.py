"""SQLite access layer.

Upsert semantics matter here: when the published version of a preprint
arrives, we want to *enrich* the existing row (add the DOI, the journal,
the final date) rather than overwrite good data with nulls.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .normalise import find_duplicate

# Resolved at call time, not import time, so it stays overridable
# (tests, a separate dev database, a different checkout layout).
DB_PATH = Path(os.environ.get("FEED_DB", "data/feed.db"))
SCHEMA_PATH = Path("schema.sql")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


# Fields where a non-empty incoming value fills a null but never clobbers
# an existing non-null.
_MERGE_FIELDS = (
    "doi", "arxiv_id", "openalex_id", "abstract", "authors",
    "venue", "url", "pdf_url", "published_date",
)

# Placeholder venues that a real journal name is allowed to overwrite.
# Without this, a paper that started life on arXiv is still labelled
# "arXiv" months after it appears in ACP.
_PLACEHOLDER_VENUES = {"arxiv", "earth arxiv", "eartharxiv", "essoar",
                       "ess open archive", "preprint", "research square",
                       "egusphere", "biorxiv", "ssrn"}


def upsert(conn: sqlite3.Connection, rec: dict) -> str:
    """Insert or merge one record. Returns 'new' | 'merged' | 'unchanged'."""
    existing_id = find_duplicate(conn, rec)
    cur = conn.cursor()

    if existing_id is None:
        cur.execute(
            """INSERT INTO works
               (doi, arxiv_id, openalex_id, title_key, block_key, title,
                abstract, authors, venue, published_date, url, pdf_url,
                is_oa, sources, kind, topics, first_seen, last_updated)
               VALUES (:doi, :arxiv_id, :openalex_id, :title_key, :block_key,
                       :title, :abstract, :authors, :venue, :published_date,
                       :url, :pdf_url, :is_oa, :sources, :kind, :topics,
                       :first_seen, :last_updated)""",
            {**_defaults(rec), "first_seen": now(), "last_updated": now()},
        )
        return "new"

    old = cur.execute("SELECT * FROM works WHERE id = ?", (existing_id,)).fetchone()
    updates, params = [], {}
    for f in _MERGE_FIELDS:
        incoming = rec.get(f)
        if not incoming:
            continue
        current = old[f]
        fills_null = not current
        upgrades_venue = (
            f == "venue"
            and current
            and current.strip().lower() in _PLACEHOLDER_VENUES
            and incoming.strip().lower() not in _PLACEHOLDER_VENUES
        )
        if fills_null or upgrades_venue:
            updates.append(f"{f} = :{f}")
            params[f] = incoming

    # Union the provenance list.
    old_sources = set(json.loads(old["sources"]))
    new_sources = old_sources | set(json.loads(rec.get("sources") or "[]"))
    if new_sources != old_sources:
        updates.append("sources = :sources")
        params["sources"] = json.dumps(sorted(new_sources))

    if not updates:
        return "unchanged"

    params["id"] = existing_id
    params["last_updated"] = now()
    updates.append("last_updated = :last_updated")
    cur.execute(f"UPDATE works SET {', '.join(updates)} WHERE id = :id", params)
    return "merged"


def _defaults(rec: dict) -> dict:
    keys = ("doi", "arxiv_id", "openalex_id", "title_key", "block_key", "title",
            "abstract", "authors", "venue", "published_date", "url", "pdf_url",
            "is_oa", "sources", "kind", "topics")
    return {k: rec.get(k) for k in keys}


def get_state(conn, source: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM source_state WHERE source = ?", (source,)
    ).fetchone()


def set_state(conn, source: str, **kw) -> None:
    cols = {"last_run": now(), **kw}
    placeholders = ", ".join(f"{k} = :{k}" for k in cols)
    conn.execute(
        f"""INSERT INTO source_state (source, {', '.join(cols)})
            VALUES (:source, {', '.join(':' + k for k in cols)})
            ON CONFLICT(source) DO UPDATE SET {placeholders}""",
        {"source": source, **cols},
    )
