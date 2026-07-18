#!/usr/bin/env bash
# Bootstrap the climate-feed repository.
#
#   ./bootstrap.sh                      # local git init only
#   ./bootstrap.sh --push YOUR-GH-USER  # also create + push via gh CLI
#
set -euo pipefail

REPO_NAME="${REPO_NAME:-climate-feed}"
PUSH_USER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH_USER="${2:?need a github username}"; shift 2 ;;
    --name) REPO_NAME="${2:?need a name}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------- structure
mkdir -p data
touch data/.gitkeep

# The workflow references site_build, which does not exist yet. Stub it so
# the first CI run succeeds instead of failing at the build step.
if [[ ! -f site_build/__main__.py ]]; then
  mkdir -p site_build public
  cat > site_build/__init__.py <<'PY'
PY
  cat > site_build/__main__.py <<'PY'
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
PY
  echo "created site_build/ stub"
fi

# ------------------------------------------------------------------ licences
# Code and data want different licences. CC-BY-4.0 on the corpus keeps it
# compatible with Climate Policy Radar's terms and citable downstream.
cat > LICENSE <<'EOF'
MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF

cat > LICENSE-DATA <<'EOF'
The contents of data/ are licensed under Creative Commons Attribution 4.0
International (CC-BY-4.0). https://creativecommons.org/licenses/by/4.0/

Metadata is aggregated from OpenAlex (CC0), arXiv (per-item author terms),
and other upstream sources. Attribution requirements of those sources apply
to their respective records.
EOF

# CITATION.cff makes the repo citable on GitHub and via Zenodo.
cat > CITATION.cff <<'EOF'
cff-version: 1.2.0
title: climate-feed
message: If you use this corpus, please cite it.
type: software
authors:
  - family-names: Shaw
    given-names: Vasundhara
    orcid: "https://orcid.org/0000-0002-5824-7191"
license: MIT
repository-code: "https://github.com/USER/climate-feed"
EOF

# ------------------------------------------------------------------- git
if [[ ! -d .git ]]; then
  git init -q -b main
  echo "initialised git repo"
fi

# Check identity up front. Otherwise a failed commit gets misreported as
# "nothing to commit" and you push an empty repo.
if ! git config user.email >/dev/null && ! git config --global user.email >/dev/null; then
  echo "ERROR: git identity not set. Run:" >&2
  echo '  git config --global user.name  "Your Name"' >&2
  echo '  git config --global user.email "you@example.org"' >&2
  exit 1
fi

git add -A
if git diff --staged --quiet; then
  echo "nothing new to commit"
else
  git commit -q -m "feat: ingest layer for OpenAlex and arXiv with dedup"
  echo "committed"
fi

# ------------------------------------------------------------------ remote
if [[ -n "$PUSH_USER" ]]; then
  if ! command -v gh >/dev/null; then
    echo "gh CLI not found. Install it, or create the repo in the browser and run:" >&2
    echo "  git remote add origin git@github.com:$PUSH_USER/$REPO_NAME.git" >&2
    echo "  git push -u origin main" >&2
    exit 1
  fi
  gh repo create "$PUSH_USER/$REPO_NAME" \
    --public \
    --source=. \
    --remote=origin \
    --description "Daily aggregation of climate science research and policy" \
    --push
  echo
  echo "Repo live at https://github.com/$PUSH_USER/$REPO_NAME"
fi

cat <<'EOF'

Next steps:
  1. Set your contact address in ingest/http.py (CONTACT) and
     ingest/sources/openalex.py (mailto). OpenAlex's polite pool needs it.
  2. Test locally before letting CI loose:
       pip install -r requirements.txt
       python -m ingest.run --dry-run
  3. Add repo secrets CF_API_TOKEN and CF_ACCOUNT_ID for Cloudflare Pages,
     or delete the Deploy step and use GitHub Pages instead.
  4. Settings > Actions > General > Workflow permissions:
     enable "Read and write permissions" so the bot can commit data/feed.db.
EOF
