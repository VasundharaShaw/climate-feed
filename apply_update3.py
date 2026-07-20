#!/usr/bin/env python3
"""Update 3: about section, feedback page, prune dead feeds.

    python3 apply_update3.py

Run from the repo root. Idempotent.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
changed: list[str] = []


def patch(rel: str, old: str, new: str, label: str) -> None:
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


EXTRA_CSS = """
/* ---- about + colophon ---- */
.about{border-top:1px solid var(--rule);padding:44px 0 8px;
  display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:36px}
.about h3{font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;
  color:var(--ice-pale);margin:0 0 12px;font-family:var(--mono);font-weight:500}
.about p{margin:0 0 10px;font-size:.85rem;color:rgba(238,244,247,.72);
  line-height:1.6;max-width:46ch}
.about a{color:var(--meltwater);text-decoration:none;
  border-bottom:1px solid rgba(78,168,199,.35)}
.about a:hover,.about a:focus-visible{border-bottom-color:var(--meltwater);
  outline:none}
.cta{display:inline-block;margin-top:6px;padding:9px 16px;
  border:1px solid var(--meltwater);color:var(--meltwater);
  font-family:var(--mono);font-size:.72rem;letter-spacing:.08em;
  text-transform:uppercase;text-decoration:none}
.cta:hover,.cta:focus-visible{background:var(--meltwater);
  color:var(--ice-deep);outline:none}

/* ---- feedback form ---- */
.form{max-width:560px;padding:36px 0 80px}
.form label{display:block;font-family:var(--mono);font-size:.68rem;
  letter-spacing:.14em;text-transform:uppercase;color:var(--ice-pale);
  margin:20px 0 7px}
.form input,.form textarea,.form select{
  width:100%;padding:12px 14px;background:rgba(168,198,217,.07);
  border:1px solid var(--rule);border-radius:2px;color:var(--snow);
  font-family:var(--sans);font-size:.92rem}
.form textarea{min-height:150px;resize:vertical;line-height:1.55}
.form input:focus,.form textarea:focus,.form select:focus{
  outline:2px solid var(--meltwater);outline-offset:1px;
  background:rgba(168,198,217,.11)}
.form button{margin-top:26px;padding:12px 26px;background:var(--meltwater);
  border:none;border-radius:2px;color:var(--ice-deep);font-family:var(--mono);
  font-size:.76rem;letter-spacing:.1em;text-transform:uppercase;
  font-weight:600;cursor:pointer}
.form button:hover{background:var(--snow)}
.form button:focus-visible{outline:2px solid var(--snow);outline-offset:2px}
.hint{font-size:.78rem;color:rgba(168,198,217,.65);margin-top:8px;
  line-height:1.5}
.hint a{color:var(--meltwater)}
.back{display:inline-block;margin-top:28px;font-family:var(--mono);
  font-size:.72rem;color:var(--ice-pale);text-decoration:none}
.back:hover{color:var(--meltwater)}
.notice{padding:14px 16px;border:1px solid var(--sediment);border-radius:2px;
  color:var(--sediment);font-size:.82rem;margin-bottom:24px}
