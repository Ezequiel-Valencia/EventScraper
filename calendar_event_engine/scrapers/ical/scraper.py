import functools
from collections.abc import Callable
from datetime import datetime, timezone

import icalendar
from icalendar.cal import Calendar

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.scrapers.common import (
    ScrapedEvent,
    fetch_text,
    hydrate_event_templates,
    parse_address_string,
)
from calendar_event_engine.types.generics import GenericEvent
from calendar_event_engine.types.submission import (
    ScraperTypes,
    AllEventsFromAGroup,
    GroupEventsKernel,
)

logger = create_logger_from_designated_logger(__name__)


class ICALScraper(Scraper):
    def close_connection_to_source(self) -> None:
        pass

    def get_source_type(self):
        return ScraperTypes.ICAL

    cache_db: SQLiteDB

    def __init__(self, cache_db: SQLiteDB):
        self.cache_db = cache_db

    def retrieve_from_source(
        self, group_event_kernel: GroupEventsKernel | None = None
    ) -> list[AllEventsFromAGroup]:
        assert group_event_kernel is not None
        all_events: list[AllEventsFromAGroup] = []
        logger.info(f"Getting events from calendar {group_event_kernel.group_name}")
        for ical_id in group_event_kernel.calendar_ids:
            calendar = icalendar.Calendar.from_ical(fetch_text(ical_id))
            events = _hydrate_event_template(
                calendar,
                group_event_kernel.event_template,
                is_cached=functools.partial(
                    self.cache_db.entry_already_in_cache, source_id=ical_id
                ),
            )
            all_events.append(AllEventsFromAGroup(events, group_event_kernel, ical_id))

        return all_events

    def connect_to_source(self):
        pass


def _as_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time(), timezone.utc)


def _hydrate_event_template(
    calendar: Calendar,
    event_kernel: GenericEvent,
    is_cached: Callable[[str, str], bool] | None = None,
) -> list[GenericEvent]:
    """
    Confirmed events within the scrape window, filled into copies of `event_kernel`.

    :param is_cached: Given an event's start time and title, whether it was already
        published. Those events are skipped before the (slow) location lookup.
    """
    scraped: list[ScrapedEvent] = []
    for event in calendar.events:
        if event.get("STATUS") != "CONFIRMED":
            continue
        address_to_geocode = None
        if "LOCATION" in event:
            # An unparseable location falls back to the default, flagged as unverified.
            address_to_geocode = (
                parse_address_string(str(event.get("LOCATION")))
                or event_kernel.physical_address
            )
        scraped.append(
            ScrapedEvent(
                title=str(event.get("SUMMARY")),
                start=_as_datetime(event.start),
                end=_as_datetime(event.end),
                description=str(event.get("DESCRIPTION", "")),
                url=str(event.get("URL")) if "URL" in event else None,
                picture=str(event.get("ATTACH", "")) or None,
                address_to_geocode=address_to_geocode,
            )
        )
    return hydrate_event_templates(scraped, event_kernel, is_cached)
