"""Tests for the 503 middleware's edge cases that the full-stack tests in test_config.py cannot reach."""

import pytest
from auth0_ai_mcp import AuthServerUnavailableError

from auth0_ai_fastmcp.utils._internal import outage


async def _receive():
    return {"type": "http.request"}


def _collect():
    sent = []

    async def send(message):
        sent.append(message)

    return sent, send


async def test_outage_after_the_response_started_is_not_turned_into_a_503():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise AuthServerUnavailableError("down")

    sent, send = _collect()

    with pytest.raises(AuthServerUnavailableError):
        await outage.ServiceUnavailableMiddleware(app)({"type": "http"}, _receive, send)

    assert [m["status"] for m in sent if m["type"] == "http.response.start"] == [200]


async def test_other_errors_are_not_turned_into_a_503():
    async def app(scope, receive, send):
        raise RuntimeError("boom")

    sent, send = _collect()

    with pytest.raises(RuntimeError):
        await outage.ServiceUnavailableMiddleware(app)({"type": "http"}, _receive, send)

    assert sent == []


async def test_non_http_scopes_pass_through_untouched():
    async def app(scope, receive, send):
        raise AuthServerUnavailableError("down")

    sent, send = _collect()

    with pytest.raises(AuthServerUnavailableError):
        await outage.ServiceUnavailableMiddleware(app)({"type": "lifespan"}, _receive, send)

    assert sent == []
