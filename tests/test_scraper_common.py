from datetime import datetime, timezone

import pytest

from calendar_event_engine.parser.package import retrieve_source_type
from calendar_event_engine.scrapers.common import parse_address_string, parse_datetime
from calendar_event_engine.types.submission import ScraperTypes


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-11-14T19:00:00Z", datetime(2026, 11, 14, 19, tzinfo=timezone.utc)),
        ("20261114T190000Z", datetime(2026, 11, 14, 19, tzinfo=timezone.utc)),
        ("2026-11-14T14:00:00-05:00", datetime(2026, 11, 14, 19, tzinfo=timezone.utc)),
        # Naive values are in the given timezone: 14:00 EST is 19:00 UTC.
        ("2026-11-14T14:00", datetime(2026, 11, 14, 19, tzinfo=timezone.utc)),
        ("2026-11-14", datetime(2026, 11, 14, 5, tzinfo=timezone.utc)),
    ],
)
def test_parse_datetime(value, expected):
    assert parse_datetime(value, "America/New_York") == expected


@pytest.mark.parametrize("value", [None, "", "next tuesday"])
def test_parse_datetime_invalid(value):
    assert parse_datetime(value, "America/New_York") is None


def test_parse_datetime_unknown_timezone_falls_back_to_utc():
    assert parse_datetime("2026-11-14T14:00", "Not/AZone") == datetime(
        2026, 11, 14, 14, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    "value, street, locality, region, postal",
    [
        ("Venue, 350 Asylum St, Hartford, CT 06103", "350 Asylum St", "Hartford", "CT", "06103"),
        ("350 Asylum St, Hartford, CT, 06103, USA", "350 Asylum St", "Hartford", "CT", "06103"),
        ("350 Asylum St, Hartford", "350 Asylum St", "Hartford", None, None),
        # Formerly the ICAL scraper's own location test.
        ("Venue, 123 Main St, Springfield, IL, 62701", "123 Main St", "Springfield", "IL", "62701"),
    ],
)
def test_parse_address_string(value, street, locality, region, postal):
    address = parse_address_string(value)
    assert address is not None
    assert (address.street, address.locality, address.region, address.postalCode) == (
        street,
        locality,
        region,
        postal,
    )


@pytest.mark.parametrize("value", [None, "", "Online", "Hartford, CT"])
def test_parse_address_string_too_vague(value):
    assert parse_address_string(value) is None


def test_new_calendar_types_are_recognised():
    assert retrieve_source_type("RSS") is ScraperTypes.RSS
    assert retrieve_source_type("JSON_LD") is ScraperTypes.JSON_LD
