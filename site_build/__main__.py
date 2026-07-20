"""Render the feed as a static site.

Design brief: a daily scan surface for climate researchers and policy
readers. One job — see what appeared today, decide what to open.

The organising metaphor is an ice core. Climate science reads its own past
by drilling layers; each day of publications becomes a stratum in a column
down the left edge, thickness set by volume, descending back through time.
It is the one bold element; everything else stays quiet.

No web fonts. A site that publishes its own gram-level CO2e per build has
no business shipping 60 kB of typefaces to every visitor. Distinctiveness
comes from scale, rule weight, and the core column instead.
"""

from __future__ import annotations

import html
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("public")
DB = Path("data/feed.db")

# --- site identity ---------------------------------------------------
AUTHOR = "Vasundhara Shaw"
AUTHOR_URL = "https://vasundharashaw.github.io"
REPO_URL = "https://github.com/VasundharaShaw/climate-feed"

# This repository is public, so anything here is as visible as the
# rendered page. Use an address that is already published elsewhere,
# or a forwarding alias you are willing to rotate. Never a private one.
CONTACT_EMAIL = "vasundhara.shaw@fiz-karlsruhe.de"
DAYS_SHOWN = 21
MAX_PER_DAY = 60

CSS = """
:root{
  --ice-deep:#0A1A24;      /* deep ice, near-black with blue in it */
  --ice-mid:#16394F;       /* compressed layer */
  --ice-pale:#A8C6D9;      /* firn */
  --snow:#EEF4F7;          /* fresh surface, cool not cream */
  --meltwater:#4EA8C7;     /* research accent */
  --sediment:#A87C4F;      /* policy accent, trapped debris */
  --rule:rgba(168,198,217,.22);
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}
  *{animation:none!important;transition:none!important}}
body{
  margin:0;background:var(--ice-deep);color:var(--snow);
  font-family:var(--sans);line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
a{color:inherit}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px}

/* ---- masthead ---- */
header{border-bottom:1px solid var(--rule);padding:56px 0 28px;margin-bottom:8px}
h1{
  font-size:clamp(2.4rem,6vw,4.2rem);line-height:.95;margin:0 0 18px;
  font-weight:800;letter-spacing:-.045em;
}
h1 .sub{display:block;color:var(--ice-pale);font-weight:300;
  font-size:clamp(.9rem,2vw,1.05rem);letter-spacing:.16em;
  text-transform:uppercase;margin-top:16px}
.stats{display:flex;flex-wrap:wrap;gap:28px;font-family:var(--mono);
  font-size:.76rem;color:var(--ice-pale);margin-top:24px}
.stats b{display:block;color:var(--snow);font-size:1.5rem;font-weight:600;
  letter-spacing:-.02em;margin-bottom:2px}

/* ---- search ---- */
.search{margin:28px 0 0;position:relative}
.search input{
  width:100%;padding:13px 16px;background:rgba(168,198,217,.07);
  border:1px solid var(--rule);border-radius:2px;color:var(--snow);
  font-family:var(--mono);font-size:.85rem;
}
.search input:focus{outline:2px solid var(--meltwater);outline-offset:1px;
  background:rgba(168,198,217,.11)}
.search input::placeholder{color:rgba(168,198,217,.5)}

/* ---- the core ---- */
.core-layout{display:grid;grid-template-columns:64px 1fr;gap:32px;
  padding:40px 0 80px;align-items:start}
.core{position:sticky;top:24px;display:flex;flex-direction:column;gap:2px}
.core-label{font-family:var(--mono);font-size:.58rem;letter-spacing:.14em;
  color:rgba(168,198,217,.55);text-transform:uppercase;margin-bottom:8px;
  writing-mode:vertical-rl;height:80px}
.stratum{
  display:block;border-radius:1px;background:var(--ice-mid);
  border-left:3px solid var(--meltwater);
  transition:background .18s,border-color .18s;
  position:relative;
}
.stratum:hover,.stratum:focus-visible{background:var(--meltwater);
  border-color:var(--snow);outline:none}
.stratum span{position:absolute;left:100%;margin-left:8px;top:50%;
  transform:translateY(-50%);font-family:var(--mono);font-size:.6rem;
  color:var(--ice-pale);white-space:nowrap;opacity:0;pointer-events:none;
  transition:opacity .18s}
.stratum:hover span,.stratum:focus-visible span{opacity:1}

/* ---- days ---- */
.day{margin-bottom:52px;scroll-margin-top:24px}
.day-head{display:flex;align-items:baseline;gap:14px;
  padding-bottom:10px;margin-bottom:4px;border-bottom:1px solid var(--rule)}
.day-date{font-family:var(--mono);font-size:1rem;letter-spacing:.04em;
  color:var(--snow);font-weight:600}
.day-count{font-family:var(--mono);font-size:.7rem;color:var(--ice-pale)}
.day-depth{margin-left:auto;font-family:var(--mono);font-size:.62rem;
  color:rgba(168,198,217,.45)}

/* ---- entries ---- */
article{padding:16px 0;border-bottom:1px solid rgba(168,198,217,.08)}
article:last-child{border-bottom:none}
article h2{margin:0 0 7px;font-size:1.02rem;line-height:1.34;font-weight:500;
  letter-spacing:-.008em}
article h2 a{text-decoration:none;background-image:linear-gradient(var(--meltwater),var(--meltwater));
  background-size:0 1px;background-position:0 100%;background-repeat:no-repeat;
  transition:background-size .2s}
article h2 a:hover,article h2 a:focus-visible{background-size:100% 1px;
  color:var(--meltwater);outline:none}
.meta{font-family:var(--mono);font-size:.7rem;color:var(--ice-pale);
  display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.meta .authors{color:rgba(238,244,247,.72)}
.tag{padding:1px 7px;border:1px solid currentColor;border-radius:1px;
  font-size:.6rem;letter-spacing:.1em;text-transform:uppercase}
.tag.research{color:var(--meltwater)}
.tag.policy{color:var(--sediment)}
.tag.oa{color:var(--ice-pale);opacity:.7}
.abstract{margin:9px 0 0;font-size:.86rem;color:rgba(238,244,247,.62);
  line-height:1.55;max-width:68ch}


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

footer{border-top:1px solid var(--rule);padding:28px 0 56px;
  font-family:var(--mono);font-size:.68rem;color:rgba(168,198,217,.6);
  display:flex;flex-wrap:wrap;gap:20px;justify-content:space-between}
footer a{color:var(--ice-pale)}
.empty{padding:60px 0;color:var(--ice-pale);font-family:var(--mono);
  font-size:.85rem}

@media (max-width:720px){
  .core-layout{grid-template-columns:1fr;gap:0}
  .core{display:none}
}
"""

