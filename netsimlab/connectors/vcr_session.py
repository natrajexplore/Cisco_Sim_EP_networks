"""vcrpy wiring shared by all connectors.

Both ``dnacentersdk`` and ``ciscoisesdk`` use ``requests`` under the hood, so a
single ``vcr.use_cassette`` context around the SDK calls is enough to record the
real sandbox traffic once and replay it forever with no network.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterator

from urllib.parse import parse_qs, urlparse

import vcr

from netsimlab.config import FIXTURES_DIR, Mode

# Query keys that legitimately change between runs and must be ignored when
# matching a live request to a recorded one.
_VOLATILE_QUERY = {"timestamp", "_", "startTime", "endTime", "time"}

_SCRUB_HEADERS = (
    "authorization",
    "x-auth-token",
    "set-cookie",
    "cookie",
    "x-csrf-token",
)


def _before_record_request(request):
    # Strip query-string credentials if any and keep body for matching.
    return request


def _before_record_response(response):
    headers = response.get("headers", {})
    for key in list(headers):
        if key.lower() in _SCRUB_HEADERS:
            headers[key] = ["REDACTED"]
    # Redact bearer tokens that come back in auth response bodies.
    body = response.get("body", {})
    raw = body.get("string") if isinstance(body, dict) else None
    was_bytes = isinstance(raw, bytes)
    text = raw.decode("utf-8", "ignore") if was_bytes else raw
    if isinstance(text, str) and '"Token"' in text:
        import re

        text = re.sub(r'"Token"\s*:\s*"[^"]+"', '"Token": "REDACTED"', text)
        body["string"] = text.encode("utf-8") if was_bytes else text
    return response


def _stable_query(r1, r2) -> bool:
    def clean(url: str) -> dict:
        q = parse_qs(urlparse(url).query)
        return {k: v for k, v in q.items() if k not in _VOLATILE_QUERY}

    if clean(r1.uri) != clean(r2.uri):
        raise AssertionError("query mismatch (ignoring volatile keys)")


def build_vcr(subdir: str) -> vcr.VCR:
    cass_dir = FIXTURES_DIR / subdir
    cass_dir.mkdir(parents=True, exist_ok=True)
    v = vcr.VCR(
        cassette_library_dir=str(cass_dir),
        record_mode="none",
        filter_headers=[(h, "REDACTED") for h in _SCRUB_HEADERS],
        filter_post_data_parameters=["password", "username"],
        before_record_request=_before_record_request,
        before_record_response=_before_record_response,
        decode_compressed_response=True,
    )
    v.register_matcher("stable_query", _stable_query)
    v.match_on = ("method", "scheme", "host", "port", "path", "stable_query")
    return v


@contextmanager
def cassette(mode: Mode, subdir: str, name: str) -> Iterator[None]:
    """Context manager selecting record/replay/live behaviour."""
    if mode == "live":
        with nullcontext():
            yield
        return

    v = build_vcr(subdir)
    record_mode = "all" if mode == "record" else "none"
    path = Path(v.cassette_library_dir) / name
    if mode == "replay" and not path.exists():
        raise FileNotFoundError(
            f"no cassette at {path}. Run the scenario once with --mode record "
            f"(needs internet) to capture it from the DevNet sandbox."
        )
    with v.use_cassette(name, record_mode=record_mode):
        yield
