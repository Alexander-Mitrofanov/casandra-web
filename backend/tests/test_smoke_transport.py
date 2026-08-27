from __future__ import annotations

import http.client
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

SMOKE = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "deploy" / "docker" / "smoke-e2e.py")
)
connection_for = SMOKE["connection_for"]


def arguments(api_origin: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        api_origin=api_origin,
        host="127.0.0.1",
        port=8082,
        source_ip="203.0.113.10",
    )


def test_public_smoke_uses_verified_https_origin() -> None:
    connection = connection_for(arguments("https://api.example.test"))
    try:
        assert isinstance(connection, http.client.HTTPSConnection)
        assert connection.host == "api.example.test"
        assert connection.port == 443
    finally:
        connection.close()


def test_private_smoke_retains_proxy_v2_transport() -> None:
    connection = connection_for(arguments(None))
    try:
        assert type(connection).__name__ == "ProxyV2Connection"
        assert connection.host == "127.0.0.1"
        assert connection.port == 8082
    finally:
        connection.close()


@pytest.mark.parametrize(
    "origin",
    [
        "http://api.example.test",
        "https://api.example.test/path",
        "https://user@api.example.test",
        "https://api.example.test?query=yes",
    ],
)
def test_public_smoke_rejects_non_origin_urls(origin: str) -> None:
    with pytest.raises(ValueError, match="HTTPS origin without a path"):
        connection_for(arguments(origin))
