"""Is this work actually about climate?

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
    "monsoon": 1.5, "el nino": 2.0, "el ni\u00f1o": 2.0, "enso": 1.5,
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

_WS = re.compile(r"\s+")

# Short terms must match whole words. Substring matching turned "SENSORS"
# into an ENSO hit and scored a horse-injury study as climate research.
_PATTERNS: dict[str, re.Pattern] = {}


def _pattern(term: str) -> re.Pattern:
    if term not in _PATTERNS:
        if len(term) <= 5 and " " not in term:
            _PATTERNS[term] = re.compile(rf"\b{re.escape(term)}\b")
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


# Arriving via a topic-filtered query is evidence, not proof. OpenAlex
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
    return rec
