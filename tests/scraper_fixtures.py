"""Shared setup for the feed and web page scraper tests."""

from datetime import datetime, timedelta, timezone

import pytest

from calendar_event_engine.types.generics import GenericAddress, GenericEvent

from tests.helpers import GEOCODED  # noqa: F401  (re-exported)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TOMORROW = NOW + timedelta(days=1)
NEXT_MONTH = NOW + timedelta(days=30)
YESTERDAY = NOW - timedelta(days=1)


@pytest.fixture(autouse=True)
def scrape_window_enforced(monkeypatch: pytest.MonkeyPatch):
    # Other tests set TEST=True, which disables the scrape window.
    monkeypatch.delenv("TEST", raising=False)


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
