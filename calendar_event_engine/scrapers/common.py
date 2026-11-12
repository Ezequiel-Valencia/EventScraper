"""Helpers shared by the scrapers that read events from a fetched document."""

import copy
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx2
import validators

from calendar_event_engine.types.generics import GenericAddress, GenericEvent
from calendar_event_engine.utils.location import find_geolocation_from_address

# How far ahead events are scraped.
SCRAPE_WINDOW = timedelta(days=7)
REQUEST_TIMEOUT_SECONDS = 30


@dataclass
class ScrapedEvent:
    """An event as read from a source, before it is merged into the group's template."""

    title: str
    start: datetime
    end: datetime | None = None
    description: str = ""
    url: str | None = None
    picture: str | None = None
    # Already geolocated (e.g. coordinates given by the source): used as is.
    resolved_address: GenericAddress | None = None
    # Needs geolocating before it is used.
    address_to_geocode: GenericAddress | None = None


def parse_datetime(value: str | None, default_tz: str) -> datetime | None:
    """
    Parse an ISO 8601 date or date-time. Values without a UTC offset are taken to be
    in `default_tz`. Returns None if the value can't be parsed.
    """
    if not value:
        return None
    value = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(value), datetime.min.time())
        except ValueError:
            return None
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(default_tz))
        except (ZoneInfoNotFoundError, ValueError):
            parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


_COUNTRY_TOKENS = {"us", "usa", "u.s.", "u.s.a.", "united states", "united states of america"}
_REGION_AND_POSTAL = re.compile(r"^([A-Za-z]{2})\.?\s+(\d{5}(?:-\d{4})?)$")
_POSTAL = re.compile(r"^\d{5}(?:-\d{4})?$")
_REGION = re.compile(r"^[A-Za-z]{2}$")


def parse_address_string(location: str | None) -> GenericAddress | None:
    """
    Best effort parse of a free text address such as
    "Venue, 123 Main St, Hartford, CT 06103". Returns None when there isn't
    at least a street and a town, so the group's default location is used instead.
    """
    if not location:
        return None
    tokens = [token.strip() for token in location.split(",") if token.strip()]
    while tokens and tokens[-1].lower() in _COUNTRY_TOKENS:
        tokens.pop()

    region = postal_code = None
    if tokens and (match := _REGION_AND_POSTAL.match(tokens[-1])):
        region, postal_code = match.group(1).upper(), match.group(2)
        tokens.pop()
    else:
        if tokens and _POSTAL.match(tokens[-1]):
            postal_code = tokens.pop()
        if tokens and _REGION.match(tokens[-1]):
            region = tokens.pop().upper()

    if len(tokens) < 2:
        return None
    return GenericAddress(
        street=tokens[-2],
        locality=tokens[-1],
        region=region,
        postalCode=postal_code,
    )


def fetch_text(url: str) -> str:
    response = httpx2.get(url, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
    response.raise_for_status()
    return response.text


def default_timezone(event_kernel: GenericEvent) -> str:
    if event_kernel.physical_address is not None:
        return event_kernel.physical_address.timezone
    return GenericAddress().timezone


def in_scrape_window(start: datetime, now: datetime | None = None) -> bool:
    if os.getenv("TEST") == "True":
        return True
    now = now or datetime.now(timezone.utc)
    return now <= start <= now + SCRAPE_WINDOW


def hydrate_event_templates(
    scraped_events: list[ScrapedEvent],
    event_kernel: GenericEvent,
    is_cached: Callable[[str, str], bool] | None = None,
    within_scrape_window: bool = True,
) -> list[GenericEvent]:
    """
    Copies of `event_kernel` filled in with each scraped event that starts within the
    scrape window and hasn't already been published.

    :param is_cached: Given an event's start time and title, whether it was already
        published. Those events are skipped before the (slow) location lookup.
    :param within_scrape_window: False when the source was already asked for only
        the events wanted, so they shouldn't be filtered again.
    """
    events: list[GenericEvent] = []
    for scraped in scraped_events:
        if within_scrape_window and not in_scrape_window(scraped.start):
            continue
        begins_on = scraped.start.isoformat()
        if is_cached is not None and is_cached(begins_on, scraped.title):
            continue

        event = copy.deepcopy(event_kernel)
        event.title = scraped.title
        event.begins_on = begins_on
        event.ends_on = scraped.end.isoformat() if scraped.end else None
        if scraped.url and validators.url(scraped.url):
            event.online_address = scraped.url
        if scraped.picture and validators.url(scraped.picture):
            event.picture = scraped.picture

        notif = ""
        if scraped.resolved_address is not None:
            event.physical_address = scraped.resolved_address
        elif scraped.address_to_geocode is not None:
            event.physical_address, notif = find_geolocation_from_address(
                scraped.address_to_geocode, event.physical_address, event.title
            )
        event.description = (
            f"Automatically scraped by Event Bot {notif}: \n\n{scraped.description}"
        )
        events.append(event)
    return events
