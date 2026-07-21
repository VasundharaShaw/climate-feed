"""Policy and analysis sources, via RSS.

Research literature and policy output arrive through completely different
plumbing. Journals have DOIs, metadata APIs and stable identifiers; think
tanks, NGOs and analysis desks publish to RSS and little else. Rather than
pretend otherwise, this module treats RSS as a first-class source and marks
everything it produces as kind='policy' so the site can distinguish it.

These records rarely have DOIs, so dedup falls back to normalised title and
URL. That is adequate here — the same briefing is seldom republished under a
different headline.

Feeds go stale. `python -m ingest.sources.policy --check` validates every
feed and reports which are dead, so a silent failure does not quietly turn
into a half-empty site.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from . import http
from ..normalise import block_key, title_key

# name -> (url, publisher label)
# Verified reachable at time of writing; run --check before trusting.
FEEDS: dict[str, tuple[str, str]] = {
    # Verified working on 2026-07-20.
    "carbonbrief":  ("https://www.carbonbrief.org/feed", "Carbon Brief"),
    "climatehome":  ("https://www.climatechangenews.com/feed/", "Climate Home News"),
    # Worked on 2026-07-20, returned 403 on 2026-07-21. Intermittent
    # user-agent blocking rather than a wrong URL, so it stays.
    "insideclimate": ("https://insideclimatenews.org/feed/", "Inside Climate News"),

    # Verified 2026-07-21.
    "grist":        ("https://grist.org/feed/", "Grist"),
    "conversation": ("https://theconversation.com/global/environment/articles.atom",
                     "The Conversation"),
    "carbonpulse":  ("https://carbon-pulse.com/feed/", "Carbon Pulse"),
}

NS = {"atom": "http://www.w3.org/2005/Atom",
      "dc": "http://purl.org/dc/elements/1.1/"}

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean(text: str | None, limit: int = 600) -> str | None:
    """RSS descriptions are HTML fragments. Strip to plain text."""
    if not text:
        return None
    s = _WS.sub(" ", _TAGS.sub(" ", text)).strip()
    return s[:limit] or None


def _parse_date(raw: str | None) -> str | None:
    """RSS uses RFC-822, Atom uses ISO-8601. Accept either, return ISO date."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _items(root: ET.Element):
    """Yield (title, link, summary, date_raw, author) for RSS or Atom."""
    rss1 = "{http://purl.org/rss/1.0/}"
    for item in list(root.iter("item")) + list(root.iter(rss1 + "item")):
        if item.tag.startswith(rss1):                    # RSS 1.0 / RDF
            yield (
                _text(item, rss1 + "title"), _text(item, rss1 + "link"),
                _text(item, rss1 + "description"),
                _text(item, "{http://purl.org/dc/elements/1.1/}date"),
                _text(item, "{http://purl.org/dc/elements/1.1/}creator"),
            )
            continue
    for item in root.iter("item"):                       # RSS 2.0
        yield (
            _text(item, "title"), _text(item, "link"),
            _text(item, "description") or _text(item, "{http://purl.org/rss/1.0/modules/content/}encoded"),
            _text(item, "pubDate"),
            _text(item, "{http://purl.org/dc/elements/1.1/}creator"),
        )
    for entry in root.findall("atom:entry", NS):         # Atom
        link = entry.find("atom:link", NS)
        yield (
            _text(entry, "atom:title", NS),
            link.get("href") if link is not None else None,
            _text(entry, "atom:summary", NS) or _text(entry, "atom:content", NS),
            _text(entry, "atom:updated", NS) or _text(entry, "atom:published", NS),
            _text(entry, "atom:author/atom:name", NS),
        )


def _text(el: ET.Element, path: str, ns: dict | None = None) -> str | None:
    node = el.find(path, ns) if ns else el.find(path)
    return node.text.strip() if node is not None and node.text else None


def fetch(watermark: str | None = None, feeds: dict | None = None):
    """Yield normalised policy records newer than `watermark` (ISO date)."""
    feeds = feeds or FEEDS
    today = datetime.now(timezone.utc).date().isoformat()

    for key, (url, publisher) in feeds.items():
        try:
            resp = http.get(url)
            root = ET.fromstring(resp.content)
        except Exception as exc:                          # noqa: BLE001
            # One dead feed must not take the others down.
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
                "sources": json.dumps([f"rss:{key}"]),
                "kind": "policy",
                "topics": json.dumps([]),
            }
            n += 1
        print(f"  · {key}: {n} items")


def check() -> int:
    """Validate every feed. Returns count of failures."""
    bad = 0
    print(f"Checking {len(FEEDS)} feeds...\n")
    for key, (url, publisher) in FEEDS.items():
        try:
            resp = http.get(url, timeout=20)
            root = ET.fromstring(resp.content)
            items = list(_items(root))
            dates = [_parse_date(d) for *_, d, _a in items]
            newest = max((d for d in dates if d), default="?")
            if not items:
                print(f"  EMPTY  {key:<18} {publisher} — parsed but no items")
                bad += 1
            else:
                print(f"  ok     {key:<18} {len(items):>3} items, newest {newest}")
        except Exception as exc:                          # noqa: BLE001
            print(f"  DEAD   {key:<18} {type(exc).__name__}: {str(exc)[:60]}")
            bad += 1
    print(f"\n{len(FEEDS) - bad}/{len(FEEDS)} feeds healthy")
    if bad:
        print("Remove or replace the dead ones in ingest/sources/policy.py")
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if check() else 0)
