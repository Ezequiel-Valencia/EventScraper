"""
Scrapes events from RSS 2.0, RSS 1.0 (RDF) and Atom feeds.

A plain feed item only has a publication date, which isn't when the event happens,
so only items carrying an event start date are scraped. The start date is read from
either of the common event extensions:
  - RSS Event module (mod_event): ev:startdate, ev:enddate, ev:location
  - xCal: xCal:dtstart, xCal:dtend, xCal:location
"""

import functools
import xml.etree.ElementTree as ET
from collections.abc import Callable

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.scrapers.common import (
    ScrapedEvent,
    default_timezone,
    fetch_text,
    hydrate_event_templates,
    parse_address_string,
    parse_datetime,
)
from calendar_event_engine.types.generics import GenericAddress, GenericEvent
from calendar_event_engine.types.submission import (
    AllEventsFromAGroup,
    GroupEventsKernel,
    ScraperTypes,
)

logger = create_logger_from_designated_logger(__name__)

_ATOM = "{http://www.w3.org/2005/Atom}"
_RSS1 = "{http://purl.org/rss/1.0/}"
_EV = "{http://purl.org/rss/1.0/modules/event/}"
_XCAL = "{urn:ietf:params:xml:ns:xcal}"
_CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
_MEDIA = "{http://search.yahoo.com/mrss/}"


class RSSScraper(Scraper):
    cache_db: SQLiteDB

    def __init__(self, cache_db: SQLiteDB):
        self.cache_db = cache_db

    def connect_to_source(self) -> None:
        pass

    def close_connection_to_source(self) -> None:
        pass

    def get_source_type(self) -> ScraperTypes:
        return ScraperTypes.RSS

    def retrieve_from_source(
        self, event_kernel: GroupEventsKernel | None = None
    ) -> list[AllEventsFromAGroup]:
        assert event_kernel is not None
        logger.info(f"Getting events from feed {event_kernel.group_name}")
        all_events: list[AllEventsFromAGroup] = []
        for feed_url in event_kernel.calendar_ids:
            events = parse_feed(
                fetch_text(feed_url),
                event_kernel.event_template,
                is_cached=functools.partial(
                    self.cache_db.entry_already_in_cache, source_id=feed_url
                ),
            )
            all_events.append(AllEventsFromAGroup(events, event_kernel, feed_url))
        return all_events


def parse_feed(
    feed_text: str,
    event_kernel: GenericEvent,
    is_cached: Callable[[str, str], bool] | None = None,
) -> list[GenericEvent]:
    root = ET.fromstring(feed_text)
    tz = default_timezone(event_kernel)
    scraped: list[ScrapedEvent] = []
    for item in _feed_items(root):
        event = _parse_item(item, tz, event_kernel.physical_address)
        if event is not None:
            scraped.append(event)
    return hydrate_event_templates(scraped, event_kernel, is_cached)


def _feed_items(root: ET.Element) -> list[ET.Element]:
    if root.tag == f"{_ATOM}feed":
        return root.findall(f"{_ATOM}entry")
    # RSS 2.0 items are un-namespaced inside <channel>; RSS 1.0 items are siblings
    # of <channel> in the RSS 1.0 namespace.
    return root.findall("./channel/item") + root.findall(f"{_RSS1}item")


def _text(item: ET.Element, *tags: str) -> str | None:
    for tag in tags:
        element = item.find(tag)
        if element is not None and element.text and element.text.strip():
            return element.text.strip()
    return None


def _link(item: ET.Element) -> str | None:
    for link in item.findall(f"{_ATOM}link"):
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href")
    return _text(item, "link", f"{_RSS1}link")


def _picture(item: ET.Element) -> str | None:
    for enclosure in item.findall("enclosure"):
        if enclosure.get("type", "").startswith("image/") and enclosure.get("url"):
            return enclosure.get("url")
    for tag in (f"{_MEDIA}content", f"{_MEDIA}thumbnail"):
        media = item.find(tag)
        if media is not None and media.get("url"):
            return media.get("url")
    return None


def _parse_item(
    item: ET.Element, tz: str, default_address: GenericAddress | None
) -> ScrapedEvent | None:
    title = _text(item, "title", f"{_RSS1}title", f"{_ATOM}title")
    start = parse_datetime(_text(item, f"{_EV}startdate", f"{_XCAL}dtstart"), tz)
    if title is None or start is None:
        logger.debug(f"Skipping feed item without a title or event start: {title}")
        return None

    location = _text(item, f"{_EV}location", f"{_XCAL}location")
    return ScrapedEvent(
        title=title,
        start=start,
        end=parse_datetime(_text(item, f"{_EV}enddate", f"{_XCAL}dtend"), tz),
        description=_text(
            item,
            f"{_CONTENT}encoded",
            "description",
            f"{_RSS1}description",
            f"{_ATOM}content",
            f"{_ATOM}summary",
        )
        or "",
        url=_link(item),
        picture=_picture(item),
        # An unparseable location falls back to the default, flagged as unverified.
        address_to_geocode=None
        if location is None
        else parse_address_string(location) or default_address,
    )
