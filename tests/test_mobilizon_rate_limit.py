import time
from unittest.mock import MagicMock

import httpx2
import pytest
from gql.transport.exceptions import TransportQueryError, TransportServerError

from calendar_event_engine.publishers.mobilizon import gql_requests as gqlr
from calendar_event_engine.publishers.mobilizon.api import (
    RATE_LIMIT_ATTEMPTS,
    RATE_LIMIT_WAIT_SECONDS,
    MobilizonAPI,
    _is_rate_limited,
)

TOO_MANY = TransportQueryError(
    "{'message': 'Too many requests', 'path': ['createEvent']}"
)


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Record tenacity's waits instead of actually sleeping."""
    recorded: list[float] = []
    monkeypatch.setattr(time, "sleep", recorded.append)
    return recorded


def _api_with_client(client: MagicMock) -> MobilizonAPI:
    # Skip __init__, which would log in over the network.
    api = object.__new__(MobilizonAPI)
    api._client = client
    api._headers = {}
    return api


def _response(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=httpx2.Request("POST", "http://x"))


@pytest.mark.parametrize(
    "error, expected",
    [
        (TOO_MANY, True),
        (TransportServerError("429", 429), True),
        (httpx2.HTTPStatusError("429", request=None, response=_response(429)), True),
        (TransportQueryError("Event not found"), False),
        (TransportServerError("500", 500), False),
        (ValueError("too many requests"), False),
    ],
)
def test_is_rate_limited(error, expected):
    assert _is_rate_limited(error) is expected


def test_rate_limited_request_waits_a_minute_then_succeeds(sleeps):
    client = MagicMock()
    client.execute.side_effect = [TOO_MANY, TOO_MANY, {"ok": True}]
    api = _api_with_client(client)

    assert api._execute_once(gqlr.IDENTITIES, None) == {"ok": True}
    assert client.execute.call_count == 3
    assert sleeps == [RATE_LIMIT_WAIT_SECONDS, RATE_LIMIT_WAIT_SECONDS]


def test_rate_limited_request_gives_up_after_max_attempts(sleeps):
    client = MagicMock()
    client.execute.side_effect = TOO_MANY
    api = _api_with_client(client)

    with pytest.raises(TransportQueryError):
        api._execute_once(gqlr.IDENTITIES, None)
    assert client.execute.call_count == RATE_LIMIT_ATTEMPTS
    assert sleeps == [RATE_LIMIT_WAIT_SECONDS] * (RATE_LIMIT_ATTEMPTS - 1)


def test_other_query_errors_are_not_retried(sleeps):
    client = MagicMock()
    client.execute.side_effect = TransportQueryError("Event not found")
    api = _api_with_client(client)

    with pytest.raises(TransportQueryError):
        api._execute_once(gqlr.IDENTITIES, None)
    assert client.execute.call_count == 1
    assert sleeps == []
