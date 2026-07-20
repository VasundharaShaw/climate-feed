#!/usr/bin/env python3
"""Apply the website + classifier update.

    python3 apply_update.py

Writes ingest/classify.py and site_build/__main__.py, and patches
ingest/db.py and ingest/run.py so every record is scored on the way in.
Idempotent: safe to run twice. Prints what it changed.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent
changed: list[str] = []


def write(rel: str, text: str) -> None:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.read_text() == text:
        print(f"  = {rel} (unchanged)")
        return
    p.write_text(text)
    changed.append(rel)
    print(f"  + {rel}")


def patch(rel: str, old: str, new: str, label: str) -> None:
    p = ROOT / rel
    if not p.exists():
        sys.exit(f"ERROR: {rel} not found. Run this from the repo root.")
    s = p.read_text()
    if new in s:
        print(f"  = {rel}: {label} (already applied)")
        return
    if old not in s:
        sys.exit(f"ERROR: could not find anchor in {rel} for: {label}")
    p.write_text(s.replace(old, new, 1))
    changed.append(rel)
    print(f"  ~ {rel}: {label}")


CLASSIFY = '''"""Is this work actually about climate?

Tier 1 of the three-tier filter: a weighted lexicon over title and
abstract. Cheap, deterministic, no API calls, no model weights. It catches
the obvious yes and the obvious no, and hands the rest to a later
embedding/LLM stage rather than guessing.

Why this is needed: arXiv has no climate category. We pull whole
categories (econ.GN, q-bio.PE, physics.soc-ph) that mix climate work with
everything else, so an unfiltered feed surfaces thoroughbred injury
studies and Neoplatonist philosophy next to heatwave dynamics. OpenAlex
records arrive pre-filtered by topic ID and are trusted accordingly.

