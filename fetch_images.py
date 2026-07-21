#!/usr/bin/env python3
"""Fetch and optimise the NASA imagery used on the site.

    pip install Pillow
    python3 fetch_images.py

Downloads once, writes optimised derivatives into public/img/, and prints
the byte cost of each. Run it again only if you change the image list --
the originals are cached in .cache/ so a rebuild costs no network at all.

Why not hotlink images.nasa.gov: it puts page speed outside your control,
sends every visitor to a third party, and serves multi-megabyte originals
where a 1600px WebP does the same visual job for a fiftieth of the bytes.

NASA media is generally free to use without permission. Credit the source,
and do not imply NASA endorses anything. Each image's official credit line
is fetched with it and written to public/img/credits.json.
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip install Pillow")

NASA_IDS = ["PIA00342", "PIA04378"]

CACHE = pathlib.Path(".cache/nasa")
OUT = pathlib.Path("public/img")
API = "https://images-api.nasa.gov"

# Widths to emit. The browser picks one via srcset, so a phone never pays
# for desktop pixels.
WIDTHS = [640, 1200, 1800]
WEBP_QUALITY = 72
JPEG_QUALITY = 78


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "climate-feed"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def metadata(nasa_id: str) -> dict:
    """Title, description and credit, straight from NASA rather than guessed."""
    d = get_json(f"{API}/search?nasa_id={nasa_id}")
    items = d.get("collection", {}).get("items", [])
    if not items:
        raise LookupError(f"{nasa_id}: not found in the NASA library")
    m = items[0]["data"][0]
    return {
        "nasa_id": nasa_id,
        "title": m.get("title", "").strip(),
        "description": (m.get("description") or "").strip(),
        "credit": (m.get("secondary_creator") or m.get("center")
                   or "NASA/JPL").strip(),
        "date": (m.get("date_created") or "")[:10],
        "page": f"https://images.nasa.gov/details/{nasa_id}",
    }


def best_asset(nasa_id: str) -> str:
    """Largest JPEG. The TIFF originals are 5-30 MB and pointless here."""
    d = get_json(f"{API}/asset/{nasa_id}")
    hrefs = [i["href"] for i in d["collection"]["items"]]
    jpegs = [h for h in hrefs if h.lower().endswith((".jpg", ".jpeg"))]
    if not jpegs:
        raise LookupError(f"{nasa_id}: no JPEG asset")
    for tag in ("~orig", "~large"):
        for h in jpegs:
            if tag in h:
                return h
    return jpegs[0]


def download(url: str, dest: pathlib.Path) -> pathlib.Path:
    if dest.exists():
        print(f"    cached  {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "climate-feed"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    print(f"    fetched {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def derive(src: pathlib.Path, stem: str) -> list[dict]:
    """Emit WebP at several widths, plus one JPEG fallback."""
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    with Image.open(src) as im:
        im = im.convert("RGB")
        ow = im.width
        for w in WIDTHS:
            if w > ow:
                continue
            h = round(im.height * w / ow)
            resized = im.resize((w, h), Image.LANCZOS)
            p = OUT / f"{stem}-{w}.webp"
            resized.save(p, "WEBP", quality=WEBP_QUALITY, method=6)
            made.append({"path": p.name, "width": w,
                         "bytes": p.stat().st_size, "type": "image/webp"})
        # Fallback for anything that cannot do WebP.
        w = min(1200, ow)
        h = round(im.height * w / ow)
        p = OUT / f"{stem}-{w}.jpg"
        im.resize((w, h), Image.LANCZOS).save(
            p, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        made.append({"path": p.name, "width": w,
                     "bytes": p.stat().st_size, "type": "image/jpeg"})
        made.sort(key=lambda d: d["width"])
        return made, im.width, im.height


def main() -> int:
    manifest = {}
    total_in = total_out = 0

    for nasa_id in NASA_IDS:
        print(f"\n{nasa_id}")
        try:
            meta = metadata(nasa_id)
        except Exception as exc:                      # noqa: BLE001
            print(f"    ERROR: {exc}")
            continue
        print(f"    title   {meta['title']}")
        print(f"    credit  {meta['credit']}")

        try:
            url = best_asset(nasa_id)
            src = download(url, CACHE / f"{nasa_id}.jpg")
        except Exception as exc:                      # noqa: BLE001
            print(f"    ERROR: {exc}")
            continue

        total_in += src.stat().st_size
        files, w, h = derive(src, nasa_id.lower())
        for f in files:
            print(f"    -> {f['path']:<22} {f['bytes'] / 1024:6.0f} kB")
        total_out += max(f["bytes"] for f in files if f["type"] == "image/webp")

        meta.update({"files": files, "width": w, "height": h})
        manifest[nasa_id] = meta

    if not manifest:
        print("\nNothing fetched.")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "credits.json").write_text(json.dumps(manifest, indent=2))

    print(f"\noriginals downloaded : {total_in / 1e6:6.1f} MB")
    print(f"largest served       : {total_out / 1024:6.0f} kB")
    print(f"reduction            : {100 * (1 - total_out / total_in):5.1f}%")
    print("\nWrote public/img/credits.json — site_build reads it from there.")
    print("Add .cache/ to .gitignore; the originals need not be committed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
