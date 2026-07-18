"""Identifier and title normalisation, plus the dedup decision.

The only interesting problem here is collapsing a preprint and its later
published version into one row. Strategy, cheapest test first:

1. Matching normalised DOI      -> same work, certain.
2. Matching arXiv id            -> same work, certain.
3. Matching normalised title    -> same work, near-certain.
4. Same block key (first author surname + year) AND high title token
   overlap -> same work, probable. Catches retitled preprints.

No fuzzy-matching library needed; token Jaccard on normalised titles is
enough at this scale and keeps the dependency tree to one package.
"""

from __future__ import annotations

import re
import unicodedata

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)

_ARXIV_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

# Words that carry no discriminative signal in a title.
_STOP = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on",
    "or", "the", "to", "with", "using", "via", "study", "analysis",
}


def norm_doi(raw: str | None) -> str | None:
    """Lowercase, strip resolver prefixes. Returns None if not DOI-shaped."""
    if not raw:
        return None
    s = raw.strip().lower()
    for p in _DOI_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    s = s.rstrip("./")
    return s if s.startswith("10.") and "/" in s else None


def norm_arxiv(raw: str | None) -> str | None:
    """Extract the bare arXiv id, dropping any version suffix."""
    if not raw:
        return None
    m = _ARXIV_RE.search(raw)
    return m.group(1) if m else None


def norm_openalex(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.rstrip("/").rsplit("/", 1)[-1] or None


def title_key(title: str | None) -> str:
    """Aggressively normalised title: lowercase, de-accented, alnum only."""
    if not title:
        return ""
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _NONWORD.sub(" ", s.lower())
    return _WS.sub(" ", s).strip()


def title_tokens(title: str | None) -> frozenset[str]:
    return frozenset(t for t in title_key(title).split() if t not in _STOP and len(t) > 2)


def block_key(authors: list[str] | None, date: str | None) -> str | None:
    """first-author surname + publication year. Cheap blocking for step 4."""
    if not authors or not date:
        return None
    surname = title_key(authors[0]).split()
    if not surname:
        return None
    return f"{surname[-1]}:{date[:4]}"


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


TITLE_MATCH_THRESHOLD = 0.75


def find_duplicate(conn, record: dict) -> int | None:
    """Return the rowid of an existing work that `record` duplicates, else None."""
    cur = conn.cursor()

    # 1 & 2: hard identifiers.
    for col, val in (("doi", record.get("doi")),
                     ("arxiv_id", record.get("arxiv_id")),
                     ("openalex_id", record.get("openalex_id"))):
        if val:
            row = cur.execute(f"SELECT id FROM works WHERE {col} = ?", (val,)).fetchone()
            if row:
                return row[0]

    # 3: exact normalised title.
    tk = record.get("title_key")
    if tk:
        row = cur.execute("SELECT id FROM works WHERE title_key = ?", (tk,)).fetchone()
        if row:
            return row[0]

    # 4: same author+year block, high title overlap.
    bk = record.get("block_key")
    if bk:
        incoming = title_tokens(record.get("title"))
        for rid, cand_title in cur.execute(
            "SELECT id, title FROM works WHERE block_key = ?", (bk,)
        ):
            if jaccard(incoming, title_tokens(cand_title)) >= TITLE_MATCH_THRESHOLD:
                return rid

    return None
