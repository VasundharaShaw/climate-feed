"""Credentials and identification.

OpenAlex changed in February 2026: API keys are now required, the polite
pool is gone, and the `mailto` parameter is no longer honoured. Rate
limits are credit-based rather than call-based.

The key is read from the environment, never committed. Locally, put it in
a .env-style shell export or your shell profile; in CI, add it as the
repository secret OPENALEX_API_KEY.
"""

from __future__ import annotations

import os

OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()

# Still worth identifying ourselves to arXiv and anyone else, even though
# OpenAlex no longer uses it. Politeness costs nothing.
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "vasundhara.shaw@fiz-karlsruhe.de")
PROJECT_URL = "https://github.com/VasundharaShaw/climate-feed"
USER_AGENT = f"climate-feed/0.1 ({PROJECT_URL}; mailto:{CONTACT_EMAIL})"


class MissingCredential(RuntimeError):
    pass


def require_openalex_key() -> str:
    """Fail loudly and early rather than burning retries on a 429."""
    if not OPENALEX_API_KEY:
        raise MissingCredential(
            "OPENALEX_API_KEY is not set. Since February 2026 OpenAlex "
            "requires an API key; the polite pool and mailto parameter are "
            "gone. Get a free key at https://openalex.org/settings/api and "
            "export OPENALEX_API_KEY=... (or add it as a repo secret)."
        )
    return OPENALEX_API_KEY
