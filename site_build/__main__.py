"""Placeholder renderer. Emits a minimal index so CI is green from day one."""
import sqlite3
from pathlib import Path

OUT = Path("public")
OUT.mkdir(exist_ok=True)

conn = sqlite3.connect("data/feed.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT title, venue, published_date, url FROM works "
    "ORDER BY published_date DESC LIMIT 100"
).fetchall()

items = "\n".join(
    f'<li><a href="{r["url"]}">{r["title"]}</a> '
    f'<small>{r["venue"] or ""} &middot; {r["published_date"] or ""}</small></li>'
    for r in rows
)
OUT.joinpath("index.html").write_text(
    f"<!doctype html><meta charset=utf-8><title>climate-feed</title>"
    f"<h1>climate-feed</h1><p>{len(rows)} most recent works.</p><ul>{items}</ul>"
)
print(f"wrote public/index.html ({len(rows)} works)")