"""

# Placeholders below are module constants in site_build/__main__.py, because
# this block gets spliced into an f-string at render time.
ABOUT_HTML = """
<section class="about" id="about">
<div>
<h3>What this is</h3>
<p>A daily layer of new climate research and policy analysis, pulled
automatically from OpenAlex, arXiv and a set of policy newsrooms. Everything
is scored for climate relevance before it appears, so the feed stays narrow
rather than exhaustive.</p>
<p>Nothing here is hand-curated. If something looks wrong, it probably is.</p>
</div>
<div>
<h3>How it runs</h3>
<p>One scheduled job per day on GitHub Actions, rendering a static page. No
server runs between builds, so this site draws no power while you are not
reading it. Each build measures its own bytes transferred and estimated
emissions, published at the top.</p>
<p>Code and the full database are <a href="{REPO_URL}">open on GitHub</a>.</p>
</div>
<div>
<h3>Who made it</h3>
<p>Built by <a href="{AUTHOR_URL}">{AUTHOR}</a>, an astrophysicist and
research software engineer working on open science infrastructure.</p>
<p>Written with the help of <a href="https://claude.ai">Claude</a>, an AI
assistant made by Anthropic.</p>
<a class="cta" href="feedback.html">Send feedback</a>
</div>
</section>
"""

FORM_CONFIGURED = """<form action="https://formspree.io/f/{formspree_id}" method="POST">
<label for="kind">What kind of feedback</label>
<select id="kind" name="kind">
<option>Something in the feed looks wrong</option>
<option>A source is missing</option>
<option>The relevance filter is too strict</option>
<option>The relevance filter is too loose</option>
<option>Something else</option>
</select>

<label for="email">Your email (optional)</label>
<input id="email" type="email" name="email" placeholder="Only if you want a reply">

<label for="message">Message</label>
<textarea id="message" name="message" required
 placeholder="A link or a title helps me find it faster."></textarea>

<button type="submit">Send feedback</button>
<p class="hint">Relayed to my inbox. Nothing is stored on this site &mdash;
there is no server here to store it on.</p>
</form>"""

FORM_UNCONFIGURED = """<div class="notice">The form is not connected yet.
Set <code>FORMSPREE_ID</code> in <code>site_build/__main__.py</code>.</div>
<p class="hint">Until then, email
<a href="mailto:{email}">{email}</a>.</p>"""

FEEDBACK_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Feedback &mdash; climate-feed</title>
<meta name="description" content="Report a problem or suggest a source for climate-feed.">
<style>{css}</style>
</head><body>
<div class="wrap">
<header>
<h1>Feedback<span class="sub">Tell me what is broken or missing</span></h1>
</header>

<div class="form">
<p class="hint">This feed is assembled automatically, so mistakes are
structural rather than personal: a source that should be included, a paper
that clearly is not climate science, a date that looks wrong. All of it
helps.</p>

{form}

<a class="back" href="index.html">&larr; Back to the feed</a>
</div>

<footer>
<span>climate-feed</span>
<span><a href="{repo}">Source &amp; data</a></span>
<span><a href="{site}">{author}</a></span>
</footer>
</div>
</body></html>"""


print("Applying update 3...")

patch(
    "ingest/sources/policy.py",
    '    "climateanalytics": ("https://climateanalytics.org/feed", "Climate Analytics"),\n'
    '    "grantham_lse":   ("https://www.lse.ac.uk/granthaminstitute/feed/", "Grantham Institute (LSE)"),\n'
    '    "wri":            ("https://www.wri.org/rss.xml", "World Resources Institute"),\n'
    '    "iisd_enb":       ("https://enb.iisd.org/feed", "IISD Earth Negotiations Bulletin"),\n'
    '    "eea":            ("https://www.eea.europa.eu/en/newsroom/news/RSS", "European Environment Agency"),\n',
    "    # Removed after a live check on 2026-07-20: climateanalytics (404),\n"
    "    # wri (403), iisd_enb (403), eea (404), grantham_lse (no items).\n"
    "    # The 403s look like user-agent blocking and may be recoverable;\n"
    "    # the 404s need a current URL. Verify with\n"
    "    #   python -m ingest.sources.policy\n"
    "    # before re-adding anything.\n",
    "remove 5 dead feeds",
)

