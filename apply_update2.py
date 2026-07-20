#!/usr/bin/env python3
"""Update 2: policy sources, date sanity, classifier trust fix.

    python3 apply_update2.py

Adds ingest/sources/policy.py (8 RSS feeds), stops future-dated records
polluting the feed, and stops the classifier blanket-trusting OpenALex.
Idempotent. Run from the repo root.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
changed = []


def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.read_text() == text:
        print(f"  = {rel} (unchanged)")
        return
    p.write_text(text)
    changed.append(rel)
    print(f"  + {rel}")


def patch(rel, old, new, label):
    p = ROOT / rel
    if not p.exists():
        sys.exit(f"ERROR: {rel} not found. Run from the repo root.")
    s = p.read_text()
    if new in s:
        print(f"  = {rel}: {label} (already applied)")
        return
    if old not in s:
        sys.exit(f"ERROR: anchor not found in {rel} for: {label}")
    p.write_text(s.replace(old, new, 1))
    changed.append(rel)
    print(f"  ~ {rel}: {label}")


POLICY = '"""Policy and analysis sources, via RSS.\n\nResearch literature and policy output arrive through completely different\nplumbing. Journals have DOIs, metadata APIs and stable identifiers; think\ntanks, NGOs and analysis desks publish to RSS and little else. Rather than\npretend otherwise, this module treats RSS as a first-class source and marks\neverything it produces as kind=\'policy\' so the site can distinguish it.\n\nThese records rarely have DOIs, so dedup falls back to normalised title and\nURL. That is adequate here — the same briefing is seldom republished under a\ndifferent headline.\n\nFeeds go stale. `python -m ingest.sources.policy --check` validates every\nfeed and reports which are dead, so a silent failure does not quietly turn\ninto a half-empty site.\n"""\n\nfrom __future__ import annotations\n\nimport json\nimport re\nimport xml.etree.ElementTree as ET\nfrom datetime import datetime, timezone\nfrom email.utils import parsedate_to_datetime\n\nfrom . import http\nfrom ..normalise import block_key, title_key\n\n# name -> (url, publisher label)\n# Verified reachable at time of writing; run --check before trusting.\nFEEDS: dict[str, tuple[str, str]] = {\n    "carbonbrief":    ("https://www.carbonbrief.org/feed", "Carbon Brief"),\n    "climatehome":    ("https://www.climatechangenews.com/feed/", "Climate Home News"),\n    "insideclimate":  ("https://insideclimatenews.org/feed/", "Inside Climate News"),\n    "climateanalytics": ("https://climateanalytics.org/feed", "Climate Analytics"),\n    "grantham_lse":   ("https://www.lse.ac.uk/granthaminstitute/feed/", "Grantham Institute (LSE)"),\n    "wri":            ("https://www.wri.org/rss.xml", "World Resources Institute"),\n    "iisd_enb":       ("https://enb.iisd.org/feed", "IISD Earth Negotiations Bulletin"),\n    "eea":            ("https://www.eea.europa.eu/en/newsroom/news/RSS", "European Environment Agency"),\n}\n\nNS = {"atom": "http://www.w3.org/2005/Atom",\n      "dc": "http://purl.org/dc/elements/1.1/"}\n\n_TAGS = re.compile(r"<[^>]+>")\n_WS = re.compile(r"\\s+")\n\n\ndef _clean(text: str | None, limit: int = 600) -> str | None:\n    """RSS descriptions are HTML fragments. Strip to plain text."""\n    if not text:\n        return None\n    s = _WS.sub(" ", _TAGS.sub(" ", text)).strip()\n    return s[:limit] or None\n\n\ndef _parse_date(raw: str | None) -> str | None:\n    """RSS uses RFC-822, Atom uses ISO-8601. Accept either, return ISO date."""\n    if not raw:\n        return None\n    raw = raw.strip()\n    try:\n        return parsedate_to_datetime(raw).date().isoformat()\n    except (TypeError, ValueError):\n        pass\n    try:\n        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()\n    except ValueError:\n        return None\n\n\ndef _items(root: ET.Element):\n    """Yield (title, link, summary, date_raw, author) for RSS or Atom."""\n    for item in root.iter("item"):                       # RSS 2.0\n        yield (\n            _text(item, "title"), _text(item, "link"),\n            _text(item, "description") or _text(item, "{http://purl.org/rss/1.0/modules/content/}encoded"),\n            _text(item, "pubDate"),\n            _text(item, "{http://purl.org/dc/elements/1.1/}creator"),\n        )\n    for entry in root.findall("atom:entry", NS):         # Atom\n        link = entry.find("atom:link", NS)\n        yield (\n            _text(entry, "atom:title", NS),\n            link.get("href") if link is not None else None,\n            _text(entry, "atom:summary", NS) or _text(entry, "atom:content", NS),\n            _text(entry, "atom:updated", NS) or _text(entry, "atom:published", NS),\n            _text(entry, "atom:author/atom:name", NS),\n        )\n\n\ndef _text(el: ET.Element, path: str, ns: dict | None = None) -> str | None:\n    node = el.find(path, ns) if ns else el.find(path)\n    return node.text.strip() if node is not None and node.text else None\n\n\ndef fetch(watermark: str | None = None, feeds: dict | None = None):\n    """Yield normalised policy records newer than `watermark` (ISO date)."""\n    feeds = feeds or FEEDS\n    today = datetime.now(timezone.utc).date().isoformat()\n\n    for key, (url, publisher) in feeds.items():\n        try:\n            resp = http.get(url)\n            root = ET.fromstring(resp.content)\n        except Exception as exc:                          # noqa: BLE001\n            # One dead feed must not take the others down.\n            print(f"  ! {key}: {type(exc).__name__}: {exc}")\n            continue\n\n        n = 0\n        for title, link, summary, date_raw, author in _items(root):\n            if not title or not link:\n                continue\n            date = _parse_date(date_raw)\n            if date and date > today:      # never trust a future date\n                date = today\n            if watermark and date and date <= watermark:\n                continue\n\n            authors = [author] if author else []\n            yield {\n                "doi": None, "arxiv_id": None, "openalex_id": None,\n                "title": title,\n                "title_key": title_key(title),\n                "block_key": block_key(authors, date),\n                "abstract": _clean(summary),\n                "authors": json.dumps(authors),\n                "venue": publisher,\n                "published_date": date,\n                "url": link,\n                "pdf_url": None,\n                "is_oa": 1,\n                "sources": json.dumps([f"rss:{key}"]),\n                "kind": "policy",\n                "topics": json.dumps([]),\n            }\n            n += 1\n        print(f"  · {key}: {n} items")\n\n\ndef check() -> int:\n    """Validate every feed. Returns count of failures."""\n    bad = 0\n    print(f"Checking {len(FEEDS)} feeds...\\n")\n    for key, (url, publisher) in FEEDS.items():\n        try:\n            resp = http.get(url, timeout=20)\n            root = ET.fromstring(resp.content)\n            items = list(_items(root))\n            dates = [_parse_date(d) for *_, d, _a in items]\n            newest = max((d for d in dates if d), default="?")\n            if not items:\n                print(f"  EMPTY  {key:<18} {publisher} — parsed but no items")\n                bad += 1\n            else:\n                print(f"  ok     {key:<18} {len(items):>3} items, newest {newest}")\n        except Exception as exc:                          # noqa: BLE001\n            print(f"  DEAD   {key:<18} {type(exc).__name__}: {str(exc)[:60]}")\n            bad += 1\n    print(f"\\n{len(FEEDS) - bad}/{len(FEEDS)} feeds healthy")\n    if bad:\n        print("Remove or replace the dead ones in ingest/sources/policy.py")\n    return bad\n\n\nif __name__ == "__main__":\n    raise SystemExit(1 if check() else 0)\n'

