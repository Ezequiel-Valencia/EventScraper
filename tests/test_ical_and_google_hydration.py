"""The ICAL and Google Calendar scrapers build events through the shared helpers."""

from datetime import timedelta

from icalendar import Calendar, Event

from calendar_event_engine.scrapers.google_calendar.api import GCalAPI
from calendar_event_engine.scrapers.ical.scraper import _hydrate_event_template
from tests.helpers import same_instant
from tests.scraper_fixtures import (  # noqa: F401  (pytest fixtures)
    GEOCODED,
    NEXT_MONTH,
    TOMORROW,
    YESTERDAY,
    geocode_calls,
    make_template,
    scrape_window_enforced,
)


def _calendar(*events: Event) -> Calendar:
    calendar = Calendar()
    for event in events:
        calendar.add_component(event)
    return calendar


def _ical_event(summary, start, status="CONFIRMED", **props) -> Event:
    event = Event()
    event.add("SUMMARY", summary)
    event.add("DTSTART", start)
    event.add("DTEND", start + timedelta(hours=2))
    event.add("STATUS", status)
    for key, value in props.items():
        event.add(key, value)
    return event


def test_ical_event(geocode_calls):
    calendar = _calendar(
        _ical_event(
            "Jazz",
            TOMORROW,
            DESCRIPTION="Live music",
            URL="https://example.com/jazz",
            ATTACH="https://example.com/jazz.png",
            LOCATION="Sally's, 350 Asylum St, Hartford, CT 06103",
        )
    )
    [event] = _hydrate_event_template(calendar, make_template())
    assert event.title == "Jazz"
    assert same_instant(event.begins_on, TOMORROW.isoformat())
    assert same_instant(event.ends_on, (TOMORROW + timedelta(hours=2)).isoformat())
    assert event.description.endswith("Live music")
    assert event.online_address == "https://example.com/jazz"
    assert event.picture == "https://example.com/jazz.png"
    assert event.physical_address.street == "350 Asylum St"
    assert (event.physical_address.latitude, event.physical_address.longitude) == GEOCODED


def test_ical_skips_unconfirmed_out_of_window_and_cached(geocode_calls):
    calendar = _calendar(
        _ical_event("Tentative", TOMORROW, status="TENTATIVE"),
        _ical_event("Past", YESTERDAY),
        _ical_event("Far", NEXT_MONTH),
        _ical_event("Cached", TOMORROW),
        _ical_event("Kept", TOMORROW),
    )
    events = _hydrate_event_template(
        calendar, make_template(), is_cached=lambda start, title: title == "Cached"
    )
    assert [e.title for e in events] == ["Kept"]


def test_ical_unparseable_location_uses_default_flagged_unverified(geocode_calls):
    calendar = _calendar(_ical_event("Online", TOMORROW, LOCATION="Online"))
    [event] = _hydrate_event_template(calendar, make_template())
    assert event.physical_address == make_template().physical_address
    assert "unverified location" in event.description
    assert geocode_calls == []


class _FakeRequest:
    def __init__(self, items):
        self.items = items

    def execute(self):
        return {"items": self.items}


class _FakeEventsAPI:
    def __init__(self, items):
        self.items = items

    def list(self, **kwargs):
        return _FakeRequest(self.items)

    def list_next(self, request, result):
        return None


class _FakeClient:
    def __init__(self, items):
        self._events = _FakeEventsAPI(items)

    def events(self):
        return self._events


def _google_event(summary, start, **fields):
    return {
        "summary": summary,
        "description": f"About {summary}",
        "start": {"dateTime": start.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
        **fields,
    }


def _google_events(items, cached=()):
    api = GCalAPI()
    api._apiClient = _FakeClient(items)
    return api.getAllEventsAWeekFromNow(
        make_template(),
        "calendar-id",
        lambda start, title, calendar_id: (
            calendar_id == "calendar-id" and title in cached
        ),
    )


def test_google_event(geocode_calls):
    [event] = _google_events(
        [
            _google_event(
                "Ride",
                TOMORROW,
                location="Bike Shop, 12 Park St, New Haven, CT 06511, USA",
            )
        ]
    )
    assert event.title == "Ride"
    assert same_instant(event.begins_on, TOMORROW.isoformat())
    assert event.description.endswith("About Ride")
    assert event.physical_address.street == "12 Park St"
    assert event.physical_address.postalCode == "06511"
    assert geocode_calls == ["12 Park St, New Haven, 06511"]
    # Google keeps the group's link rather than an event URL.
    assert event.online_address == "https://group.example"


def test_google_skips_incomplete_and_cached_but_not_past(geocode_calls):
    all_day = {"summary": "All day", "description": "x", "start": {"date": "2026-11-14"}, "end": {"date": "2026-11-15"}}
    no_description = _google_event("No description", TOMORROW)
    del no_description["description"]
    events = _google_events(
        [
            all_day,
            no_description,
            _google_event("Cached", TOMORROW),
            # The API query already bounds the time range, so this isn't refiltered.
            _google_event("Since last scrape", YESTERDAY),
        ],
        cached={"Cached"},
    )
    assert [e.title for e in events] == ["Since last scrape"]
    assert "unverified location" in events[0].description
