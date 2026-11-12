"""
Scrapes schema.org Event markup embedded in web pages as JSON-LD
(<script type="application/ld+json">). Event platforms such as Eventbrite and
Meetup, and most WordPress event plugins, publish this markup so search engines
can list their events, which makes it the most widely available structured
source for groups that don't offer a calendar feed.

Each calendar ID is the URL of a page listing (or describing) events.
"""

import functools
import html
import json
from collections.abc import Callable, Iterator
from html.parser import HTMLParser
from typing import Any

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

# Events with these statuses aren't going ahead as listed.
_SKIPPED_STATUSES = ("EventCancelled", "EventPostponed")


class JSONLDScraper(Scraper):
    cache_db: SQLiteDB

    def __init__(self, cache_db: SQLiteDB):
        self.cache_db = cache_db

    def connect_to_source(self) -> None:
        pass

    def close_connection_to_source(self) -> None:
        pass

    def get_source_type(self) -> ScraperTypes:
        return ScraperTypes.JSON_LD

    def retrieve_from_source(
        self, event_kernel: GroupEventsKernel | None = None
    ) -> list[AllEventsFromAGroup]:
        assert event_kernel is not None
        logger.info(f"Getting events from web page {event_kernel.group_name}")
        all_events: list[AllEventsFromAGroup] = []
        for page_url in event_kernel.calendar_ids:
            events = parse_page(
                fetch_text(page_url),
                event_kernel.event_template,
                page_url=page_url,
                is_cached=functools.partial(
                    self.cache_db.entry_already_in_cache, source_id=page_url
                ),
            )
            all_events.append(AllEventsFromAGroup(events, event_kernel, page_url))
        return all_events


def parse_page(
    page_html: str,
    event_kernel: GenericEvent,
    page_url: str | None = None,
    is_cached: Callable[[str, str], bool] | None = None,
) -> list[GenericEvent]:
    tz = default_timezone(event_kernel)
    scraped: list[ScrapedEvent] = []
    for node in _find_events(extract_json_ld(page_html)):
        event = _parse_event(node, tz, page_url)
        if event is not None:
            scraped.append(event)
    return hydrate_event_templates(scraped, event_kernel, is_cached)


class _JSONLDExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            script_type = (dict(attrs).get("type") or "").split(";")[0].strip()
            if script_type.lower() == "application/ld+json":
                self._current = []

    def handle_data(self, data):
        if self._current is not None:
            self._current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._current is not None:
            self.blocks.append("".join(self._current))
            self._current = None


def extract_json_ld(page_html: str) -> list[Any]:
    """Every JSON-LD document in the page. Malformed ones are skipped."""
    extractor = _JSONLDExtractor()
    extractor.feed(page_html)
    extractor.close()
    documents = []
    for block in extractor.blocks:
        try:
            documents.append(json.loads(block, strict=False))
        except json.JSONDecodeError as err:
            logger.debug(f"Skipping malformed JSON-LD block: {err}")
    return documents


def _types(node: dict) -> list[str]:
    raw = node.get("@type", [])
    types = raw if isinstance(raw, list) else [raw]
    # Strip prefixes such as "schema:" or "https://schema.org/".
    return [str(t).rsplit("/", 1)[-1].rsplit(":", 1)[-1] for t in types]


def _is_event(node: dict) -> bool:
    # Covers Event and its subtypes (MusicEvent, SocialEvent, ...).
    return any(t.endswith("Event") for t in _types(node))


def _find_events(value: Any) -> Iterator[dict]:
    """Event nodes anywhere in the documents, e.g. inside @graph or an ItemList."""
    if isinstance(value, list):
        for child in value:
            yield from _find_events(child)
    elif isinstance(value, dict):
        if _is_event(value):
            yield value
            return
        for child in value.values():
            yield from _find_events(child)


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _string(value: Any) -> str | None:
    value = _first(value)
    if isinstance(value, dict):
        value = value.get("name") or value.get("@value")
    if value is None:
        return None
    text = html.unescape(str(value)).strip()
    return text or None


def _url(value: Any) -> str | None:
    value = _first(value)
    if isinstance(value, dict):
        value = value.get("url") or value.get("@id")
    return str(value) if value else None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _place(location: Any) -> dict | None:
    """The first physical place, skipping VirtualLocation."""
    locations = location if isinstance(location, list) else [location]
    for loc in locations:
        if isinstance(loc, str):
            return {"address": loc}
        if isinstance(loc, dict) and "VirtualLocation" not in _types(loc):
            return loc
    return None


def _virtual_url(location: Any) -> str | None:
    locations = location if isinstance(location, list) else [location]
    for loc in locations:
        if isinstance(loc, dict) and "VirtualLocation" in _types(loc):
            return _url(loc)
    return None


def _address(place: dict, tz: str) -> tuple[GenericAddress | None, bool]:
    """
    The place's address, and whether it is already geolocated (the page gave its
    coordinates) so Nominatim doesn't need to be asked.
    """
    raw = _first(place.get("address"))
    address: GenericAddress | None
    if isinstance(raw, dict):
        address = GenericAddress(
            street=_string(raw.get("streetAddress")),
            locality=_string(raw.get("addressLocality")),
            region=_string(raw.get("addressRegion")),
            postalCode=_string(raw.get("postalCode")),
        )
        country = _string(raw.get("addressCountry"))
        # Two/three letter codes like "US" are left as the default country name.
        if country and len(country) > 3:
            address.country = country
    else:
        address = parse_address_string(_string(raw))

    geo = _first(place.get("geo"))
    latitude = _float(geo.get("latitude")) if isinstance(geo, dict) else None
    longitude = _float(geo.get("longitude")) if isinstance(geo, dict) else None
    has_coordinates = latitude is not None and longitude is not None
    if has_coordinates:
        address = address or GenericAddress()
        address.latitude, address.longitude = latitude, longitude

    if address is not None:
        address.timezone = tz
        address.description = _string(place.get("name")) or ""
    return address, has_coordinates


def _parse_event(node: dict, tz: str, page_url: str | None) -> ScrapedEvent | None:
    title = _string(node.get("name"))
    start = parse_datetime(_string(node.get("startDate")), tz)
    if title is None or start is None:
        logger.debug(f"Skipping JSON-LD event without a name or start date: {title}")
        return None
    status = _string(node.get("eventStatus")) or ""
    if status.endswith(_SKIPPED_STATUSES):
        logger.debug(f"Skipping {title}, its status is {status}")
        return None

    address, geolocated = None, False
    place = _place(node.get("location"))
    if place is not None:
        address, geolocated = _address(place, tz)

    return ScrapedEvent(
        title=title,
        start=start,
        end=parse_datetime(_string(node.get("endDate")), tz),
        description=_string(node.get("description")) or "",
        url=_url(node.get("url"))
        or _virtual_url(node.get("location"))
        or page_url,
        picture=_url(node.get("image")),
        resolved_address=address if geolocated else None,
        address_to_geocode=None if geolocated else address,
    )
