import copy
import os
from datetime import datetime, timedelta, timezone, date

import icalendar
import requests
import validators
from icalendar.cal import Calendar

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.publishers.mobilizon.api import logger
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.types.generics import GenericEvent, GenericAddress
from calendar_event_engine.types.submission import ScraperTypes, AllEventsFromAGroup, GroupEventsKernel
from calendar_event_engine.utils.location import find_geolocation_from_address

logger = create_logger_from_designated_logger(__name__)


class ICALScraper(Scraper):
    def close_connection_to_source(self) -> None:
        pass

    def get_source_type(self):
        return ScraperTypes.GOOGLE_CAL

    cache_db: SQLiteDB
    def __init__(self, cache_db: SQLiteDB):
        self.cache_db = cache_db

    def retrieve_from_source(self, group_event_kernel: GroupEventsKernel) -> list[AllEventsFromAGroup]:
        all_events: list[AllEventsFromAGroup] = []
        logger.info(f"Getting events from calendar {group_event_kernel.group_name}")
        for ical_id in group_event_kernel.calendar_ids:
            cal_text = requests.get(ical_id).text
            calendar = icalendar.Calendar.from_ical(cal_text)
            events = _hydrate_event_template(calendar, group_event_kernel.event_template)
            all_events.append(AllEventsFromAGroup(events, group_event_kernel, ical_id))

        return all_events

    # Get only events 1 week from today, and that are confirmed

    def connect_to_source(self):
        pass


def _hydrate_event_template(calendar: Calendar, event_kernel: GenericEvent) -> list[GenericEvent]:
    week_from_now = datetime.now(timezone.utc) + timedelta(days=7)
    events = []
    for event in calendar.walk('VEVENT'):
        event_template = copy.deepcopy(event_kernel)
        start = event.start
        if type(start) == date:
            start = datetime.combine(start, datetime.min.time(), timezone.utc)
        end = event.end
        if type(end) == date:
            end = datetime.combine(end, datetime.min.time(), timezone.utc)
        summary = str(event.get("SUMMARY"))
        status = event.get("STATUS")
        over_a_week = week_from_now < start
        before_today = start < datetime.now(timezone.utc)

        # Have to search entire list because events aren't organized
        if (over_a_week or before_today) and os.getenv("TEST") != "True":
            continue
        elif status == "CONFIRMED":
            event_template.title = summary
            event_template.begins_on = start.isoformat()
            event_template.ends_on = end.isoformat()
            if 'ATTACH' in event and validators.url(event.get("ATTACH")):
                event_template.picture = event.get("ATTACH")
            grabbed_description = "" if "DESCRIPTION" not in event else str(event.get("DESCRIPTION"))
            notif = ""
            event_template.online_address = event_template.online_address if "URL" not in event else str(event.get("URL"))
            if "LOCATION" in event:
                parsed_location = _parse_retrieved_location(str(event.get("LOCATION")), event_template.physical_address)
                event_template.physical_address, notif = find_geolocation_from_address(parsed_location,
                                                                               event_template.physical_address,
                                                                               event_template.title)
            event_template.description = f"Automatically scraped by Event Bot {notif}: \n\n{grabbed_description}"
            events.append(event_template)

    return events


def _parse_retrieved_location(location: str, default_location: GenericAddress) -> GenericAddress:
    if location is None:
        logger.debug("No location provided, using default")
        return default_location
    tokens = location.split(",")
    address: GenericAddress
    match len(tokens):
        case 1:
            return default_location
        case 2:
            return default_location
        case 3:
            address = GenericAddress(locality=tokens[2], street=tokens[1])
        case 4:
            address = GenericAddress(locality=tokens[2], street=tokens[1],
                                              region=tokens[3])
        case 5:
            address = GenericAddress(locality=tokens[2], postalCode=tokens[4], street=tokens[1],
                                            region=tokens[3])
        case _:
            return default_location
    return address