patch(
    "site_build/__main__.py",
    'OUT = Path("public")\nDB = Path("data/feed.db")',
    'OUT = Path("public")\n'
    'DB = Path("data/feed.db")\n\n'
    "# --- site identity ---------------------------------------------------\n"
    'AUTHOR = "Vasundhara Shaw"\n'
    'AUTHOR_URL = "https://vasundharashaw.github.io"\n'
    'REPO_URL = "https://github.com/VasundharaShaw/climate-feed"\n\n'
    "# Formspree relays the contact form to your inbox without putting your\n"
    "# address in the HTML, which matters because scrapers read static pages.\n"
    "# Sign up at formspree.io, create a form pointed at your inbox, then\n"
    "# paste the ID (the part after /f/ in the endpoint) here.\n"
    'FORMSPREE_ID = ""\n\n'
    "# Only used when FORMSPREE_ID is blank. Publishing this exposes it to\n"
    "# scrapers, so prefer the form.\n"
    'FALLBACK_EMAIL = "vasundharashaw@gmail.com"',
    "add site identity config",
)

patch(
    "site_build/__main__.py",
    "footer{border-top:1px solid var(--rule);padding:28px 0 56px;",
    EXTRA_CSS + "\nfooter{border-top:1px solid var(--rule);padding:28px 0 56px;",
    "add about/form styles",
)

patch(
    "site_build/__main__.py",
    "<footer>\n<span>Built {built}</span>",
    ABOUT_HTML + "\n<footer>\n<span>Built {built}</span>",
    "add about section",
)

patch(
    "site_build/__main__.py",
    '<span><a href="https://github.com/VasundharaShaw/climate-feed">Source &amp; data</a></span>',
    '<span><a href="{REPO_URL}">Source &amp; data</a> &middot; '
    '<a href="feedback.html">Feedback</a></span>',
    "add feedback link to footer",
)

patch(
    "site_build/__main__.py",
    'def main() -> None:\n'
    '    OUT.mkdir(exist_ok=True)\n'
    '    OUT.joinpath("index.html").write_text(render(), encoding="utf-8")\n'
    '    size = OUT.joinpath("index.html").stat().st_size\n'
    '    print(f"wrote public/index.html ({size / 1024:.0f} kB)")',
    "FORM_CONFIGURED = " + repr(FORM_CONFIGURED) + "\n\n"
    "FORM_UNCONFIGURED = " + repr(FORM_UNCONFIGURED) + "\n\n"
    "FEEDBACK_PAGE = " + repr(FEEDBACK_PAGE) + "\n\n\n"
    "def render_feedback() -> str:\n"
    '    """Contact form. The site is static, so a relay does the sending."""\n'
    "    form = (FORM_CONFIGURED.format(formspree_id=FORMSPREE_ID)\n"
    "            if FORMSPREE_ID\n"
    "            else FORM_UNCONFIGURED.format(email=FALLBACK_EMAIL))\n"
    "    return FEEDBACK_PAGE.format(css=CSS, form=form, repo=REPO_URL,\n"
    "                                site=AUTHOR_URL, author=AUTHOR)\n\n\n"
    "def main() -> None:\n"
    "    OUT.mkdir(exist_ok=True)\n"
    '    OUT.joinpath("index.html").write_text(render(), encoding="utf-8")\n'
    '    OUT.joinpath("feedback.html").write_text(render_feedback(),\n'
    '                                             encoding="utf-8")\n'
    '    for name in ("index.html", "feedback.html"):\n'
    "        kb = OUT.joinpath(name).stat().st_size / 1024\n"
    '        print(f"wrote public/{name} ({kb:.0f} kB)")\n'
    "    if not FORMSPREE_ID:\n"
    '        print("\\nNote: FORMSPREE_ID is blank, so the feedback page shows "\n'
    '              "a plain email address instead of a form.")',
    "render feedback page",
)

print()
print(f"Changed {len(set(changed))} files." if changed else "Already up to date.")
print("""
Next:
  python -m site_build && open public/index.html

To connect the form:
  1. formspree.io -> sign up free -> New Form -> deliver to your Gmail
  2. Copy the ID from the endpoint (https://formspree.io/f/XXXXXXXX)
  3. Paste it into FORMSPREE_ID in site_build/__main__.py
  4. python -m site_build
""")
