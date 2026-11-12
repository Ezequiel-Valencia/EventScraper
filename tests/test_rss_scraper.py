from datetime import datetime

from calendar_event_engine.scrapers.rss.scraper import RSSScraper, parse_feed
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


def _rss2(items: str) -> str:
    return f"""<?xml version="1.0"?>
<rss version="2.0"
     xmlns:ev="http://purl.org/rss/1.0/modules/event/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:media="http://search.yahoo.com/mrss/">
  <channel><title>Feed</title>{items}</channel>
</rss>"""


def _ev_item(
    title: str, start: datetime, end: datetime | None = None, extra: str = ""
) -> str:
    end_tag = f"<ev:enddate>{end.isoformat()}</ev:enddate>" if end else ""
    return f"""<item>
  <title>{title}</title>
  <link>https://example.com/{title.replace(" ", "-")}</link>
  <description>&lt;p&gt;About {title}&lt;/p&gt;</description>
  <ev:startdate>{start.isoformat()}</ev:startdate>{end_tag}{extra}
</item>"""


def test_rss2_event_module_item(geocode_calls):
    end = TOMORROW.replace(hour=23)
    feed = _rss2(
        _ev_item(
            "Jazz Night",
            TOMORROW,
            end,
            extra="""
  <ev:location>Black-eyed Sally's, 350 Asylum St, Hartford, CT 06103</ev:location>
  <enclosure url="https://example.com/jazz.png" type="image/png" length="1"/>""",
        )
    )

    [event] = parse_feed(feed, make_template())

    assert event.title == "Jazz Night"
    assert same_instant(event.begins_on, TOMORROW.isoformat())
    assert same_instant(event.ends_on, end.isoformat())
    assert event.online_address == "https://example.com/Jazz-Night"
    assert event.picture == "https://example.com/jazz.png"
    assert event.description.endswith("<p>About Jazz Night</p>")
    assert event.physical_address.street == "350 Asylum St"
    assert event.physical_address.postalCode == "06103"
    assert (
        event.physical_address.latitude,
        event.physical_address.longitude,
    ) == GEOCODED
    assert geocode_calls == ["350 Asylum St, Hartford, 06103"]
    # The template itself isn't modified.
    assert make_template().title == ""


def test_items_without_event_dates_are_skipped(geocode_calls):
    feed = _rss2(
        """<item><title>Blog post</title>
           <pubDate>Mon, 09 Nov 2026 10:00:00 GMT</pubDate></item>"""
        + _ev_item("Real event", TOMORROW)
    )
    assert [e.title for e in parse_feed(feed, make_template())] == ["Real event"]


def test_only_events_within_the_next_week(geocode_calls):
    feed = _rss2(
        _ev_item("Past", YESTERDAY)
        + _ev_item("Soon", TOMORROW)
        + _ev_item("Far", NEXT_MONTH)
    )
    assert [e.title for e in parse_feed(feed, make_template())] == ["Soon"]


def test_no_location_keeps_default_address(geocode_calls):
    [event] = parse_feed(_rss2(_ev_item("Meetup", TOMORROW)), make_template())
    assert event.physical_address == make_template().physical_address
    assert event.ends_on is None
    assert geocode_calls == []


def test_cached_events_are_skipped(geocode_calls):
    feed = _rss2(_ev_item("Old", TOMORROW) + _ev_item("New", TOMORROW))
    events = parse_feed(
        feed, make_template(), is_cached=lambda start, title: title == "Old"
    )
    assert [e.title for e in events] == ["New"]


def test_naive_dates_use_the_groups_timezone(geocode_calls):
    naive = TOMORROW.replace(tzinfo=None).isoformat()
    feed = _rss2(
        f"<item><title>Local</title><ev:startdate>{naive}</ev:startdate></item>"
    )
    [event] = parse_feed(feed, make_template())
    assert datetime.fromisoformat(event.begins_on).tzinfo is not None
    assert event.begins_on.startswith(naive)


def test_atom_feed_with_xcal(geocode_calls):
    start = TOMORROW.strftime("%Y%m%dT%H%M%SZ")
    feed = f"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:xCal="urn:ietf:params:xml:ns:xcal">
  <title>Atom</title>
  <entry>
    <title>Cleanup Day</title>
    <link rel="alternate" href="https://example.com/cleanup"/>
    <summary>Bring gloves</summary>
    <xCal:dtstart>{start}</xCal:dtstart>
  </entry>
</feed>"""
    [event] = parse_feed(feed, make_template())
    assert event.title == "Cleanup Day"
    assert event.online_address == "https://example.com/cleanup"
    assert event.description.endswith("Bring gloves")
    assert same_instant(event.begins_on, TOMORROW.isoformat())


def test_rss1_rdf_feed(geocode_calls):
    feed = f"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:ev="http://purl.org/rss/1.0/modules/event/">
  <channel rdf:about="https://example.com"><title>RDF</title></channel>
  <item rdf:about="https://example.com/a">
    <title>RDF Event</title>
    <link>https://example.com/a</link>
    <ev:startdate>{TOMORROW.isoformat()}</ev:startdate>
  </item>
</rdf:RDF>"""
    [event] = parse_feed(feed, make_template())
    assert event.title == "RDF Event"
    assert event.online_address == "https://example.com/a"


def test_scraper_fetches_each_feed(local_http_server, cache_db, geocode_calls):
    url = local_http_server.add_file(
        "events.rss", _rss2(_ev_item("Served", TOMORROW))
    )
    kernel = GroupEventsKernel(
        make_template(), "Group", [url], ScraperTypes.RSS, ""
    )

    [result] = RSSScraper(cache_db).retrieve_from_source(kernel)

    assert result.calendar_id == url
    assert [e.title for e in result.events] == ["Served"]
