"""OpenAlex ingest.

Two things here are doing the low-carbon work:

  `select=`  — OpenAlex returns a ~15 kB object per work by default. We ask
               for nine fields and get ~1.5 kB. Across ~2000 works/day that
               is the difference between 30 MB and 3 MB transferred.

  `cursor=`  — cursor pagination instead of `page=`, so the server does a
               keyset scan rather than an offset scan. Cheaper for them,
               and it does not break past 10,000 results.

Filtering uses `from_created_date`, not `from_publication_date`: we want
records that entered the index since our last run, regardless of the date
printed on the paper. Backfilled records would otherwise be missed forever.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from . import http
from ..normalise import block_key, norm_doi, norm_openalex, title_key

BASE = "https://api.openalex.org/works"

SELECT = ",".join([
    "id", "doi", "title", "publication_date", "primary_location",
    "authorships", "abstract_inverted_index", "topics", "open_access",
])

# OpenAlex topic IDs. Deliberately broad at this stage — the classifier
# narrows later. Verify these periodically; OpenAlex renumbers topics.
CLIMATE_TOPICS = [
    "T10024",  # Climate variability and change
    "T10173",  # Climate change impacts on agriculture
    "T10248",  # Atmospheric aerosols and clouds
    "T10444",  # Carbon capture and storage
    "T11463",  # Climate policy and governance
    "T10105",  # Oceanography and sea level
    "T10851",  # Glaciers and ice sheets
]


def _deinvert(inv: dict | None) -> str | None:
    """OpenAlex stores abstracts as an inverted index to dodge copyright."""
    if not inv:
        return None
    positions = [(pos, word) for word, ps in inv.items() for pos in ps]
    positions.sort()
    return " ".join(w for _, w in positions)


def fetch(since: str | None = None, max_pages: int = 25):
    """Yield normalised records created on or after `since` (ISO date)."""
    since = since or (date.today() - timedelta(days=2)).isoformat()

    filters = f"from_created_date:{since},topics.id:{'|'.join(CLIMATE_TOPICS)}"
    cursor, pages = "*", 0

    while cursor and pages < max_pages:
        resp = http.get(BASE, params={
            "filter": filters,
            "select": SELECT,
            "per-page": 200,
            "cursor": cursor,
            "mailto": "you@example.org",   # polite pool: faster, higher limits
        })
        payload = resp.json()

        for w in payload.get("results", []):
            rec = _to_record(w)
            if rec:
                yield rec

        cursor = payload.get("meta", {}).get("next_cursor")
        pages += 1


def _to_record(w: dict) -> dict | None:
    title = (w.get("title") or "").strip()
    if not title:
        return None

    authors = [
        a["author"]["display_name"]
        for a in w.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    oa = w.get("open_access") or {}
    pub_date = w.get("publication_date")

    return {
        "doi": norm_doi(w.get("doi")),
        "arxiv_id": None,
        "openalex_id": norm_openalex(w.get("id")),
        "title": title,
        "title_key": title_key(title),
        "block_key": block_key(authors, pub_date),
        "abstract": _deinvert(w.get("abstract_inverted_index")),
        "authors": json.dumps(authors),
        "venue": src.get("display_name"),
        "published_date": pub_date,
        "url": loc.get("landing_page_url") or w.get("id"),
        "pdf_url": loc.get("pdf_url"),
        "is_oa": int(bool(oa.get("is_oa"))),
        "sources": json.dumps(["openalex"]),
        "kind": "research",
        "topics": json.dumps([t.get("display_name") for t in w.get("topics", [])]),
    }
