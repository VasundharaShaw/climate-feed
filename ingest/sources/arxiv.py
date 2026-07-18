"""arXiv ingest.

Parsed with stdlib ElementTree rather than feedparser — one fewer
dependency to install on every CI run, which is a real (if small) share of
the job's footprint.

arXiv has no "changed since" filter, so we sort by submittedDate descending
and stop as soon as we cross the watermark. In steady state that is a
single page of 100 results per category per day.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from . import http
from ..normalise import block_key, norm_arxiv, norm_doi, title_key

BASE = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

CATEGORIES = [
    "physics.ao-ph",   # atmospheric and oceanic physics
    "physics.geo-ph",  # geophysics
    "physics.soc-ph",  # catches climate-economics and energy-systems work
    "q-bio.PE",        # populations and ecology
    "econ.GN",         # general economics, incl. climate econ
]

PAGE = 100


def fetch(watermark: str | None = None, max_pages_per_cat: int = 5):
    """Yield records newer than `watermark` (ISO datetime), newest first."""
    for cat in CATEGORIES:
        start = 0
        for _ in range(max_pages_per_cat):
            resp = http.get(BASE, params={
                "search_query": f"cat:{cat}",
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "start": start,
                "max_results": PAGE,
            })
            entries = ET.fromstring(resp.text).findall("a:entry", NS)
            if not entries:
                break

            crossed = False
            for e in entries:
                published = _text(e, "a:published")
                if watermark and published and published <= watermark:
                    crossed = True
                    break
                rec = _to_record(e)
                if rec:
                    yield rec

            if crossed or len(entries) < PAGE:
                break
            start += PAGE


def _text(el, path: str) -> str | None:
    node = el.find(path, NS)
    return node.text.strip() if node is not None and node.text else None


def _to_record(e) -> dict | None:
    title = _text(e, "a:title")
    if not title:
        return None
    title = " ".join(title.split())

    authors = [
        n.text.strip()
        for n in e.findall("a:author/a:name", NS)
        if n is not None and n.text
    ]
    published = _text(e, "a:published")
    pub_date = published[:10] if published else None

    pdf_url = None
    for link in e.findall("a:link", NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href")

    abstract = _text(e, "a:summary")
    if abstract:
        abstract = " ".join(abstract.split())

    return {
        "doi": norm_doi(_text(e, "arxiv:doi")),
        "arxiv_id": norm_arxiv(_text(e, "a:id")),
        "openalex_id": None,
        "title": title,
        "title_key": title_key(title),
        "block_key": block_key(authors, pub_date),
        "abstract": abstract,
        "authors": json.dumps(authors),
        "venue": _text(e, "arxiv:journal_ref") or "arXiv",
        "published_date": pub_date,
        "url": _text(e, "a:id"),
        "pdf_url": pdf_url,
        "is_oa": 1,
        "sources": json.dumps(["arxiv"]),
        "kind": "research",
        "topics": json.dumps([
            c.get("term") for c in e.findall("a:category", NS) if c.get("term")
        ]),
        "_published_raw": published,
    }
