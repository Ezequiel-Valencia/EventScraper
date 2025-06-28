
from abc import ABC, abstractmethod

from event_engine.types.submission import EventsToUploadFromCalendarID


class Publisher(ABC):
    """
    The resulting website or remote destination where all scraped events will be stored.
    """
    @abstractmethod
    def upload(self, events_to_upload: list[EventsToUploadFromCalendarID]) -> list[EventsToUploadFromCalendarID]:
        """
        Upload events to the publishers, and returns a list of successfully uploaded events.
        :param events_to_upload:
        :return:
        """
        pass

    @abstractmethod
    def update(self) -> None:
        """
        Update an event that has already been uploaded to the publisher.
        :return:
        """
        pass

    @abstractmethod
    def connect(self) -> None:
        """
        Connect to the external publisher.
        :return:
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the connection created with the publisher.
        :return:
        """
        pass

    @abstractmethod
    def monitor(self) -> None:
        """
        Used to check already scraped events if they have changed, and update them if needed.
        """
        pass











