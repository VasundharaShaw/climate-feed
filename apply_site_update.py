#!/usr/bin/env python3
"""Site update: about section, contact page, prune dead feeds.

Replaces the earlier apply_update3 / apply_update4 pair. Run from the repo
root after apply_update.py and apply_update2.py:

    python3 apply_site_update.py

Then set CONTACT_EMAIL in site_build/__main__.py and rebuild. Idempotent.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
changed: list[str] = []


def patch(rel: str, old: str, new: str, label: str) -> None:
    p = ROOT / rel
    if not p.exists():
        sys.exit(f"ERROR: {rel} not found. Run this from the repo root.")
    s = p.read_text()
    if new in s:
        print(f"  = {rel}: {label} (already applied)")
        return
    if old not in s:
        sys.exit(
            f"ERROR: anchor not found in {rel} for: {label}\n"
            f"       Run apply_update.py and apply_update2.py first."
        )
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
.about .mail{font-family:var(--mono);font-size:.8rem;word-break:break-all}
.cta{display:inline-block;margin-top:10px;padding:9px 16px;
  border:1px solid var(--meltwater);color:var(--meltwater);
  font-family:var(--mono);font-size:.72rem;letter-spacing:.08em;
  text-transform:uppercase;text-decoration:none;border-bottom-width:1px}
.cta:hover,.cta:focus-visible{background:var(--meltwater);
  color:var(--ice-deep);outline:none}

/* ---- contact page ---- */
.page{max-width:620px;padding:36px 0 80px}
.page p{font-size:.9rem;color:rgba(238,244,247,.75);line-height:1.65;
  max-width:56ch}
.page ul{font-size:.9rem;color:rgba(238,244,247,.75);line-height:1.9;
  padding-left:20px;max-width:56ch}
.contact{margin:36px 0 0;padding:28px 0 0;border-top:1px solid var(--rule)}
.contact-lead{font-family:var(--mono);font-size:.68rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--ice-pale);margin:0 0 14px}
.addr{display:inline-block;font-family:var(--mono);
  font-size:clamp(.95rem,3vw,1.3rem);color:var(--meltwater);
  text-decoration:none;letter-spacing:-.01em;
  border-bottom:1px solid rgba(78,168,199,.4);padding-bottom:2px}
.addr:hover,.addr:focus-visible{border-bottom-color:var(--meltwater);
  outline:none}
.copy{display:block;margin-top:20px;padding:8px 15px;background:none;
  border:1px solid var(--rule);border-radius:2px;color:var(--ice-pale);
  font-family:var(--mono);font-size:.68rem;letter-spacing:.09em;
  text-transform:uppercase;cursor:pointer}
.copy:hover{border-color:var(--meltwater);color:var(--meltwater)}
.copy:focus-visible{outline:2px solid var(--meltwater);outline-offset:2px}
.hint{font-size:.78rem;color:rgba(168,198,217,.65);margin-top:10px;
  line-height:1.55;max-width:52ch}
.back{display:inline-block;margin-top:34px;font-family:var(--mono);
  font-size:.72rem;color:var(--ice-pale);text-decoration:none}
.back:hover{color:var(--meltwater)}
.notice{padding:14px 16px;border:1px solid var(--sediment);border-radius:2px;
  color:var(--sediment);font-size:.82rem;margin-bottom:24px}
"""

# Placeholders here are module constants in site_build/__main__.py, because
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
<p>Corrections and suggested sources:
<a class="mail" href="mailto:{CONTACT_EMAIL}?subject=climate-feed">{CONTACT_EMAIL}</a></p>
<a class="cta" href="feedback.html">Send feedback</a>
</div>
</section>
"""

CONTACT_BLOCK = """<div class="contact">
<p class="contact-lead">Email</p>
<a class="addr" href="mailto:{email}?subject=climate-feed%20feedback">{email}</a>
<button class="copy" data-addr="{email}" type="button">Copy address</button>
</div>"""

CONTACT_UNSET = """<div class="notice">No contact address configured. Set
<code>CONTACT_EMAIL</code> in <code>site_build/__main__.py</code>.</div>"""

COPY_JS = """
const b=document.querySelector('.copy');
if(b&&navigator.clipboard){b.addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText(b.dataset.addr);
    const t=b.textContent;b.textContent='Copied';
    setTimeout(()=>b.textContent=t,1600);}catch(e){}});}
