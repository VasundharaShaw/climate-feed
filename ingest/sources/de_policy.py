"""German climate policy sources.

Separate from ``policy.py`` because the audience differs: that module tracks
anglophone climate journalism, this one tracks German institutions whose
output feeds domestic policy debate.

There is no single database of German climate policy documents. The
professional briefings that come closest -- Table.Media, Tagesspiegel
Background -- are paywalled and cannot be aggregated here. What follows is
the free, machine-readable subset: agencies, advisory councils, research
institutes, NGOs, and journalism that is openly readable.

IMPORTANT: the outlets below were checked and are free to read. The feed
URLs are conventional guesses and have NOT been verified. Check them before
trusting any of them:

    python -m ingest.sources.de_policy

Prune whatever fails. A dead feed costs a failed request every day forever.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import http
from . policy import _clean, _items, _parse_date
from ..normalise import block_key, title_key

# name -> (url, publisher, kind_of_body)
# name -> (url, publisher, body_type, curated)
#
# curated=True means everything the publisher puts out is climate or energy
# work, so the lexicon is not asked to prove it. False means the feed is
# broader than climate and still needs filtering.
#
# Checked live 2026-07-21. Only four survived; the rest 404'd, and the
# agency URLs in particular were my guesses at Government Site Builder
# conventions that do not hold.
FEEDS: dict[str, tuple[str, str, str, bool]] = {
    # --- verified working ---
    "ariadne": ("https://ariadneprojekt.de/feed/",
                "Kopernikus-Projekt Ariadne", "institute", True),
    "germanwatch": ("https://www.germanwatch.org/de/rss.xml",
                    "Germanwatch", "ngo", False),
    "clew": ("https://www.cleanenergywire.org/rss.xml",
             "Clean Energy Wire", "journalism", True),

    # Parses, but the newest item was from 2024 -- the feed is stale or the
    # section slug has moved. Left in so the next check re-tests it; drop it
    # if it is still two years behind.
    "taz_oeko": ("https://taz.de/!s=oeko;rss/", "taz", "journalism", False),

    # --- unresolved, worth finding the real URL for ---
    # These outlets matter and publish openly; only my URLs were wrong.
    # UBA, PIK, Agora, Öko-Institut, MCC, DIW, Wuppertal, DUH, SRU, DWD,
    # BMUV, BMWK and klimareporter all 404'd or returned malformed XML.
    # The reliable way to find each is to open the site and look for the
    # feed <link rel="alternate" type="application/rss+xml"> in the page
    # source, rather than guessing a path.
}


def fetch(watermark: str | None = None, feeds: dict | None = None):
    """Yield German policy records newer than `watermark` (ISO date).

    Tagged region='de' so the site can present them separately without
    having to guess from the publisher name."""
    feeds = feeds or FEEDS
    today = datetime.now(timezone.utc).date().isoformat()

    for key, (url, publisher, body, curated) in feeds.items():
        try:
            resp = http.get(url)
            root = ET.fromstring(resp.content)
        except Exception as exc:                          # noqa: BLE001
            # One dead feed must not take the other eighteen down.
            print(f"  ! {key}: {type(exc).__name__}: {exc}")
            continue

        n = 0
        for title, link, summary, date_raw, author in _items(root):
            if not title or not link:
                continue
            date = _parse_date(date_raw)
            if date and date > today:      # never trust a future date
                date = today
            if watermark and date and date <= watermark:
                continue

            authors = [author] if author else []
            yield {
                "doi": None, "arxiv_id": None, "openalex_id": None,
                "title": title,
                "title_key": title_key(title),
                "block_key": block_key(authors, date),
                "abstract": _clean(summary),
                "authors": json.dumps(authors),
                "venue": publisher,
                "published_date": date,
                "url": link,
                "pdf_url": None,
                "is_oa": 1,
                "sources": json.dumps([f"de:{key}"]),
                "kind": "policy",
                "region": "de",
                "curated": curated,
                "topics": json.dumps([]),
            }
            n += 1
        print(f"  \u00b7 {key}: {n} items")


def check() -> int:
    """Fetch every feed once and report. Run before adding a source, and
    again whenever the daily run starts logging failures."""
    ok = dead = 0
    print(f"Checking {len(FEEDS)} feeds...\n")
    for key, (url, publisher, body, curated) in FEEDS.items():
        try:
            resp = http.get(url)
            root = ET.fromstring(resp.content)
            items = list(_items(root))
            dates = [_parse_date(d) for _, _, _, d, _ in items]
            newest = max((d for d in dates if d), default=None)
        except Exception as exc:                          # noqa: BLE001
            print(f"  DEAD  {key:<16} {type(exc).__name__}: {exc}")
            dead += 1
            continue
        if not items:
            print(f"  EMPTY {key:<16} parsed, no items -- wrong URL?")
            dead += 1
        else:
            print(f"  ok    {key:<16} {len(items):>3} items, "
                  f"newest {newest or '?'}   {publisher}")
            ok += 1
    print(f"\n{ok} healthy, {dead} to remove.")
    return 0 if dead == 0 else 1


if __name__ == "__main__":
    raise SystemExit(check())
