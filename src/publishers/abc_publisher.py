
from abc import ABC, abstractmethod

from src.parser.types.generics import GenericEvent
from src.parser.types.submission import EventsToUploadFromCalendarID


class Publisher(ABC):
    """
    The publisher is responsible for checking the cache keeping track of events already uploaded.
    """
    @abstractmethod
    def upload(self, events_to_upload: list[EventsToUploadFromCalendarID]):
        """
        Takes [EventsToUploadFromCalendarID]
        """
        pass

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def generic_event_converter(self, generic_event: GenericEvent):
        pass











