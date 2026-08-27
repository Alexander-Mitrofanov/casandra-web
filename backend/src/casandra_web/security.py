"""Capability-token and filename helpers."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from pathlib import Path

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def new_job_id() -> str:
    return secrets.token_hex(16)


def new_access_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def token_matches(token: str, expected_digest: str, pepper: str) -> bool:
    return hmac.compare_digest(token_digest(token, pepper), expected_digest)


def client_digest(address: str, pepper: str) -> str:
    return hmac.new(pepper.encode("utf-8"), address.encode("utf-8"), hashlib.sha256).hexdigest()


def safe_display_filename(value: str | None) -> str:
    name = Path(value or "sequence.fasta").name
    cleaned = _SAFE_FILENAME.sub("_", name).strip("._")[:120]
    return cleaned or "sequence.fasta"
