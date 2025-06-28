from abc import ABC, abstractmethod

from calendar_event_engine.types.submission import GroupEventsKernel, AllEventsFromAGroup, ScraperTypes


class Scraper(ABC):
    """
    The class used to retrieve information from a particular source type.
    """
    @abstractmethod
    def connect_to_source(self) -> None:
        pass

    @abstractmethod
    def retrieve_from_source(self, event_kernel: GroupEventsKernel=None) -> list[AllEventsFromAGroup]:
        """
        Takes GroupEventKernel and returns list[EventsToUploadFromCalendarID]
        For custom scrapers, ignore any input and directly scrape from the resource to create EventsToUploadFromCalendarID.
        """
        pass

    @abstractmethod
    def close_connection_to_source(self) -> None:
        pass

    @abstractmethod
    def get_source_type(self) -> ScraperTypes:
        pass


