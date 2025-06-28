import os


from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.parser.package import get_group_package
from calendar_event_engine.publishers.mobilizon.api import logger
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.scrapers.google_calendar.api import GCalAPI
from calendar_event_engine.types.generics import GenericEvent
from calendar_event_engine.types.submission import GroupEventsKernel, AllEventsFromAGroup, ScraperTypes

logger = create_logger_from_designated_logger(__name__)

class GoogleCalendarScraper(Scraper):
    def close_connection_to_source(self) -> None:
        self.google_calendar_api.close()

    def get_source_type(self):
        return ScraperTypes.GOOGLE_CAL

    google_calendar_api: GCalAPI
    cache_db: SQLiteDB
    def __init__(self, cache_db: SQLiteDB):
        self.cache_db = cache_db
        self.google_calendar_api = GCalAPI()

    def _get_specific_calendar_events(self, google_calendar_id, group_kernel: GroupEventsKernel):
        last_uploaded_event_date = None
        if not self.cache_db.no_entries_with_source_id(google_calendar_id):
            last_uploaded_event_date = self.cache_db.get_last_event_date_for_source_id(google_calendar_id)

        events: list[GenericEvent] = self.google_calendar_api.getAllEventsAWeekFromNow(
            calendarId=google_calendar_id, eventKernel=group_kernel.event_template,
            checkCacheFunction=self.cache_db.entry_already_in_cache,
            dateOfLastEventScraped=last_uploaded_event_date)

        return events


    def retrieve_from_source(self, group_event_kernel: GroupEventsKernel) -> list[AllEventsFromAGroup]:


        all_events: list[AllEventsFromAGroup] = []
        logger.info(f"Getting events from calendar {group_event_kernel.group_name}")
        for google_calendar_id in group_event_kernel.calendar_ids:
            events = self._get_specific_calendar_events(google_calendar_id, group_event_kernel)
            all_events.append(AllEventsFromAGroup(events, group_event_kernel, google_calendar_id))

        return all_events


    ############################
    # Used Mostly for Testing ##
    ############################
    def get_gcal_events_for_specific_group_and_upload_them(self, calendar_group: str):
        google_calendars: list[GroupEventsKernel] = get_group_package(f"{os.getcwd()}/src/scrapers/GCal.json")
        logger.info(f"\nGetting events from calendar {calendar_group}")
        gCal: GroupEventsKernel
        all_events: list[GenericEvent] = []
        for gCal in google_calendars:
            if gCal.group_name == calendar_group:
                for googleCalendarID in gCal.calendar_ids:
                    all_events += self._get_specific_calendar_events(googleCalendarID, gCal)
        return all_events

    def connect_to_source(self):
        use_oidc = os.environ.get("USE_OIDC_TOKEN")
        if use_oidc:
            token_path = f"{os.getcwd()}/config/token.json" if "GOOGLE_API_TOKEN_PATH" not in os.environ else os.environ.get("GOOGLE_API_TOKEN_PATH")
            self.google_calendar_api.init_calendar_read_client_browser(token_path)
        else:
            self.google_calendar_api.init_calendar_read_client_adc()