print("Applying update 2...")
write("ingest/sources/policy.py", POLICY)

# --- 1. classifier: stop blanket-trusting OpenAlex ---------------------
# The topic filter is OR'd across seven topics, so weak matches leak in.
# A pre-filter is evidence, not proof: give it a boost, not a veto.
patch("ingest/classify.py",
      '''def classify_record(rec: dict) -> dict:
    """Attach score and tier. OpenAlex arrives topic-filtered already."""
    pre_filtered = "openalex" in (rec.get("sources") or "")
    s, tier, _ = score(rec.get("title"), rec.get("abstract"), rec.get("topics"))
    if pre_filtered:
        tier = "accept" if tier != "reject" else "uncertain"
    rec["score"] = s
    rec["tier"] = tier
    return rec''',
      '''# Arriving via a topic-filtered query is evidence, not proof. OpenAlex
# ORs seven topic IDs, so a work with one weak climate topic gets through;
# that is how a treatise on Damascius reached the feed. Boost the score,
# never override a reject.
PREFILTER_BONUS = 1.5


def classify_record(rec: dict) -> dict:
    """Attach score and tier."""
    s, _tier, _hits = score(rec.get("title"), rec.get("abstract"),
                            rec.get("topics"))
    # Only boost when the text itself corroborates. With no lexical signal
    # at all the topic match was spurious, and boosting it is how a
    # Neoplatonist treatise ends up on a climate site.
    if s > 0 and "openalex" in (rec.get("sources") or ""):
        s += PREFILTER_BONUS
    rec["score"] = round(s, 2)
    rec["tier"] = ("accept" if s >= ACCEPT else
                   "uncertain" if s >= UNCERTAIN else "reject")
    return rec''',
      "no blanket trust for OpenAlex")

# --- 2. site: never show future-dated records --------------------------
patch("site_build/__main__.py",
      '''           WHERE tier IN ('accept','uncertain') AND published_date IS NOT NULL
           ORDER BY published_date DESC, score DESC"""
    ).fetchall()

    total_all''',
      '''           WHERE tier IN ('accept','uncertain')
             AND published_date IS NOT NULL
             AND published_date <= date('now')
           ORDER BY published_date DESC, score DESC"""
    ).fetchall()

    total_all''',
      "exclude future dates")

# --- 3. run.py: wire in the policy source ------------------------------
patch("ingest/run.py",
      "from .sources import arxiv, openalex",
      "from .sources import arxiv, openalex, policy",
      "import policy source")

patch("ingest/run.py",
      '''RUNNERS = {"openalex": run_openalex, "arxiv": run_arxiv}''',
      '''def run_policy(conn, counts, args) -> None:
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


RUNNERS = {"openalex": run_openalex, "arxiv": run_arxiv, "policy": run_policy}''',
      "add policy runner")

print()
print(f"Changed {len(set(changed))} files." if changed else "Already up to date.")
print("""
Next:
  1. python3 -m ingest.sources.policy      # check which feeds are alive
  2. python3 backfill_scores.py            # re-score with the fixed logic
  3. python -m ingest.run --source policy  # pull policy documents
  4. python -m site_build && open public/index.html
""")