SEARCH_JS = """
const q=document.getElementById('q'),arts=[...document.querySelectorAll('article')],
      days=[...document.querySelectorAll('.day')];
q.addEventListener('input',()=>{
  const v=q.value.trim().toLowerCase();
  arts.forEach(a=>{a.hidden=v&&!a.dataset.s.includes(v)});
  days.forEach(d=>{d.hidden=![...d.querySelectorAll('article')].some(a=>!a.hidden)});
});
"""


def esc(s) -> str:
    return html.escape(str(s or ""))


def load(conn) -> tuple[list, dict]:
    rows = conn.execute(
        """SELECT title, abstract, authors, venue, published_date, url,
                  is_oa, kind, sources, score, tier
           FROM works
           WHERE tier IN ('accept','uncertain') AND published_date IS NOT NULL
           ORDER BY published_date DESC, score DESC"""
    ).fetchall()

    totals = dict(conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(tier='accept'),0) FROM works"
    ).fetchone() and {} or {})
    return rows, totals


def render() -> str:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT title, abstract, authors, venue, published_date, url,
                  is_oa, kind, score, tier
           FROM works
           WHERE tier IN ('accept','uncertain')
             AND published_date IS NOT NULL
             AND published_date <= date('now')
           ORDER BY published_date DESC, score DESC"""
    ).fetchall()

    total_all = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    kept = len(rows)
    last_run = conn.execute(
        "SELECT co2e_g, finished_at FROM runs WHERE finished_at IS NOT NULL "
        "ORDER BY id DESC LIMIT 1").fetchone()

    by_day: dict[str, list] = defaultdict(list)
    for r in rows:
        by_day[r["published_date"]].append(r)

    days = sorted(by_day, reverse=True)[:DAYS_SHOWN]
    peak = max((len(by_day[d]) for d in days), default=1)

    # --- core column: one stratum per day, height by volume ---
    strata = []
    for i, d in enumerate(days):
        n = len(by_day[d])
        h = max(6, round(9 + 52 * (n / peak)))
        opacity = 0.35 + 0.65 * (1 - i / max(len(days), 1))
        strata.append(
            f'<a class="stratum" href="#d{d}" style="height:{h}px;'
            f'opacity:{opacity:.2f}" aria-label="{d}, {n} works">'
            f'<span>{d} · {n}</span></a>'
        )

    # --- day sections ---
    sections = []
    for i, d in enumerate(days):
        items = by_day[d][:MAX_PER_DAY]
        entries = []
        for r in items:
            try:
                authors = json.loads(r["authors"] or "[]")
            except json.JSONDecodeError:
                authors = []
            alist = ", ".join(authors[:3])
            if len(authors) > 3:
                alist += f" +{len(authors) - 3}"

            tags = [f'<span class="tag {r["kind"]}">{esc(r["kind"])}</span>']
            if r["is_oa"]:
                tags.append('<span class="tag oa">open</span>')

            abstract = (r["abstract"] or "")[:260]
            if r["abstract"] and len(r["abstract"]) > 260:
                abstract += "…"

            haystack = esc(f'{r["title"]} {alist} {r["venue"]} {abstract}').lower()
            entries.append(f"""<article data-s="{haystack}">
