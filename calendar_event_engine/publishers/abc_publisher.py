from abc import ABC, abstractmethod
from logging import Logger

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.db.event_source_driver import EventSource
from calendar_event_engine.db.uploaded_events_driver import UploadedEventRow
from calendar_event_engine.filter import normalize_generic_event
from calendar_event_engine.types.generics import GenericEvent
from calendar_event_engine.types.submission import (
    AllEventsFromAGroup,
    GroupEventsKernel,
)


class Publisher(ABC):
    """
    The resulting website or remote destination where all scraped events will be stored.
    """

    def __init__(self, cache_db: SQLiteDB, logger: Logger):
        self.cache_db = cache_db
        self.logger = logger

    def upload(
        self, list_of_groups_event: list[AllEventsFromAGroup]
    ) -> list[GenericEvent]:
        """
        Upload the events that are not in the cache yet, and return the ones
        that were successfully uploaded. A failing event is logged and skipped.
        """
        events_uploaded = []
        checked_pictures: dict[str, bool] = {}
        for events_to_upload in list_of_groups_event:
            event_kernel = events_to_upload.event_kernel
            source_id = events_to_upload.calendar_id
            for generic_event in events_to_upload.events:
                try:
                    if self.cache_db.entry_already_in_cache(
                        generic_event.begins_on, generic_event.title, source_id
                    ):
                        continue
                    normalize_generic_event(generic_event, checked_pictures)
                    upload_response = self.upload_individual_event(generic_event)
                    event_row, event_source = self.create_cachable_response(
                        upload_response, event_kernel, generic_event, source_id
                    )
                    self.cache_db.insert_uploaded_event(event_row, event_source)
                    self.logger.info(f"{generic_event.title}: {upload_response}")
                    events_uploaded.append(generic_event)
                except Exception as e:
                    self.logger.error(
                        f"Unable to upload the following event: {generic_event}",
                        exc_info=e,
                    )

        return events_uploaded

    @abstractmethod
    def create_cachable_response(
        self,
        upload_response: dict,
        event_kernel: GroupEventsKernel,
        generic_event: GenericEvent,
        calendar_id: str,
    ) -> tuple[UploadedEventRow, EventSource]:
        pass

    @abstractmethod
    def upload_individual_event(self, event_to_upload: GenericEvent) -> dict:
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
