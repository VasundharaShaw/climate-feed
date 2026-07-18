"""One shared session for every source.

Tracks request count and bytes transferred so the run log can report a real
number rather than a vibe. Also enforces a floor on inter-request delay,
which keeps us inside every source's polite-use policy without needing
retries (retries are the expensive failure mode).
"""

from __future__ import annotations

import time

import requests

CONTACT = "climate-feed (mailto:you@example.org)"

_session = requests.Session()
_session.headers["User-Agent"] = CONTACT

stats = {"requests": 0, "bytes": 0}
_last_call = 0.0
MIN_INTERVAL = 0.15  # seconds


def get(url: str, params: dict | None = None, headers: dict | None = None,
        timeout: int = 30) -> requests.Response:
    global _last_call
    wait = MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)

    resp = _session.get(url, params=params, headers=headers or {}, timeout=timeout)
    _last_call = time.monotonic()

    stats["requests"] += 1
    stats["bytes"] += len(resp.content)
    resp.raise_for_status()
    return resp