<h2><a href="{esc(r['url'])}" rel="noopener">{esc(r['title'])}</a></h2>
<div class="meta"><span class="authors">{esc(alist) or '—'}</span>
<span>{esc(r['venue']) or '—'}</span>{''.join(tags)}</div>
{f'<p class="abstract">{esc(abstract)}</p>' if abstract else ''}
</article>""")

        more = (f'<div class="day-depth">showing {MAX_PER_DAY} of '
                f'{len(by_day[d])}</div>' if len(by_day[d]) > MAX_PER_DAY
                else f'<div class="day-depth">layer {i + 1}</div>')

        sections.append(f"""<section class="day" id="d{d}">
<div class="day-head"><span class="day-date">{d}</span>
<span class="day-count">{len(by_day[d])} works</span>{more}</div>
{''.join(entries)}
</section>""")

    co2 = f"{last_run['co2e_g']:.2f} g" if last_run and last_run["co2e_g"] else "—"
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body = "".join(sections) or '<p class="empty">No works yet. Run the ingest.</p>'

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>climate-feed — new climate research and policy, daily</title>
<meta name="description" content="A daily layer of new climate science research and policy documents, drawn from OpenAlex and arXiv.">
<style>{CSS}</style>
</head><body>
<div class="wrap">
<header>
<h1>climate&#8203;-feed<span class="sub">New climate research &amp; policy, drilled daily</span></h1>
<div class="stats">
<div><b>{kept:,}</b>works in the core</div>
<div><b>{len(days)}</b>days of layers</div>
<div><b>{total_all:,}</b>records screened</div>
<div><b>{co2}</b>last build</div>
</div>
<div class="search"><input id="q" type="search" placeholder="Filter by title, author, journal…" aria-label="Filter works"></div>
</header>

<div class="core-layout">
<nav class="core" aria-label="Jump to day">
<div class="core-label">Depth →</div>
{''.join(strata)}
</nav>
<main>{body}</main>
</div>


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

<footer>
<span>Built {built}</span>
<span>Sources: OpenAlex · arXiv</span>
<span><a href="{REPO_URL}">Source &amp; data</a> &middot; <a href="feedback.html">Feedback</a></span>
</footer>
</div>
<script>{SEARCH_JS}</script>
</body></html>"""


CONTACT_BLOCK = '<div class="contact">\n<p class="contact-lead">Email</p>\n<a class="addr" href="mailto:{email}?subject=climate-feed%20feedback">{email}</a>\n<button class="copy" data-addr="{email}" type="button">Copy address</button>\n</div>'

CONTACT_UNSET = '<div class="notice">No contact address configured. Set\n<code>CONTACT_EMAIL</code> in <code>site_build/__main__.py</code>.</div>'

COPY_JS = "\nconst b=document.querySelector('.copy');\nif(b&&navigator.clipboard){b.addEventListener('click',async()=>{\n  try{await navigator.clipboard.writeText(b.dataset.addr);\n    const t=b.textContent;b.textContent='Copied';\n    setTimeout(()=>b.textContent=t,1600);}catch(e){}});}\nelse if(b){b.hidden=true;}\n"

FEEDBACK_PAGE = '<!doctype html>\n<html lang="en"><head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>Feedback &mdash; climate-feed</title>\n<meta name="description" content="Report a problem or suggest a source for climate-feed.">\n<style>{css}</style>\n</head><body>\n<div class="wrap">\n<header>\n<h1>Feedback<span class="sub">Tell me what is broken or missing</span></h1>\n</header>\n\n<div class="page">\n<p>This feed is assembled automatically, so mistakes are structural rather\nthan personal. The most useful things to report:</p>\n<ul>\n<li>A paper listed here that clearly is not climate science</li>\n<li>A source that should be included and is not</li>\n<li>Climate work that is being filtered out when it should not be</li>\n<li>Dates, authors or venues that look wrong</li>\n</ul>\n<p>A link or an exact title makes it much faster to trace.</p>\n\n{contact}\n\n<a class="back" href="index.html">&larr; Back to the feed</a>\n</div>\n\n<footer>\n<span>climate-feed</span>\n<span><a href="{repo}">Source &amp; data</a></span>\n<span><a href="{site}">{author}</a></span>\n</footer>\n</div>\n<script>{js}</script>\n</body></html>'


def render_feedback() -> str:
    """Contact page. No form, no relay, no server."""
    contact = (CONTACT_BLOCK.format(email=CONTACT_EMAIL)
               if CONTACT_EMAIL else CONTACT_UNSET)
    return FEEDBACK_PAGE.format(css=CSS, contact=contact, js=COPY_JS,
                                repo=REPO_URL, site=AUTHOR_URL,
                                author=AUTHOR)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    OUT.joinpath("index.html").write_text(render(), encoding="utf-8")
    OUT.joinpath("feedback.html").write_text(render_feedback(),
                                             encoding="utf-8")
    for name in ("index.html", "feedback.html"):
        kb = OUT.joinpath(name).stat().st_size / 1024
        print(f"wrote public/{name} ({kb:.0f} kB)")
    if not CONTACT_EMAIL:
        print("\nNote: CONTACT_EMAIL is blank, so there is no way to reach you.\n"
              "  Set it in site_build/__main__.py and rebuild.")


if __name__ == "__main__":
    main()
