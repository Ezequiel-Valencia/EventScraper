import json

from calendar_event_engine.scrapers.json_ld.scraper import (
    JSONLDScraper,
    extract_json_ld,
    parse_page,
)
from calendar_event_engine.types.submission import GroupEventsKernel, ScraperTypes
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

PAGE_URL = "https://venue.example/events"


def _page(*documents) -> str:
    scripts = "\n".join(
        f'<script type="application/ld+json">{json.dumps(d)}</script>'
        for d in documents
    )
    return f"<html><head>{scripts}</head><body><p>Events</p></body></html>"


def _event(name: str, start, **fields) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": name,
        "startDate": start.isoformat(),
        **fields,
    }


def test_full_event(geocode_calls):
    end = TOMORROW.replace(hour=23)
    page = _page(
        _event(
            "Salsa Night",
            TOMORROW,
            endDate=end.isoformat(),
            description="Dance &amp; music",
            url="https://venue.example/salsa",
            image=["https://venue.example/salsa.jpg"],
            location={
                "@type": "Place",
                "name": "The Hall",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "10 Main St",
                    "addressLocality": "New Haven",
                    "addressRegion": "CT",
                    "postalCode": "06510",
                    "addressCountry": "US",
                },
            },
        )
    )

    [event] = parse_page(page, make_template(), PAGE_URL)

    assert event.title == "Salsa Night"
    assert same_instant(event.begins_on, TOMORROW.isoformat())
    assert same_instant(event.ends_on, end.isoformat())
    assert event.description.endswith("Dance & music")
    assert event.online_address == "https://venue.example/salsa"
    assert event.picture == "https://venue.example/salsa.jpg"
    address = event.physical_address
    assert (address.street, address.locality, address.region, address.postalCode) == (
        "10 Main St",
        "New Haven",
        "CT",
        "06510",
    )
    assert address.country == "United States"
    assert address.description == "The Hall"
    assert (address.latitude, address.longitude) == GEOCODED
    assert geocode_calls == ["10 Main St, New Haven, 06510"]


def test_coordinates_on_the_page_skip_geocoding(geocode_calls):
    page = _page(
        _event(
            "Market",
            TOMORROW,
            location={
                "@type": "Place",
                "address": "5 Elm St, Hartford, CT 06103",
                "geo": {"@type": "GeoCoordinates", "latitude": "41.5", "longitude": -72.5},
            },
        )
    )
    [event] = parse_page(page, make_template(), PAGE_URL)
    assert (event.physical_address.latitude, event.physical_address.longitude) == (
        41.5,
        -72.5,
    )
    assert event.physical_address.street == "5 Elm St"
    assert "unverified location" not in event.description
    assert geocode_calls == []


def test_events_in_graph_and_item_list_and_subtypes(geocode_calls):
    page = _page(
        {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebPage", "name": "Not an event"},
                _event("In graph", TOMORROW) | {"@type": "MusicEvent"},
            ],
        },
        {
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "item": _event("In list", TOMORROW)},
                {
                    "@type": "ListItem",
                    "item": _event("Prefixed", TOMORROW)
                    | {"@type": ["schema:SocialEvent"]},
                },
            ],
        },
    )
    titles = [e.title for e in parse_page(page, make_template(), PAGE_URL)]
    assert titles == ["In graph", "In list", "Prefixed"]


def test_cancelled_and_postponed_events_are_skipped(geocode_calls):
    page = _page(
        [
            _event(
                "Cancelled",
                TOMORROW,
                eventStatus="https://schema.org/EventCancelled",
            ),
            _event("Postponed", TOMORROW, eventStatus="EventPostponed"),
            _event("Scheduled", TOMORROW, eventStatus="https://schema.org/EventScheduled"),
        ]
    )
    titles = [e.title for e in parse_page(page, make_template(), PAGE_URL)]
    assert titles == ["Scheduled"]


def test_only_events_within_the_next_week(geocode_calls):
    page = _page(
        [
            _event("Past", YESTERDAY),
            _event("Soon", TOMORROW),
            _event("Far", NEXT_MONTH),
        ]
    )
    titles = [e.title for e in parse_page(page, make_template(), PAGE_URL)]
    assert titles == ["Soon"]


def test_online_event_uses_virtual_location_url(geocode_calls):
    page = _page(
        _event(
            "Webinar",
            TOMORROW,
            location={"@type": "VirtualLocation", "url": "https://zoom.example/123"},
        )
    )
    [event] = parse_page(page, make_template(), PAGE_URL)
    assert event.online_address == "https://zoom.example/123"
    assert event.physical_address == make_template().physical_address
    assert geocode_calls == []


def test_missing_url_falls_back_to_the_page(geocode_calls):
    [event] = parse_page(_page(_event("No URL", TOMORROW)), make_template(), PAGE_URL)
    assert event.online_address == PAGE_URL


def test_cached_events_are_skipped(geocode_calls):
    page = _page([_event("Old", TOMORROW), _event("New", TOMORROW)])
    events = parse_page(
        page, make_template(), PAGE_URL, is_cached=lambda start, title: title == "Old"
    )
    assert [e.title for e in events] == ["New"]


def test_malformed_and_unrelated_scripts_are_ignored():
    page = """<html><head>
      <script>var x = {"@type": "Event"};</script>
      <script type="application/ld+json">{ not json </script>
      <script type="application/ld+json; charset=utf-8">{"@type": "Event"}</script>
    </head></html>"""
    assert extract_json_ld(page) == [{"@type": "Event"}]


def test_events_without_a_start_date_are_skipped(geocode_calls):
    page = _page({"@type": "Event", "name": "TBA"})
    assert parse_page(page, make_template(), PAGE_URL) == []


def test_scraper_fetches_each_page(local_http_server, cache_db, geocode_calls):
    url = local_http_server.add_file("events.html", _page(_event("Served", TOMORROW)))
    kernel = GroupEventsKernel(
        make_template(), "Group", [url], ScraperTypes.JSON_LD, ""
    )

    [result] = JSONLDScraper(cache_db).retrieve_from_source(kernel)

    assert result.calendar_id == url
    assert [e.title for e in result.events] == ["Served"]
    assert result.events[0].online_address == url