Scoring is asymmetric on purpose. A CORE term is close to decisive; a
CONTEXT term only counts alongside something else, because "adaptation",
"emissions" and "resilience" are common far outside climate work.
"""

from __future__ import annotations

import json
import re

CORE = {
    "climate change": 3.0, "global warming": 3.0, "climate model": 3.0,
    "greenhouse gas": 2.5, "carbon cycle": 2.5, "climate policy": 3.0,
    "sea level rise": 3.0, "ocean acidification": 3.0, "paris agreement": 3.0,
    "ipcc": 3.0, "unfccc": 3.0, "climate variability": 2.5,
    "radiative forcing": 2.5, "climate sensitivity": 3.0, "cmip": 2.5,
    "decarboni": 2.5, "net zero": 2.5, "carbon budget": 2.5,
    "climate risk": 2.5, "climate adaptation": 3.0, "climate mitigation": 3.0,
    "extreme weather": 2.5, "heatwave": 2.0, "drought": 1.5,
    "permafrost": 2.5, "ice sheet": 2.5, "sea ice": 2.5, "glacier": 2.0,
    "monsoon": 1.5, "el nino": 2.0, "el ni\\u00f1o": 2.0, "enso": 1.5,
    "atmospheric co2": 2.5, "carbon dioxide removal": 2.5,
    "climate finance": 2.5, "emission scenario": 2.5, "ssp": 1.0,
    "anthropogenic warming": 3.0, "climate justice": 3.0,
    "tipping point": 1.5, "aerosol forcing": 2.5, "teleconnection": 1.5,
    "paleoclimate": 3.0, "climate projection": 3.0, "carbon sink": 2.5,
}

CONTEXT = {
    "emission": 0.6, "carbon": 0.5, "warming": 0.8, "atmosphere": 0.5,
    "temperature": 0.3, "precipitation": 0.6, "renewable": 0.6,
    "mitigation": 0.5, "adaptation": 0.4, "resilience": 0.4,
    "sustainability": 0.5, "biodiversity": 0.5, "ecosystem": 0.4,
    "weather": 0.4, "ocean": 0.4, "forecast": 0.3, "anomaly": 0.3,
    "energy transition": 0.8, "land use": 0.4, "deforestation": 0.8,
    "methane": 0.7, "albedo": 0.7, "troposphere": 0.6, "circulation": 0.3,
}

# Other fields borrowing the same vocabulary.
NEGATIVE = {
    "carbon nanotube": -3.0, "carbon fiber": -3.0, "carbon nanostructure": -2.5,
    "carbon steel": -2.5, "carbon black": -2.0, "activated carbon": -2.0,
    "quantum": -1.0, "supersymmetr": -2.0, "neutrino": -1.5, "quark": -2.0,
    "black hole": -2.0, "galaxy": -1.5, "exoplanet": -1.5, "cosmolog": -1.5,
    "tumor": -2.0, "carcinoma": -2.0, "clinical trial": -1.5,
}

ACCEPT = 2.5
UNCERTAIN = 0.8

_WS = re.compile(r"\\s+")

# Short terms must match whole words. Substring matching turned "SENSORS"
# into an ENSO hit and scored a horse-injury study as climate research.
_PATTERNS: dict[str, re.Pattern] = {}


def _pattern(term: str) -> re.Pattern:
    if term not in _PATTERNS:
        if len(term) <= 5 and " " not in term:
            _PATTERNS[term] = re.compile(rf"\\b{re.escape(term)}\\b")
        else:
            _PATTERNS[term] = re.compile(re.escape(term))
    return _PATTERNS[term]


def _has(term: str, text: str) -> bool:
    return bool(_pattern(term).search(text))


def _norm(text: str | None) -> str:
    return _WS.sub(" ", (text or "").lower())


def score(title: str | None, abstract: str | None,
          topics: str | None = None) -> tuple[float, str, list[str]]:
    """Return (score, tier, matched_terms).

    Title matches count double: a paper announces its subject in the title,
    while an abstract may mention climate only as passing motivation.
    """
    t, a = _norm(title), _norm(abstract)
    total = 0.0
    hits: list[str] = []

    for lexicon in (CORE, CONTEXT, NEGATIVE):
        for term, weight in lexicon.items():
            in_t, in_a = _has(term, t), _has(term, a)
            if not (in_t or in_a):
                continue
            total += weight * (2.0 if in_t else 1.0)
            if weight > 0:
                hits.append(term)

    core_hit = any(_has(term, t) or _has(term, a) for term in CORE)
    if not core_hit and total < 2.0:
        total *= 0.5

    if topics:
        try:
            labels = " ".join(json.loads(topics)).lower()
            if "climate" in labels or "atmospheric" in labels:
                total += 2.0
                hits.append("topic:climate")
        except (json.JSONDecodeError, TypeError):
            pass

    tier = "accept" if total >= ACCEPT else (
        "uncertain" if total >= UNCERTAIN else "reject")
    return round(total, 2), tier, sorted(set(hits))[:8]


def classify_record(rec: dict) -> dict:
    """Attach score and tier. OpenAlex arrives topic-filtered already."""
    pre_filtered = "openalex" in (rec.get("sources") or "")
    s, tier, _ = score(rec.get("title"), rec.get("abstract"), rec.get("topics"))
    if pre_filtered:
        tier = "accept" if tier != "reject" else "uncertain"
    rec["score"] = s
    rec["tier"] = tier
    return rec
'''

SITE = '"""Render the feed as a static site.\n\nDesign brief: a daily scan surface for climate researchers and policy\nreaders. One job — see what appeared today, decide what to open.\n\nThe organising metaphor is an ice core. Climate science reads its own past\nby drilling layers; each day of publications becomes a stratum in a column\ndown the left edge, thickness set by volume, descending back through time.\nIt is the one bold element; everything else stays quiet.\n\nNo web fonts. A site that publishes its own gram-level CO2e per build has\nno business shipping 60 kB of typefaces to every visitor. Distinctiveness\ncomes from scale, rule weight, and the core column instead.\n"""\n\nfrom __future__ import annotations\n\nimport html\nimport json\nimport sqlite3\nfrom collections import defaultdict\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n\nOUT = Path("public")\nDB = Path("data/feed.db")\nDAYS_SHOWN = 21\nMAX_PER_DAY = 60\n\nCSS = """\n:root{\n  --ice-deep:#0A1A24;      /* deep ice, near-black with blue in it */\n  --ice-mid:#16394F;       /* compressed layer */\n  --ice-pale:#A8C6D9;      /* firn */\n  --snow:#EEF4F7;          /* fresh surface, cool not cream */\n  --meltwater:#4EA8C7;     /* research accent */\n  --sediment:#A87C4F;      /* policy accent, trapped debris */\n  --rule:rgba(168,198,217,.22);\n  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;\n  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;\n}\n*{box-sizing:border-box}\nhtml{scroll-behavior:smooth}\n@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}\n  *{animation:none!important;transition:none!important}}\nbody{\n  margin:0;background:var(--ice-deep);color:var(--snow);\n  font-family:var(--sans);line-height:1.5;\n  -webkit-font-smoothing:antialiased;\n}\na{color:inherit}\n.wrap{max-width:1080px;margin:0 auto;padding:0 24px}\n\n/* ---- masthead ---- */\nheader{border-bottom:1px solid var(--rule);padding:56px 0 28px;margin-bottom:8px}\nh1{\n  font-size:clamp(2.4rem,6vw,4.2rem);line-height:.95;margin:0 0 18px;\n  font-weight:800;letter-spacing:-.045em;\n}\nh1 .sub{display:block;color:var(--ice-pale);font-weight:300;\n  font-size:clamp(.9rem,2vw,1.05rem);letter-spacing:.16em;\n  text-transform:uppercase;margin-top:16px}\n.stats{display:flex;flex-wrap:wrap;gap:28px;font-family:var(--mono);\n  font-size:.76rem;color:var(--ice-pale);margin-top:24px}\n.stats b{display:block;color:var(--snow);font-size:1.5rem;font-weight:600;\n  letter-spacing:-.02em;margin-bottom:2px}\n\n/* ---- search ---- */\n.search{margin:28px 0 0;position:relative}\n.search input{\n  width:100%;padding:13px 16px;background:rgba(168,198,217,.07);\n  border:1px solid var(--rule);border-radius:2px;color:var(--snow);\n  font-family:var(--mono);font-size:.85rem;\n}\n.search input:focus{outline:2px solid var(--meltwater);outline-offset:1px;\n  background:rgba(168,198,217,.11)}\n.search input::placeholder{color:rgba(168,198,217,.5)}\n\n/* ---- the core ---- */\n.core-layout{display:grid;grid-template-columns:64px 1fr;gap:32px;\n  padding:40px 0 80px;align-items:start}\n.core{position:sticky;top:24px;display:flex;flex-direction:column;gap:2px}\n.core-label{font-family:var(--mono);font-size:.58rem;letter-spacing:.14em;\n  color:rgba(168,198,217,.55);text-transform:uppercase;margin-bottom:8px;\n  writing-mode:vertical-rl;height:80px}\n.stratum{\n  display:block;border-radius:1px;background:var(--ice-mid);\n  border-left:3px solid var(--meltwater);\n  transition:background .18s,border-color .18s;\n  position:relative;\n}\n.stratum:hover,.stratum:focus-visible{background:var(--meltwater);\n  border-color:var(--snow);outline:none}\n.stratum span{position:absolute;left:100%;margin-left:8px;top:50%;\n  transform:translateY(-50%);font-family:var(--mono);font-size:.6rem;\n  color:var(--ice-pale);white-space:nowrap;opacity:0;pointer-events:none;\n  transition:opacity .18s}\n.stratum:hover span,.stratum:focus-visible span{opacity:1}\n\n/* ---- days ---- */\n.day{margin-bottom:52px;scroll-margin-top:24px}\n.day-head{display:flex;align-items:baseline;gap:14px;\n  padding-bottom:10px;margin-bottom:4px;border-bottom:1px solid var(--rule)}\n.day-date{font-family:var(--mono);font-size:1rem;letter-spacing:.04em;\n  color:var(--snow);font-weight:600}\n.day-count{font-family:var(--mono);font-size:.7rem;color:var(--ice-pale)}\n.day-depth{margin-left:auto;font-family:var(--mono);font-size:.62rem;\n  color:rgba(168,198,217,.45)}\n\n/* ---- entries ---- */\narticle{padding:16px 0;border-bottom:1px solid rgba(168,198,217,.08)}\narticle:last-child{border-bottom:none}\narticle h2{margin:0 0 7px;font-size:1.02rem;line-height:1.34;font-weight:500;\n  letter-spacing:-.008em}\narticle h2 a{text-decoration:none;background-image:linear-gradient(var(--meltwater),var(--meltwater));\n  background-size:0 1px;background-position:0 100%;background-repeat:no-repeat;\n  transition:background-size .2s}\narticle h2 a:hover,article h2 a:focus-visible{background-size:100% 1px;\n  color:var(--meltwater);outline:none}\n.meta{font-family:var(--mono);font-size:.7rem;color:var(--ice-pale);\n  display:flex;flex-wrap:wrap;gap:8px;align-items:center}\n.meta .authors{color:rgba(238,244,247,.72)}\n.tag{padding:1px 7px;border:1px solid currentColor;border-radius:1px;\n  font-size:.6rem;letter-spacing:.1em;text-transform:uppercase}\n.tag.research{color:var(--meltwater)}\n.tag.policy{color:var(--sediment)}\n.tag.oa{color:var(--ice-pale);opacity:.7}\n.abstract{margin:9px 0 0;font-size:.86rem;color:rgba(238,244,247,.62);\n  line-height:1.55;max-width:68ch}\n\nfooter{border-top:1px solid var(--rule);padding:28px 0 56px;\n  font-family:var(--mono);font-size:.68rem;color:rgba(168,198,217,.6);\n  display:flex;flex-wrap:wrap;gap:20px;justify-content:space-between}\nfooter a{color:var(--ice-pale)}\n.empty{padding:60px 0;color:var(--ice-pale);font-family:var(--mono);\n  font-size:.85rem}\n\n@media (max-width:720px){\n  .core-layout{grid-template-columns:1fr;gap:0}\n  .core{display:none}\n}\n"""\n\nSEARCH_JS = """\nconst q=document.getElementById(\'q\'),arts=[...document.querySelectorAll(\'article\')],\n      days=[...document.querySelectorAll(\'.day\')];\nq.addEventListener(\'input\',()=>{\n  const v=q.value.trim().toLowerCase();\n  arts.forEach(a=>{a.hidden=v&&!a.dataset.s.includes(v)});\n  days.forEach(d=>{d.hidden=![...d.querySelectorAll(\'article\')].some(a=>!a.hidden)});\n});\n"""\n\n\ndef esc(s) -> str:\n    return html.escape(str(s or ""))\n\n\ndef load(conn) -> tuple[list, dict]:\n    rows = conn.execute(\n        """SELECT title, abstract, authors, venue, published_date, url,\n                  is_oa, kind, sources, score, tier\n           FROM works\n           WHERE tier IN (\'accept\',\'uncertain\') AND published_date IS NOT NULL\n           ORDER BY published_date DESC, score DESC"""\n    ).fetchall()\n\n    totals = dict(conn.execute(\n        "SELECT COUNT(*), COALESCE(SUM(tier=\'accept\'),0) FROM works"\n    ).fetchone() and {} or {})\n    return rows, totals\n\n\ndef render() -> str:\n    conn = sqlite3.connect(DB)\n    conn.row_factory = sqlite3.Row\n\n    rows = conn.execute(\n        """SELECT title, abstract, authors, venue, published_date, url,\n                  is_oa, kind, score, tier\n           FROM works\n           WHERE tier IN (\'accept\',\'uncertain\') AND published_date IS NOT NULL\n           ORDER BY published_date DESC, score DESC"""\n    ).fetchall()\n\n    total_all = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]\n    kept = len(rows)\n    last_run = conn.execute(\n        "SELECT co2e_g, finished_at FROM runs WHERE finished_at IS NOT NULL "\n        "ORDER BY id DESC LIMIT 1").fetchone()\n\n    by_day: dict[str, list] = defaultdict(list)\n    for r in rows:\n        by_day[r["published_date"]].append(r)\n\n    days = sorted(by_day, reverse=True)[:DAYS_SHOWN]\n    peak = max((len(by_day[d]) for d in days), default=1)\n\n    # --- core column: one stratum per day, height by volume ---\n    strata = []\n    for i, d in enumerate(days):\n        n = len(by_day[d])\n        h = max(6, round(9 + 52 * (n / peak)))\n        opacity = 0.35 + 0.65 * (1 - i / max(len(days), 1))\n        strata.append(\n            f\'<a class="stratum" href="#d{d}" style="height:{h}px;\'\n            f\'opacity:{opacity:.2f}" aria-label="{d}, {n} works">\'\n            f\'<span>{d} · {n}</span></a>\'\n        )\n\n    # --- day sections ---\n    sections = []\n    for i, d in enumerate(days):\n        items = by_day[d][:MAX_PER_DAY]\n        entries = []\n        for r in items:\n            try:\n                authors = json.loads(r["authors"] or "[]")\n            except json.JSONDecodeError:\n                authors = []\n            alist = ", ".join(authors[:3])\n            if len(authors) > 3:\n                alist += f" +{len(authors) - 3}"\n\n            tags = [f\'<span class="tag {r["kind"]}">{esc(r["kind"])}</span>\']\n            if r["is_oa"]:\n                tags.append(\'<span class="tag oa">open</span>\')\n\n            abstract = (r["abstract"] or "")[:260]\n            if r["abstract"] and len(r["abstract"]) > 260:\n                abstract += "…"\n\n            haystack = esc(f\'{r["title"]} {alist} {r["venue"]} {abstract}\').lower()\n            entries.append(f"""<article data-s="{haystack}">\n<h2><a href="{esc(r[\'url\'])}" rel="noopener">{esc(r[\'title\'])}</a></h2>\n<div class="meta"><span class="authors">{esc(alist) or \'—\'}</span>\n<span>{esc(r[\'venue\']) or \'—\'}</span>{\'\'.join(tags)}</div>\n{f\'<p class="abstract">{esc(abstract)}</p>\' if abstract else \'\'}\n</article>""")\n\n        more = (f\'<div class="day-depth">showing {MAX_PER_DAY} of \'\n                f\'{len(by_day[d])}</div>\' if len(by_day[d]) > MAX_PER_DAY\n                else f\'<div class="day-depth">layer {i + 1}</div>\')\n\n        sections.append(f"""<section class="day" id="d{d}">\n<div class="day-head"><span class="day-date">{d}</span>\n<span class="day-count">{len(by_day[d])} works</span>{more}</div>\n{\'\'.join(entries)}\n</section>""")\n\n    co2 = f"{last_run[\'co2e_g\']:.2f} g" if last_run and last_run["co2e_g"] else "—"\n    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")\n\n    body = "".join(sections) or \'<p class="empty">No works yet. Run the ingest.</p>\'\n\n    return f"""<!doctype html>\n<html lang="en"><head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>climate-feed — new climate research and policy, daily</title>\n<meta name="description" content="A daily layer of new climate science research and policy documents, drawn from OpenAlex and arXiv.">\n<style>{CSS}</style>\n</head><body>\n<div class="wrap">\n<header>\n<h1>climate&#8203;-feed<span class="sub">New climate research &amp; policy, drilled daily</span></h1>\n<div class="stats">\n<div><b>{kept:,}</b>works in the core</div>\n<div><b>{len(days)}</b>days of layers</div>\n<div><b>{total_all:,}</b>records screened</div>\n<div><b>{co2}</b>last build</div>\n</div>\n<div class="search"><input id="q" type="search" placeholder="Filter by title, author, journal…" aria-label="Filter works"></div>\n</header>\n\n<div class="core-layout">\n<nav class="core" aria-label="Jump to day">\n<div class="core-label">Depth →</div>\n{\'\'.join(strata)}\n</nav>\n<main>{body}</main>\n</div>\n\n<footer>\n<span>Built {built}</span>\n<span>Sources: OpenAlex · arXiv</span>\n<span><a href="https://github.com/VasundharaShaw/climate-feed">Source &amp; data</a></span>\n</footer>\n</div>\n<script>{SEARCH_JS}</script>\n</body></html>"""\n\n\ndef main() -> None:\n    OUT.mkdir(exist_ok=True)\n    OUT.joinpath("index.html").write_text(render(), encoding="utf-8")\n    size = OUT.joinpath("index.html").stat().st_size\n    print(f"wrote public/index.html ({size / 1024:.0f} kB)")\n\n\nif __name__ == "__main__":\n    main()\n'

print("Applying update...")
write("ingest/classify.py", CLASSIFY)
write("site_build/__init__.py", "")
write("site_build/__main__.py", SITE)

# --- db.py: persist score and tier -------------------------------------
patch("ingest/db.py",
      "is_oa, sources, kind, topics, first_seen, last_updated)",
      "is_oa, sources, kind, topics, score, tier, first_seen, last_updated)",
      "insert score/tier columns")
patch("ingest/db.py",
      ":url, :pdf_url, :is_oa, :sources, :kind, :topics,\n"
      "                       :first_seen, :last_updated)\"\"\",",
      ":url, :pdf_url, :is_oa, :sources, :kind, :topics,\n"
      "                       :score, :tier, :first_seen, :last_updated)\"\"\",",
      "bind score/tier params")
patch("ingest/db.py",
      '"is_oa", "sources", "kind", "topics")',
      '"is_oa", "sources", "kind", "topics", "score", "tier")',
      "include score/tier in defaults")

# --- run.py: classify before upsert ------------------------------------
patch("ingest/run.py",
      "from . import db, http",
      "from . import db, http\nfrom .classify import classify_record",
      "import classifier")
patch("ingest/run.py",
      "    for rec in openalex.fetch(since=since):\n        counts[db.upsert(conn, rec)] += 1",
      "    for rec in openalex.fetch(since=since):\n"
      "        counts[db.upsert(conn, classify_record(rec))] += 1",
      "classify openalex records")
patch("ingest/run.py",
      "        raw = rec.pop(\"_published_raw\", None)\n        counts[db.upsert(conn, rec)] += 1",
      "        raw = rec.pop(\"_published_raw\", None)\n"
      "        counts[db.upsert(conn, classify_record(rec))] += 1",
      "classify arxiv records")

print()
if changed:
    print(f"Changed {len(set(changed))} files.")
else:
    print("Nothing to do — already up to date.")
print("""
Next:
  1. python3 backfill_scores.py     # score the 2,498 rows already stored
  2. python -m site_build           # build the site
  3. open public/index.html
""")
