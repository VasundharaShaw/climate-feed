"""Shared HTTP session: per-host pacing, backoff, byte accounting.

Two lessons are baked in here.

Per-host intervals. A single global delay is wrong because every API has
its own policy. arXiv asks for one request every three seconds; hammering
it at 0.15s got us throttled after roughly 1,900 records. Pacing correctly
up front is cheaper than retrying — in wall-clock time and in energy.

Credit exhaustion is not rate limiting. Since OpenAlex went credit-based,
a 429 means either "too fast, wait a moment" or "daily quota gone, come
back tomorrow". Retrying the second case is pure waste, so we read the
rate-limit headers and bail immediately when credits are spent.
"""

from __future__ import annotations

import logging
import random
import time
from urllib.parse import urlsplit

import requests

from .config import USER_AGENT

log = logging.getLogger(__name__)

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT

stats = {"requests": 0, "bytes": 0, "retries": 0}

# Seconds between requests, per host. Values come from each provider's
# stated policy, not from guesswork.
HOST_INTERVALS = {
    "export.arxiv.org": 3.0,      # arXiv asks for 1 request / 3 seconds
    "api.openalex.org": 0.2,      # credit-based; pacing is a courtesy
}
DEFAULT_INTERVAL = 1.0

_last_call: dict[str, float] = {}

MAX_ATTEMPTS = 5
RETRY_STATUSES = {429, 500, 502, 503, 504}


class RateLimited(Exception):
    """Host kept refusing after MAX_ATTEMPTS."""


class QuotaExhausted(Exception):
    """Daily credits spent. Retrying before reset is pointless."""


def _host(url: str) -> str:
    return urlsplit(url).netloc


def _credits_exhausted(resp: requests.Response) -> bool:
    """Distinguish a spent daily quota from a momentary rate limit."""
    remaining = resp.headers.get("X-RateLimit-Remaining")
    required = resp.headers.get("X-RateLimit-Credits-Required")
    if remaining is None:
        return False
    try:
        rem = float(remaining)
    except ValueError:
        return False
    if required is not None:
        try:
            return rem < float(required)
        except ValueError:
            pass
    return rem <= 0


def _backoff(attempt: int, resp: requests.Response | None) -> float:
    if resp is not None:
        hdr = resp.headers.get("Retry-After")
        if hdr:
            try:
                return min(float(hdr), 120.0)
            except ValueError:
                pass
    # Jitter matters on shared CI IPs, where many jobs would otherwise
    # retry in lockstep and re-trigger the same limit.
    return min(2.0 ** attempt + random.uniform(0, 1.0), 60.0)


def get(url: str, params: dict | None = None, headers: dict | None = None,
        timeout: int = 30) -> requests.Response:
    host = _host(url)
    interval = HOST_INTERVALS.get(host, DEFAULT_INTERVAL)
    last_resp = None

    for attempt in range(MAX_ATTEMPTS):
        wait = interval - (time.monotonic() - _last_call.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)

        try:
            resp = _session.get(url, params=params, headers=headers or {},
                                timeout=timeout)
        except requests.RequestException as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            delay = _backoff(attempt, None)
            log.warning("%s: %s — retrying in %.1fs (%d/%d)",
                        host, exc, delay, attempt + 1, MAX_ATTEMPTS)
            stats["retries"] += 1
            time.sleep(delay)
            continue
        finally:
            _last_call[host] = time.monotonic()

        stats["requests"] += 1
        stats["bytes"] += len(resp.content)

        if resp.status_code in RETRY_STATUSES:
            if resp.status_code == 429 and _credits_exhausted(resp):
                raise QuotaExhausted(
                    f"{host}: daily credits exhausted "
                    f"(remaining={resp.headers.get('X-RateLimit-Remaining')}). "
                    f"Resets at midnight UTC."
                )
            last_resp = resp
            if attempt == MAX_ATTEMPTS - 1:
                break
            delay = _backoff(attempt, resp)
            log.warning("%s: HTTP %d — retrying in %.1fs (%d/%d)",
                        host, resp.status_code, delay, attempt + 1, MAX_ATTEMPTS)
            stats["retries"] += 1
            time.sleep(delay)
            continue

        resp.raise_for_status()
        return resp

    code = last_resp.status_code if last_resp else "?"
    hint = ""
    if host == "api.openalex.org":
        hint = " OpenAlex requires an API key since Feb 2026 — check OPENALEX_API_KEY."
    elif host == "export.arxiv.org":
        hint = " arXiv asks for 1 request / 3 seconds; check HOST_INTERVALS."
    raise RateLimited(f"{host}: HTTP {code} after {MAX_ATTEMPTS} attempts.{hint}")
