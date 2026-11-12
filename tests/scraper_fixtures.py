"""Shared setup for the feed and web page scraper tests."""

from datetime import datetime, timedelta, timezone

import pytest

from calendar_event_engine.types.generics import GenericAddress, GenericEvent

GEOCODED = (41.0, -72.0)
NOW = datetime.now(timezone.utc).replace(microsecond=0)
TOMORROW = NOW + timedelta(days=1)
NEXT_MONTH = NOW + timedelta(days=30)
YESTERDAY = NOW - timedelta(days=1)


@pytest.fixture(autouse=True)
def scrape_window_enforced(monkeypatch: pytest.MonkeyPatch):
    # Other tests set TEST=True, which disables the scrape window.
    monkeypatch.delenv("TEST", raising=False)


@pytest.fixture
def geocode_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub Nominatim, recording each query sent to it."""
    calls: list[str] = []

    def fake_geocode(query: str):
        calls.append(query)
        return GEOCODED

    monkeypatch.setattr("calendar_event_engine.utils.location._geocode", fake_geocode)
    return calls


def make_template() -> GenericEvent:
    return GenericEvent(
        publisher_specific_info={"mobilizon": {"groupID": 1}},
        title="",
        begins_on="",
        online_address="https://group.example",
        physical_address=GenericAddress(
            street="1 Default St", locality="Hartford", region="CT"
        ),
    )
