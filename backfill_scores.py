#!/usr/bin/env python3
"""Score rows that were ingested before the classifier existed.

Reads every work, applies the lexicon, writes score and tier back.
Reports what would be filtered out so you can sanity-check the threshold
before trusting it.
"""
import sqlite3
from collections import Counter

from ingest.classify import classify_record

conn = sqlite3.connect("data/feed.db")
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT id, title, abstract, topics, sources FROM works").fetchall()
tiers = Counter()

for r in rows:
    rec = classify_record({
        "title": r["title"], "abstract": r["abstract"],
        "topics": r["topics"], "sources": r["sources"],
    })
    tiers[rec["tier"]] += 1
    conn.execute("UPDATE works SET score = ?, tier = ? WHERE id = ?",
                 (rec["score"], rec["tier"], r["id"]))

conn.commit()

total = len(rows)
if not total:
    print("No works in data/feed.db yet. Run: python -m ingest.run")
    raise SystemExit(0)

print(f"Scored {total:,} works:")
for tier in ("accept", "uncertain", "reject"):
    n = tiers[tier]
    print(f"  {tier:<10} {n:>6,}  {n / total * 100:5.1f}%")

print("\nSample of what was REJECTED (check these look like junk):")
for r in conn.execute(
    "SELECT title, score FROM works WHERE tier='reject' "
    "ORDER BY RANDOM() LIMIT 6"):
    print(f"  [{r['score']:>5}] {r['title'][:78]}")

print("\nSample of what was ACCEPTED (check these look like climate):")
for r in conn.execute(
    "SELECT title, score FROM works WHERE tier='accept' "
    "ORDER BY RANDOM() LIMIT 6"):
    print(f"  [{r['score']:>5}] {r['title'][:78]}")
