from abc import ABC, abstractmethod

from src.types.submission import GroupEventsKernel, EventsToUploadFromCalendarID, ScraperTypes


class Scraper(ABC):
    """
    The class used to retrieve information from a particular source type.
    """
    @abstractmethod
    def connect_to_source(self) -> None:
        pass

    @abstractmethod
    def retrieve_from_source(self, event_kernel: GroupEventsKernel=None) -> list[EventsToUploadFromCalendarID]:
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


