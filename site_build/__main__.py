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
  /* Earth from orbit: ocean, shelf, chlorophyll. Dark ground because the
     imagery is of a lit planet against space -- and because a dark page
     costs less energy to display on OLED, which this site cares about. */
  --deep:#04171C;          /* deep ocean at night */
  --abyss:#0B2B33;         /* raised surfaces */
  --shelf:#12505A;         /* continental shelf */
  --pale:#9DC7C4;          /* pale sea-glass, secondary text */
  --snow:#EAF5F2;          /* primary text */
  --ocean:#3E9FD4;         /* research accent, hydrosphere blue */
  --bloom:#42C08A;         /* policy accent, chlorophyll green */
  --rule:rgba(157,199,196,.2);
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}
  *{animation:none!important;transition:none!important}}
body{
  margin:0;background:var(--deep);color:var(--snow);
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
h1 .sub{display:block;color:var(--pale);font-weight:300;
  font-size:clamp(.9rem,2vw,1.05rem);letter-spacing:.16em;
  text-transform:uppercase;margin-top:16px}
.stats{display:flex;flex-wrap:wrap;gap:28px;font-family:var(--mono);
  font-size:.76rem;color:var(--pale);margin-top:24px}
.stats b{display:block;color:var(--snow);font-size:1.5rem;font-weight:600;
  letter-spacing:-.02em;margin-bottom:2px}

/* ---- search ---- */
.search{margin:28px 0 0;position:relative}
.search input{
  width:100%;padding:13px 16px;background:rgba(157,199,196,.07);
  border:1px solid var(--rule);border-radius:2px;color:var(--snow);
  font-family:var(--mono);font-size:.85rem;
}
.search input:focus{outline:2px solid var(--ocean);outline-offset:1px;
  background:rgba(157,199,196,.11)}
.search input::placeholder{color:rgba(157,199,196,.5)}

/* ---- the core ---- */
.core-layout{display:grid;grid-template-columns:64px 1fr;gap:32px;
  padding:40px 0 80px;align-items:start}
.core{position:sticky;top:24px;display:flex;flex-direction:column;gap:2px}
.core-label{font-family:var(--mono);font-size:.58rem;letter-spacing:.14em;
  color:rgba(157,199,196,.55);text-transform:uppercase;margin-bottom:8px;
  writing-mode:vertical-rl;height:80px}
.stratum{
  display:block;border-radius:1px;background:var(--shelf);
  border-left:3px solid var(--ocean);
  transition:background .18s,border-color .18s;
  position:relative;
}
.stratum:hover,.stratum:focus-visible{background:var(--ocean);
  border-color:var(--snow);outline:none}
.stratum span{position:absolute;left:100%;margin-left:8px;top:50%;
  transform:translateY(-50%);font-family:var(--mono);font-size:.6rem;
  color:var(--pale);white-space:nowrap;opacity:0;pointer-events:none;
  transition:opacity .18s}
.stratum:hover span,.stratum:focus-visible span{opacity:1}

/* ---- days ---- */
.day{margin-bottom:52px;scroll-margin-top:24px}
.day-head{display:flex;align-items:baseline;gap:14px;
  padding-bottom:10px;margin-bottom:4px;border-bottom:1px solid var(--rule)}
.day-date{font-family:var(--mono);font-size:1rem;letter-spacing:.04em;
  color:var(--snow);font-weight:600}
.day-count{font-family:var(--mono);font-size:.7rem;color:var(--pale)}
.day-depth{margin-left:auto;font-family:var(--mono);font-size:.62rem;
  color:rgba(157,199,196,.45)}

/* ---- entries ---- */
article{padding:16px 0;border-bottom:1px solid rgba(157,199,196,.08)}
article:last-child{border-bottom:none}
article h2{margin:0 0 7px;font-size:1.02rem;line-height:1.34;font-weight:500;
  letter-spacing:-.008em}
article h2 a{text-decoration:none;background-image:linear-gradient(var(--ocean),var(--ocean));
  background-size:0 1px;background-position:0 100%;background-repeat:no-repeat;
  transition:background-size .2s}
article h2 a:hover,article h2 a:focus-visible{background-size:100% 1px;
  color:var(--ocean);outline:none}
.meta{font-family:var(--mono);font-size:.7rem;color:var(--pale);
  display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.meta .authors{color:rgba(234,245,242,.72)}
.tag{padding:1px 7px;border:1px solid currentColor;border-radius:1px;
  font-size:.6rem;letter-spacing:.1em;text-transform:uppercase}
.tag.research{color:var(--ocean)}
.tag.policy{color:var(--bloom)}
.tag.oa{color:var(--pale);opacity:.7}
.abstract{margin:9px 0 0;font-size:.86rem;color:rgba(234,245,242,.62);
  line-height:1.55;max-width:68ch}


.lede{margin:26px 0 0;max-width:60ch}
.lede p{margin:0 0 12px;font-size:.98rem;line-height:1.62;
  color:rgba(234,245,242,.82)}
.lede p+p{font-size:.9rem;color:rgba(157,199,196,.78)}
@media(max-width:640px){.lede p{font-size:.92rem}}

/* ---- hero: Earth from orbit ---- */
.hero{position:relative;margin:0 0 4px;border-bottom:1px solid var(--rule)}
.hero-img{display:block;width:100%;height:clamp(200px,34vh,360px);
  object-fit:cover;object-position:left center;
  filter:saturate(1.05) contrast(1.03)}
.hero-veil{position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(to bottom,rgba(4,23,28,.22) 0%,
    rgba(4,23,28,0) 38%,rgba(4,23,28,.5) 78%,rgba(4,23,28,.95) 100%)}
.hero-credit{position:absolute;right:11px;bottom:7px;display:flex;
  flex-direction:column;align-items:flex-end;gap:2px;font-family:var(--mono);
  font-size:.56rem;letter-spacing:.05em;line-height:1.4;text-align:right}
.hero-credit a{color:rgba(234,245,242,.6);text-decoration:none}
.hero-credit a:hover,.hero-credit a:focus-visible{color:var(--snow);
  outline:none}

.figure{margin:32px 0 0;border-top:1px solid var(--rule);padding-top:26px}
.figure img{display:block;width:100%;height:auto;border-radius:2px}
.figure figcaption{margin-top:10px;font-family:var(--mono);font-size:.66rem;
  line-height:1.6;color:rgba(157,199,196,.7)}
.figure figcaption a{color:var(--pale)}

.calc{font-family:var(--mono);font-size:.74rem;line-height:1.75;
  color:var(--pale);background:var(--abyss);border:1px solid var(--rule);
  border-radius:2px;padding:14px 16px;margin:0 0 12px;overflow-x:auto;
  white-space:pre}
.about a.jump{color:var(--ocean);text-decoration:none;
  border-bottom:1px solid rgba(62,159,212,.35)}

/* ---- page tabs ---- */
.tabs{display:flex;gap:2px;margin:26px 0 0;border-bottom:1px solid var(--rule)}
.tab{padding:9px 15px 8px;font-family:var(--mono);font-size:.72rem;
  letter-spacing:.1em;text-transform:uppercase;text-decoration:none;
  color:var(--pale);border-bottom:2px solid transparent;margin-bottom:-1px}
.tab:hover{color:var(--snow)}
.tab:focus-visible{outline:2px solid var(--ocean);outline-offset:-2px}
.tab.on{color:var(--ocean);border-bottom-color:var(--ocean)}
.tag.score{color:var(--pale);border-color:var(--rule);font-variant-numeric:
  tabular-nums}

/* ---- about + colophon ---- */
.about{border-top:1px solid var(--rule);padding:44px 0 8px;
  display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:36px}
.about h3{font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;
  color:var(--pale);margin:0 0 12px;font-family:var(--mono);font-weight:500}
.about p{margin:0 0 10px;font-size:.85rem;color:rgba(234,245,242,.72);
  line-height:1.6;max-width:46ch}
.about a{color:var(--ocean);text-decoration:none;
  border-bottom:1px solid rgba(62,159,212,.35)}
.about a:hover,.about a:focus-visible{border-bottom-color:var(--ocean);
  outline:none}
.about .mail{font-family:var(--mono);font-size:.8rem;word-break:break-all}
.cta{display:inline-block;margin-top:10px;padding:9px 16px;
  border:1px solid var(--ocean);color:var(--ocean);
  font-family:var(--mono);font-size:.72rem;letter-spacing:.08em;
  text-transform:uppercase;text-decoration:none;border-bottom-width:1px}
.cta:hover,.cta:focus-visible{background:var(--ocean);
  color:var(--deep);outline:none}

/* ---- contact page ---- */
.page{max-width:620px;padding:36px 0 80px}
.page p{font-size:.9rem;color:rgba(234,245,242,.75);line-height:1.65;
  max-width:56ch}
.page ul{font-size:.9rem;color:rgba(234,245,242,.75);line-height:1.9;
  padding-left:20px;max-width:56ch}
.contact{margin:36px 0 0;padding:28px 0 0;border-top:1px solid var(--rule)}
.contact-lead{font-family:var(--mono);font-size:.68rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--pale);margin:0 0 14px}
.addr{display:inline-block;font-family:var(--mono);
  font-size:clamp(.95rem,3vw,1.3rem);color:var(--ocean);
  text-decoration:none;letter-spacing:-.01em;
  border-bottom:1px solid rgba(62,159,212,.4);padding-bottom:2px}
.addr:hover,.addr:focus-visible{border-bottom-color:var(--ocean);
  outline:none}
.copy{display:block;margin-top:20px;padding:8px 15px;background:none;
  border:1px solid var(--rule);border-radius:2px;color:var(--pale);
  font-family:var(--mono);font-size:.68rem;letter-spacing:.09em;
  text-transform:uppercase;cursor:pointer}
.copy:hover{border-color:var(--ocean);color:var(--ocean)}
.copy:focus-visible{outline:2px solid var(--ocean);outline-offset:2px}
.hint{font-size:.78rem;color:rgba(157,199,196,.65);margin-top:10px;
  line-height:1.55;max-width:52ch}
.back{display:inline-block;margin-top:34px;font-family:var(--mono);
  font-size:.72rem;color:var(--pale);text-decoration:none}
.back:hover{color:var(--ocean)}
.notice{padding:14px 16px;border:1px solid var(--bloom);border-radius:2px;
  color:var(--bloom);font-size:.82rem;margin-bottom:24px}

footer{border-top:1px solid var(--rule);padding:28px 0 56px;
  font-family:var(--mono);font-size:.68rem;color:rgba(157,199,196,.6);
  display:flex;flex-wrap:wrap;gap:20px;justify-content:space-between}
footer a{color:var(--pale)}
.empty{padding:60px 0;color:var(--pale);font-family:var(--mono);
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


CREDITS = Path("public/img/credits.json")


def _images() -> dict:
    """Manifest written by fetch_images.py. Absent is fine: no images."""
    try:
        return json.loads(CREDITS.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _srcset(files: list[dict], mime: str) -> str:
    return ", ".join(f"img/{f['path']} {f['width']}w"
                     for f in files if f["type"] == mime)


def render_hero(imgs: dict) -> str:
    """Full-bleed banner. Eager-loaded: it is the first thing on screen, so
    lazy-loading it would only guarantee a visible pop-in.

    The image is a composite of two separately licensed works, so every
    source is credited in place rather than buried in a colophon."""
    m = imgs.get("hero")
    if not m:
        return ""
    jpg = next((f for f in m["files"] if f["type"] == "image/jpeg"), None)
    if not jpg:
        return ""
    credits = "\n".join(
        f'<a href="{esc(c["url"])}" rel="noopener">{esc(c["text"])}</a>'
        for c in m.get("credits", []))
    return f"""<div class="hero">
<picture>
<source type="image/webp" srcset="{_srcset(m['files'], 'image/webp')}"
 sizes="100vw">
<img class="hero-img" src="img/{jpg['path']}"
 width="{m['width']}" height="{m['height']}"
 alt="{esc(m.get('alt') or m['title'])}"
 fetchpriority="high" decoding="async">
</picture>
<div class="hero-veil"></div>
<div class="hero-credit">
{credits}
</div>
</div>"""


def render_figure(imgs: dict, nasa_id: str) -> str:
    """Inline figure, lazy-loaded because it sits below the fold."""
    m = imgs.get(nasa_id)
    if not m:
        return ""
    jpg = next((f for f in m["files"] if f["type"] == "image/jpeg"), None)
    if not jpg:
        return ""
    desc = (m.get("description") or "")[:260]
    if m.get("description") and len(m["description"]) > 260:
        desc += "\u2026"
    return f"""<figure class="figure">
<picture>
<source type="image/webp" srcset="{_srcset(m['files'], 'image/webp')}"
 sizes="(max-width:720px) 100vw, 1080px">
<img src="img/{jpg['path']}" width="{m['width']}" height="{m['height']}"
 alt="{esc(m['title'])}" loading="lazy" decoding="async">
</picture>
<figcaption>{esc(m['title'])} &mdash; {esc(desc)}<br>
<a href="{esc(m['page'])}" rel="noopener">{esc(m['credit'])} &middot; {esc(nasa_id)}</a>
</figcaption>
</figure>"""


WINDOW_DAYS = 90   # calendar days back from today, not "days that have papers"


def _entry(r, show_score: bool = False) -> str:
    """One work. Identical on both pages except for the score badge."""
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
    if show_score:
        tags.append(f'<span class="tag score">{r["score"]:.1f}</span>')

    abstract = (r["abstract"] or "")[:260]
    if r["abstract"] and len(r["abstract"]) > 260:
        abstract += "\u2026"

    haystack = esc(f'{r["title"]} {alist} {r["venue"]} {abstract}').lower()
    return f"""<article data-s="{haystack}">
<h2><a href="{esc(r['url'])}" rel="noopener">{esc(r['title'])}</a></h2>
<div class="meta"><span class="authors">{esc(alist) or '—'}</span>
<span>{esc(r['venue']) or '—'}</span>{''.join(tags)}</div>
{f'<p class="abstract">{esc(abstract)}</p>' if abstract else ''}
</article>"""


def _has_region(conn) -> bool:
    """The site must render against whatever schema it finds. A fresh
    checkout may not have run the ingest yet, and the committed database
    predates the region column."""
    return any(r[1] == "region"
               for r in conn.execute("PRAGMA table_info(works)"))


def _fetch(conn, tier: str, region: str | None = None):
    """Works of one tier inside the window, optionally one region.

    Future dates are excluded: OpenAlex stores 1 January when only a year is
    known, which otherwise sorts unpublished work to the top."""
    if region and not _has_region(conn):
        return []

    where = ["tier = ?", "published_date IS NOT NULL",
             "published_date <= date('now')",
             "published_date >= date('now', ?)"]
    params = [tier, f"-{WINDOW_DAYS} days"]
    if region:
        where.insert(1, "region = ?")
        params.insert(1, region)

    return conn.execute(
        "SELECT title, abstract, authors, venue, published_date, url, "
        "       is_oa, kind, score, tier "
        "FROM works WHERE " + " AND ".join(where) +
        " ORDER BY published_date DESC, score DESC",
        params,
    ).fetchall()


def _feed(rows, show_score: bool = False) -> tuple[str, str, int]:
    """Returns (strata rail, day sections, number of days with content)."""
    by_day: dict[str, list] = defaultdict(list)
    for r in rows:
        by_day[r["published_date"]].append(r)
    days = sorted(by_day, reverse=True)
    peak = max((len(by_day[d]) for d in days), default=1)

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

    sections = []
    for i, d in enumerate(days):
        items = by_day[d][:MAX_PER_DAY]
        more = (f'<div class="day-depth">showing {MAX_PER_DAY} of '
                f'{len(by_day[d])}</div>' if len(by_day[d]) > MAX_PER_DAY
                else f'<div class="day-depth">layer {i + 1}</div>')
        sections.append(f"""<section class="day" id="d{d}">
<div class="day-head"><span class="day-date">{d}</span>
<span class="day-count">{len(by_day[d])} works</span>{more}</div>
{''.join(_entry(r, show_score) for r in items)}
</section>""")

    return "".join(strata), "".join(sections), len(days)


def _nav(here: str) -> str:
    items = [("index.html", "Feed"), ("germany.html", "Germany"),
             ("uncertain.html", "Uncertain"), ("feedback.html", "Feedback")]
    return '<nav class="tabs">' + "".join(
        f'<span class="tab on">{label}</span>' if href == here
        else f'<a class="tab" href="{href}">{label}</a>'
        for href, label in items) + "</nav>"


def _shell(*, title: str, desc: str, head: str, stats: str, strata: str,
           body: str, here: str, about: str, hero: str = "") -> str:
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{esc(desc)}">
<style>{CSS}</style>
</head><body>
{hero}
<div class="wrap">
<header>
{head}
{_nav(here)}
{stats}
<div class="search"><input id="q" type="search" placeholder="Filter by title, author, journal…" aria-label="Filter works"></div>
</header>

<div class="core-layout">
<nav class="core" aria-label="Jump to day">
<div class="core-label">Depth →</div>
{strata}
</nav>
<main>{body}</main>
</div>

{about}

<footer>
<span>Built {built}</span>
<span><a href="{REPO_URL}">Source &amp; data</a> &middot; <a href="feedback.html">Feedback</a></span>
<span><a href="{AUTHOR_URL}">{AUTHOR}</a></span>
</footer>
</div>
<script>{SEARCH_JS}</script>
</body></html>"""



def emissions_note(last_run) -> str:
    """Show the actual arithmetic, with the coefficients derived from the
    stored run rather than repeated here. Hardcoding them would let this
    page drift out of step with ingest/run.py the moment either changed."""
    if not last_run or not last_run["bytes_in"] or not last_run["co2e_g"]:
        return ""

    mb = last_run["bytes_in"] / 1e6
    gb = last_run["bytes_in"] / 1e9
    g = last_run["co2e_g"]
    kwh = last_run["energy_kwh"]
    if not kwh:
        # Run predates the energy column. Show the endpoints rather than
        # dropping the explanation entirely.
        return f"""<section class="about" id="emissions">
<div>
<h3>How the figure is calculated</h3>
<p>Every HTTP response during a run is weighed, and the total is
multiplied by an energy intensity for network transfer and then by a grid
carbon intensity. The most recent run moved {mb:,.1f} MB and came to
{g:.2f} g CO&#8322;e. The byte count is measured; both coefficients are
assumptions.</p>
</div>
<div>
<h3>What it leaves out</h3>
<p>This is the transfer cost of fetching records and nothing else. It
excludes the build runner\u2019s own electricity, which for a job of this
length is likely larger. It excludes serving these pages to you, which at
any real readership dominates everything else. It excludes embodied
carbon, and the work done upstream answering the queries.</p>
<p>Treat it as a floor on one component, not as this site\u2019s
footprint.</p>
</div>
</section>"""

    kwh_per_gb = kwh / gb if gb else 0
    g_per_kwh = g / kwh if kwh else 0

    return f"""<section class="about" id="emissions">
<div>
<h3>How the figure is calculated</h3>
<p>Every HTTP response during a run is weighed, and the total is multiplied
by an energy intensity for network transfer and then by a grid carbon
intensity. The most recent run:</p>
<pre class="calc">{mb:,.1f} MB transferred
  &times; {kwh_per_gb:g} kWh/GB      network transfer intensity
  = {kwh:.6f} kWh
  &times; {g_per_kwh:g} gCO&#8322;e/kWh   grid carbon intensity
  = {g:.2f} g CO&#8322;e</pre>
<p>The byte count is measured. Both coefficients are assumptions, and
both are cited below so you can judge them.</p>
</div>
<div>
<h3>Where the coefficients come from</h3>
<p>The transfer intensity is the 2015 estimate from Aslan, Mayers, Koomey
and France, <a href="https://doi.org/10.1111/jiec.12630">Electricity
Intensity of Internet Data Transmission</a> (Journal of Industrial Ecology
22(4), 785&ndash;798). It covers core and fixed-line access networks only,
not data centres and not your device.</p>
<p>That paper also finds the figure has halved roughly every two years since
2000. Applied unadjusted a decade later it is therefore too high, probably
by an order of magnitude. It is kept as a conservative upper bound rather
than a best estimate, and published estimates for this quantity span several
orders of magnitude depending on where the boundary is drawn.</p>
<p>The grid intensity follows the <a
href="https://www.eea.europa.eu/en/analysis/indicators/greenhouse-gas-emission-intensity-of-1">European
Environment Agency</a>, whose EU-27 average was around 230 gCO&#8322;e/kWh
in 2020 and has fallen since. The average hides a wide spread &mdash; Poland
near 700, Sweden and Norway near zero &mdash; and this build runs on
infrastructure whose location is not disclosed.</p>
</div>
<div>
<h3>What it leaves out</h3>
<p>This is the transfer cost of fetching records, and nothing else. It
excludes the electricity the build runner itself consumes, which for a job
of this length is likely larger than the number above. It excludes serving
these pages to you, which at any real readership dominates everything else.
It excludes the hardware's embodied carbon, and the work done by OpenAlex
and arXiv answering the queries.</p>
<p>Treat it as a floor on one component, not as this site's footprint.
Replacing both coefficients with direct measurement is the obvious
improvement.</p>
</div>
</section>"""


def render() -> str:
    """The feed proper: accepted works only."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = _fetch(conn, "accept")
    n_uncertain = conn.execute(
        "SELECT COUNT(*) FROM works WHERE tier='uncertain' "
        "AND published_date <= date('now') "
        "AND published_date >= date('now', ?)",
        (f"-{WINDOW_DAYS} days",)).fetchone()[0]
    total_all = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    last_run = conn.execute(
        "SELECT co2e_g, bytes_in, energy_kwh, http_requests, finished_at "
        "FROM runs WHERE finished_at IS NOT NULL "
        "ORDER BY id DESC LIMIT 1").fetchone()

    strata, body, n_days = _feed(rows)
    co2 = f"{last_run['co2e_g']:.2f} g" if last_run and last_run["co2e_g"] else "—"

    imgs = _images()
    hero_note = esc(imgs.get("hero", {}).get("note", ""))

    stats = f"""<div class="stats">
<div><b>{len(rows):,}</b>works accepted</div>
<div><b>{n_days}</b>days with new work</div>
<div><b>{total_all:,}</b>records screened</div>
<div><a href="#emissions"><b>{co2}</b>last build transfer</a></div>
</div>"""

    head = ('<h1>climate&#8203;-feed<span class="sub">New climate research '
            '&amp; policy, drilled daily</span></h1>\n'
            f'<div class="lede">\n<p>{LEDE}</p>\n<p>{LEDE_2}</p>\n</div>')

    about = f"""<section class="about" id="about">
<div>
<h3>The banner</h3>
<p>{hero_note}</p>
</div>
<div>
<h3>What this is</h3>
<p>A daily layer of new climate research and policy analysis, pulled
automatically from OpenAlex, arXiv and a set of policy newsrooms. Every
item is scored for climate relevance before it appears.</p>
<p>Nothing here is hand-curated. If something looks wrong, it probably is.</p>
</div>
<div>
<h3>How scoring works</h3>
<p>A weighted lexicon runs over title and abstract. Decisive terms score
high, ambient ones only count in combination, and vocabulary borrowed by
other fields scores negative, so carbon nanotubes and tumour studies do not
drift in. Title matches count double.</p>
<p>Above 2.5 an item is accepted. Below 0.8 it is rejected. In between it
lands in <a href="uncertain.html">uncertain</a>, published separately.</p>
</div>
<div>
<h3>How it runs</h3>
<p>One scheduled job per day on GitHub Actions, rendering a static page. No
server runs between builds, so this site draws no power while you are not
reading it.</p>
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
</section>"""
    about += emissions_note(last_run)

    return _shell(
        title="climate-feed — new climate research and policy, daily",
        desc=("A daily layer of new climate science research and policy "
              "documents, drawn from OpenAlex, arXiv and policy newsrooms."),
        head=head, stats=stats, strata=strata, body=body or
        '<p class="empty">No works yet. Run the ingest.</p>',
        here="index.html", about=about, hero=render_hero(imgs))



def render_germany() -> str:
    """German climate policy.

    Kept separate rather than mixed into the main feed because policy is
    jurisdictional in a way research is not: a German ministry consultation
    matters enormously in Berlin and not at all in Nairobi. Other countries
    can be added by giving their sources a region code."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = _fetch(conn, "accept", region="de")
    strata, body, n_days = _feed(rows)

    publishers = conn.execute(
        """SELECT COUNT(DISTINCT venue) FROM works
           WHERE region='de' AND published_date >= date('now', ?)""",
        (f"-{WINDOW_DAYS} days",)).fetchone()[0] if _has_region(conn) else 0

    stats = f"""<div class="stats">
<div><b>{len(rows):,}</b>documents</div>
<div><b>{n_days}</b>days with new work</div>
<div><b>{publishers}</b>publishers</div>
</div>"""

    head = ('<h1>Germany<span class="sub">Klimapolitik &mdash; agencies, '
            'councils, institutes</span></h1>\n'
            '<div class="lede">\n'
            '<p>German climate policy output from federal agencies, statutory '
            'advisory councils, research institutes and the journalism that '
            'covers the policy process. Policy is jurisdictional in a way '
            'research is not, so it gets its own page rather than diluting '
            'the main feed.</p>\n'
            '<p>This is the openly published subset. The professional '
            'briefings that practitioners actually rely on are paywalled and '
            'cannot be aggregated here.</p>\n'
            '</div>')

    about = f"""<section class="about">
<div>
<h3>What is covered</h3>
<p>Umweltbundesamt, BMUV, the Sachverständigenrat für Umweltfragen, and
institutes including Agora Energiewende, MCC Berlin, Öko-Institut, DIW,
the Wuppertal Institut and PIK. Plus Clean Energy Wire and Klimareporter°
for the process itself.</p>
<p>Everything here publishes openly. Nothing is scraped from behind a
paywall.</p>
</div>
<div>
<h3>What is missing</h3>
<p>There is no single database of German climate policy documents, which is
the gap this page is trying to fill. Bundestag proceedings, Länder-level
policy, and the paywalled professional briefings are all absent.</p>
<p>If you know a source that belongs here, that is the most useful thing
you can send.</p>
<a class="cta" href="feedback.html">Suggest a source</a>
</div>
<div>
<h3>Other countries</h3>
<p>Sources carry a region code, so adding a country is a matter of adding
its feeds rather than restructuring anything. Germany is simply first.</p>
<a class="cta" href="index.html">Back to the feed</a>
</div>
</section>"""

    return _shell(
        title="Germany — climate-feed",
        desc=("German climate policy documents from federal agencies, "
              "advisory councils and research institutes."),
        head=head, stats=stats, strata=strata, body=body or
        '<p class="empty">Nothing yet. Run the ingest with --source de_policy.</p>',
        here="germany.html", about=about)



def render_uncertain() -> str:
    """The borderline band. Published rather than hidden, because this is
    where the classifier's mistakes are, and they cannot be reported if
    nobody can see them."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = _fetch(conn, "uncertain")
    strata, body, n_days = _feed(rows, show_score=True)

    stats = f"""<div class="stats">
<div><b>{len(rows):,}</b>in the band</div>
<div><b>{n_days}</b>days with entries</div>
<div><b>0.8&#8202;–&#8202;2.5</b>score range</div>
</div>"""

    head = ('<h1>Uncertain<span class="sub">May or may not be climate '
            'science</span></h1>\n'
            '<div class="lede">\n'
            '<p>These scored high enough to suggest a climate connection but '
            'not high enough to be confident. Some are climate work the '
            'scoring undersold. Some borrow the vocabulary and are about '
            'something else entirely. They are published here rather than '
            'discarded, because a filter nobody can inspect is a filter '
            'nobody can correct.</p>\n'
            '<p>Each entry shows its score. The accepted feed starts at 2.5; '
            'anything below 0.8 was rejected outright and is not shown.</p>\n'
            '</div>')

    about = f"""<section class="about">
<div>
<h3>Why this page exists</h3>
<p>A single lexicon cannot separate climate science from every field that
shares its words. Rather than quietly dropping the ambiguous cases or
silently mixing them into the feed, they get their own page.</p>
<p>If something here clearly belongs in the feed, or clearly does not belong
anywhere, that is the most useful thing you can report.</p>
<a class="cta" href="feedback.html">Report a misclassification</a>
</div>
<div>
<h3>What would fix it</h3>
<p>The scoring is deliberately simple: a weighted term list, no training
data, no model. It is fast, cheap and legible, and it fails on anything
phrased unusually.</p>
<p>The intended next step is to resolve this band with sentence embeddings
against a set of known climate papers, which would move most of these one
way or the other.</p>
</div>
<div>
<h3>Back to the feed</h3>
<p>The accepted works, updated daily.</p>
<a class="cta" href="index.html">Go to the feed</a>
</div>
</section>"""

    return _shell(
        title="Uncertain — climate-feed",
        desc=("Works that scored in the borderline band: they may or may not "
              "be climate science."),
        head=head, stats=stats, strata=strata, body=body or
        '<p class="empty">Nothing in the uncertain band right now.</p>',
        here="uncertain.html", about=about)



LEDE = (
    "Every day a scheduled job pulls new work from OpenAlex, arXiv and a "
    "set of policy newsrooms, scores each item for climate relevance, and "
    "publishes what passes. Nothing is selected by hand, and anything the "
    "scoring is unsure about is held back rather than shown."
)

LEDE_2 = (
    "The site is static. No server runs between builds, so it draws no "
    "power while you are not reading it, and every build measures its own "
    "data transfer and estimated emissions."
)


CONTACT_BLOCK = '<div class="contact">\n<p class="contact-lead">Email</p>\n<a class="addr" href="mailto:{email}?subject=climate-feed%20feedback">{email}</a>\n<button class="copy" data-addr="{email}" type="button">Copy address</button>\n</div>'

CONTACT_UNSET = '<div class="notice">No contact address configured. Set\n<code>CONTACT_EMAIL</code> in <code>site_build/__main__.py</code>.</div>'

COPY_JS = "\nconst b=document.querySelector('.copy');\nif(b&&navigator.clipboard){b.addEventListener('click',async()=>{\n  try{await navigator.clipboard.writeText(b.dataset.addr);\n    const t=b.textContent;b.textContent='Copied';\n    setTimeout(()=>b.textContent=t,1600);}catch(e){}});}\nelse if(b){b.hidden=true;}\n"

FEEDBACK_PAGE = '<!doctype html>\n<html lang="en"><head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>Feedback &mdash; climate-feed</title>\n<meta name="description" content="Report a problem or suggest a source for climate-feed.">\n<style>{css}</style>\n</head><body>\n<div class="wrap">\n<header>\n<h1>Feedback<span class="sub">Tell me what is broken or missing</span></h1>\n{tabs}\n</header>\n\n<div class="page">\n<p>This feed is assembled automatically, so mistakes are structural rather\nthan personal. The most useful things to report:</p>\n<ul>\n<li>A paper listed here that clearly is not climate science</li>\n<li>A source that should be included and is not</li>\n<li>Climate work that is being filtered out when it should not be</li>\n<li>Dates, authors or venues that look wrong</li>\n</ul>\n<p>A link or an exact title makes it much faster to trace.</p>\n\n{contact}\n\n<a class="back" href="index.html">&larr; Back to the feed</a>\n</div>\n\n<footer>\n<span>climate-feed</span>\n<span><a href="{repo}">Source &amp; data</a></span>\n<span><a href="{site}">{author}</a></span>\n</footer>\n</div>\n<script>{js}</script>\n</body></html>'


def render_feedback() -> str:
    """Contact page. No form, no relay, no server."""
    contact = (CONTACT_BLOCK.format(email=CONTACT_EMAIL)
               if CONTACT_EMAIL else CONTACT_UNSET)
    return FEEDBACK_PAGE.format(css=CSS, contact=contact, js=COPY_JS,
                                tabs=_nav("feedback.html"),
                                repo=REPO_URL, site=AUTHOR_URL,
                                author=AUTHOR)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    OUT.joinpath("index.html").write_text(render(), encoding="utf-8")
    OUT.joinpath("germany.html").write_text(render_germany(),
                                            encoding="utf-8")
    OUT.joinpath("uncertain.html").write_text(render_uncertain(),
                                              encoding="utf-8")
    OUT.joinpath("feedback.html").write_text(render_feedback(),
                                             encoding="utf-8")
    for name in ("index.html", "germany.html", "uncertain.html",
                 "feedback.html"):
        kb = OUT.joinpath(name).stat().st_size / 1024
        print(f"wrote public/{name} ({kb:.0f} kB)")
    if not CONTACT_EMAIL:
        print("\nNote: CONTACT_EMAIL is blank, so there is no way to reach you.\n"
              "  Set it in site_build/__main__.py and rebuild.")


if __name__ == "__main__":
    main()
