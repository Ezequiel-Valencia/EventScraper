import copy
import functools
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import httpx2
import icalendar
import validators
from icalendar.cal import Calendar

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.types.generics import GenericEvent, GenericAddress
from calendar_event_engine.types.submission import (
    ScraperTypes,
    AllEventsFromAGroup,
    GroupEventsKernel,
)
from calendar_event_engine.utils.location import find_geolocation_from_address

logger = create_logger_from_designated_logger(__name__)

REQUEST_TIMEOUT_SECONDS = 30


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
            response = httpx2.get(
                ical_id, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True
            )
            response.raise_for_status()
            calendar = icalendar.Calendar.from_ical(response.text)
            events = _hydrate_event_template(
                calendar,
                group_event_kernel.event_template,
                is_cached=functools.partial(
                    self.cache_db.entry_already_in_cache, source_id=ical_id
                ),
            )
            all_events.append(AllEventsFromAGroup(events, group_event_kernel, ical_id))

        return all_events

    # Get only events 1 week from today, and that are confirmed

    def connect_to_source(self):
        pass


def _hydrate_event_template(
    calendar: Calendar,
    event_kernel: GenericEvent,
    is_cached: Callable[[str, str], bool] | None = None,
) -> list[GenericEvent]:
    """
    Events within the next week that are confirmed, filled into copies of `event_kernel`.

    :param is_cached: Given an event's start time and title, whether it was already
        published. Those events are skipped before the (slow) location lookup.
    """
    now = datetime.now(timezone.utc)
    week_from_now = now + timedelta(days=7)
    include_all_dates = os.getenv("TEST") == "True"
    events = []
    for event in calendar.events:
        start = event.start
        if not isinstance(start, datetime):
            start = datetime.combine(start, datetime.min.time(), timezone.utc)
        end = event.end
        if not isinstance(end, datetime):
            end = datetime.combine(end, datetime.min.time(), timezone.utc)
        summary = str(event.get("SUMMARY"))
        status = event.get("STATUS")
        over_a_week = week_from_now < start
        before_today = start < now

        # Have to search entire list because events aren't organized
        if (over_a_week or before_today) and not include_all_dates:
            continue
        if status != "CONFIRMED":
            continue
        if is_cached is not None and is_cached(start.isoformat(), summary):
            continue

        event_template = copy.deepcopy(event_kernel)
        event_template.title = summary
        event_template.begins_on = start.isoformat()
        event_template.ends_on = end.isoformat()
        attachment = str(event.get("ATTACH", ""))
        if attachment and validators.url(attachment):
            event_template.picture = attachment
        grabbed_description = (
            "" if "DESCRIPTION" not in event else str(event.get("DESCRIPTION"))
        )
        notif = ""
        event_template.online_address = (
            event_template.online_address
            if "URL" not in event
            else str(event.get("URL"))
        )
        if "LOCATION" in event:
            parsed_location = _parse_retrieved_location(
                str(event.get("LOCATION")), event_template.physical_address
            )
            event_template.physical_address, notif = find_geolocation_from_address(
                parsed_location,
                event_template.physical_address,
                event_template.title,
            )
        event_template.description = (
            f"Automatically scraped by Event Bot {notif}: \n\n{grabbed_description}"
        )
        events.append(event_template)

    return events


def _parse_retrieved_location(
    location: str, default_location: GenericAddress | None
) -> GenericAddress | None:
    if location is None:
        logger.debug("No location provided, using default")
        return default_location
    tokens = [token.strip() for token in location.split(",")]
    address: GenericAddress
    match len(tokens):
        case 1:
            return default_location
        case 2:
            return default_location
        case 3:
            address = GenericAddress(locality=tokens[2], street=tokens[1])
        case 4:
            address = GenericAddress(
                locality=tokens[2], street=tokens[1], region=tokens[3]
            )
        case 5:
            address = GenericAddress(
                locality=tokens[2],
                postalCode=tokens[4],
                street=tokens[1],
                region=tokens[3],
            )
        case _:
            return default_location
    return address
