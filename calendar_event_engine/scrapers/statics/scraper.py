import copy
from datetime import datetime, timedelta


from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.types.generics import GenericEvent
from calendar_event_engine.types.submission import (
    ScraperTypes,
    GroupEventsKernel,
    AllEventsFromAGroup,
)

logger = create_logger_from_designated_logger(__name__)


class StaticScraper(Scraper):
    def close_connection_to_source(self) -> None:
        pass

    def get_source_type(self):
        return ScraperTypes.STATIC

    def connect_to_source(self):
        pass

    def retrieve_from_source(
        self, group_kernel: GroupEventsKernel | None = None
    ) -> list[AllEventsFromAGroup]:
        assert group_kernel is not None
        logger.info(f"Getting static events: {group_kernel.group_name}")
        events: list[GenericEvent] = hydrate_event_template_with_legitimate_times(
            group_kernel
        )
        event: GenericEvent
        for event in events:
            event.description = f"Automatically scraped by event bot: \n\n{event.description} \n\n Source for farmer market info: https://portal.ct.gov/doag/adarc/adarc/farmers-market-nutrition-program/authorized-redemption-locations"
        return [AllEventsFromAGroup(events, group_kernel, group_kernel.group_name)]


def hydrate_event_template_with_legitimate_times(
    group_kernel: GroupEventsKernel,
) -> list[GenericEvent]:
    """
    Updating the initial default times from the static event to their relevant times for the week, unless
    the end date has been reached.
    """

    time_info = group_kernel.default_time_info
    if time_info is None:
        raise ValueError(f"Static group {group_kernel.group_name} has no default times")

    end_date = datetime.fromisoformat(time_info.end_time)
    now = datetime.now().astimezone()
    if now.date() > end_date.date():
        logger.info(f"Static Event {group_kernel.group_name} Has Expired")
        return []

    # There can be multiple days in a week when an event can occur
    generated_events = []
    for start_string, end_string in time_info.default_times:
        start_time = datetime.fromisoformat(start_string)
        end_time = datetime.fromisoformat(end_string)

        # Move the first occurrence forward to the next one that hasn't started.
        # Floor division can land on the week prior, hence the extra check.
        weeks_elapsed = timedelta(weeks=(now - start_time).days // 7)
        start_time += weeks_elapsed
        end_time += weeks_elapsed
        if start_time < now:
            start_time += timedelta(weeks=1)
            end_time += timedelta(weeks=1)
        if start_time.date() > end_date.date():
            continue

        event: GenericEvent = copy.deepcopy(group_kernel.event_template)
        event.begins_on = start_time.astimezone().isoformat()
        event.ends_on = end_time.astimezone().isoformat()
        generated_events.append(event)

    return generated_events