else if(b){b.hidden=true;}
"""

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

<div class="page">
<p>This feed is assembled automatically, so mistakes are structural rather
than personal. The most useful things to report:</p>
<ul>
<li>A paper listed here that clearly is not climate science</li>
<li>A source that should be included and is not</li>
<li>Climate work that is being filtered out when it should not be</li>
<li>Dates, authors or venues that look wrong</li>
</ul>
<p>A link or an exact title makes it much faster to trace.</p>

{contact}

<a class="back" href="index.html">&larr; Back to the feed</a>
</div>

<footer>
<span>climate-feed</span>
<span><a href="{repo}">Source &amp; data</a></span>
<span><a href="{site}">{author}</a></span>
</footer>
</div>
<script>{js}</script>
</body></html>"""


print("Applying site update...")

# 1. Prune dead feeds. Checked live 2026-07-20: climateanalytics 404,
#    wri 403, iisd_enb 403, eea 404, grantham_lse parsed but empty.
#    Leaving them in means five failed requests every day, forever.
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

# 2. Site identity.
patch(
    "site_build/__main__.py",
    'OUT = Path("public")\nDB = Path("data/feed.db")',
    'OUT = Path("public")\n'
    'DB = Path("data/feed.db")\n\n'
    "# --- site identity ---------------------------------------------------\n"
    'AUTHOR = "Vasundhara Shaw"\n'
    'AUTHOR_URL = "https://vasundharashaw.github.io"\n'
    'REPO_URL = "https://github.com/VasundharaShaw/climate-feed"\n\n'
    "# This repository is public, so anything here is as visible as the\n"
    "# rendered page. Use an address that is already published elsewhere,\n"
    "# or a forwarding alias you are willing to rotate. Never a private one.\n"
    'CONTACT_EMAIL = ""',
    "add site identity config",
)

# 3. Styles.
patch(
    "site_build/__main__.py",
    "footer{border-top:1px solid var(--rule);padding:28px 0 56px;",
    EXTRA_CSS + "\nfooter{border-top:1px solid var(--rule);padding:28px 0 56px;",
    "add about/contact styles",
)

# 4. About section.
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

# 5. Contact page renderer.
patch(
    "site_build/__main__.py",
    'def main() -> None:\n'
    '    OUT.mkdir(exist_ok=True)\n'
    '    OUT.joinpath("index.html").write_text(render(), encoding="utf-8")\n'
    '    size = OUT.joinpath("index.html").stat().st_size\n'
    '    print(f"wrote public/index.html ({size / 1024:.0f} kB)")',
    "CONTACT_BLOCK = " + repr(CONTACT_BLOCK) + "\n\n"
    "CONTACT_UNSET = " + repr(CONTACT_UNSET) + "\n\n"
    "COPY_JS = " + repr(COPY_JS) + "\n\n"
    "FEEDBACK_PAGE = " + repr(FEEDBACK_PAGE) + "\n\n\n"
    "def render_feedback() -> str:\n"
    '    """Contact page. No form, no relay, no server."""\n'
    "    contact = (CONTACT_BLOCK.format(email=CONTACT_EMAIL)\n"
    "               if CONTACT_EMAIL else CONTACT_UNSET)\n"
    "    return FEEDBACK_PAGE.format(css=CSS, contact=contact, js=COPY_JS,\n"
    "                                repo=REPO_URL, site=AUTHOR_URL,\n"
    "                                author=AUTHOR)\n\n\n"
    "def main() -> None:\n"
    "    OUT.mkdir(exist_ok=True)\n"
    '    OUT.joinpath("index.html").write_text(render(), encoding="utf-8")\n'
    '    OUT.joinpath("feedback.html").write_text(render_feedback(),\n'
    '                                             encoding="utf-8")\n'
    '    for name in ("index.html", "feedback.html"):\n'
    "        kb = OUT.joinpath(name).stat().st_size / 1024\n"
    '        print(f"wrote public/{name} ({kb:.0f} kB)")\n'
    "    if not CONTACT_EMAIL:\n"
    '        print("\\nNote: CONTACT_EMAIL is blank, so there is no way to '
    'reach you.\\n"\n'
    '              "  Set it in site_build/__main__.py and rebuild.")',
    "add contact page renderer",
)

print()
print(f"Changed {len(set(changed))} files." if changed else "Already up to date.")
print("""
Now set your address:

  1. Open site_build/__main__.py
  2. Find:  CONTACT_EMAIL = ""
  3. Paste the address already published on your website
  4. python -m site_build && open public/index.html
""")
