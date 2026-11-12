from dataclasses import dataclass, field
from enum import Enum

from calendar_event_engine.types.generics import GenericEvent


class ScraperTypes(Enum):
    STATIC = "JSON"
    GOOGLE_CAL = "Google Calendar"
    ICAL = "ICAL"
    RSS = "RSS"
    JSON_LD = "JSON-LD"
    CUSTOM = "CUSTOM"


class PublisherTypes(Enum):
    MOBILIZON = "Mobilizon"


@dataclass
class TimeInfo:
    """
    Used to hydrate the static event schema.
    Args:
        default_times: [start, end] ISO 8601 pairs for the first occurrence of each weekly event.
        end_time: ISO 8601 date after which no more events are generated.
    """

    default_times: list[list[str]]
    end_time: str


@dataclass
class GroupEventsKernel:
    """
    All the information required to scrape a groups' information.
    An individual group can have multiple calendars.
    """

    event_template: GenericEvent
    group_name: str
    calendar_ids: list[str]
    scraper_type: ScraperTypes
    json_source_url: str
    default_time_info: TimeInfo | None = field(default=None, compare=False)


@dataclass
class GroupPackage:
    """
    A bundle of scrapers (ICal, Google, etc...) and the groups (ex. Salsa Club, Nature Volunteers, Car Enthusiasts, etc...)
    that information will be retrieved from.
    """

    scraper_type_and_kernels: dict[ScraperTypes, list[GroupEventsKernel]]
    package_name: str | None
    description: str | None


@dataclass
class AllEventsFromAGroup:
    """
    Wrapper for the events scraped for a particular calendar id.
    Args:
        events: All the events scrapped.
        event_kernel: All information about the group which being scrapped.
        calendar_id: The specific calendar where all the events scrapped originated from.
    """

    events: list[GenericEvent]
    event_kernel: GroupEventsKernel
    calendar_id: str
