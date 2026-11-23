import dataclasses
import hashlib
import json
from abc import ABC, abstractmethod
from collections import Counter
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


def event_fingerprint(event: GenericEvent) -> str:
    """
    A hash of everything about `event` that gets published, so a later scrape can
    tell whether the event changed.
    """
    content = dataclasses.asdict(event)
    # The source's ID only identifies the event, it isn't published.
    content.pop("source_event_id", None)
    serialized = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _repeated_source_ids(events: list[GenericEvent]) -> set[str]:
    """IDs given to more than one event, which therefore can't identify them."""
    counts = Counter(e.source_event_id for e in events if e.source_event_id)
    return {source_id for source_id, count in counts.items() if count > 1}


class Publisher(ABC):
    """
    The resulting website or remote destination where all scraped events will be stored.
    """

    def __init__(self, cache_db: SQLiteDB, logger: Logger):
        self.cache_db = cache_db
        self.logger = logger

    @property
    def site_name(self) -> str:
        """
        The site events are published to, recorded with each cached event. When
        publishers are routed, the publisher's name is recorded instead.
        """
        return self.__class__.__name__

    def upload(
        self, list_of_groups_event: list[AllEventsFromAGroup], site: str | None = None
    ) -> list[GenericEvent]:
        """
        Publish new events, update the published events that changed, and return
        the events that were published or updated. Unchanged events are skipped.
        A failing event is logged and skipped.

        :param site: Recorded as the site each event was published to. Defaults to
            `site_name`.
        """
        site = site or self.site_name
        events_published = []
        checked_pictures: dict[str, bool] = {}
        for events_to_upload in list_of_groups_event:
            event_kernel = events_to_upload.event_kernel
            source_id = events_to_upload.calendar_id
            repeated_ids = _repeated_source_ids(events_to_upload.events)
            for generic_event in events_to_upload.events:
                try:
                    if generic_event.source_event_id in repeated_ids:
                        generic_event.source_event_id = None
                    if self._publish_event(
                        generic_event, event_kernel, source_id, site, checked_pictures
                    ):
                        events_published.append(generic_event)
                except Exception as e:
                    self.logger.error(
                        f"Unable to upload the following event: {generic_event}",
                        exc_info=e,
                    )

        return events_published

    def _publish_event(
        self,
        event: GenericEvent,
        event_kernel: GroupEventsKernel,
        calendar_id: str,
        site: str,
        checked_pictures: dict[str, bool],
    ) -> bool:
        """Create or update `event`. Returns whether the publisher was sent it."""
        # Fingerprinted before normalising, which depends on whether the picture
        # happens to be reachable right now.
        content_hash = event_fingerprint(event)
        cached = self.cache_db.find_uploaded_event(
            calendar_id, site, event.source_event_id, event.begins_on, event.title
        )

        if cached is None:
            normalize_generic_event(event, checked_pictures)
            upload_response = self.upload_individual_event(event)
            event_row, event_source = self._cachable_response(
                upload_response, event_kernel, event, calendar_id, site, content_hash
            )
            self.cache_db.insert_uploaded_event(event_row, event_source)
            self.logger.info(f"{event.title}: {upload_response}")
            return True

        # Rows from an older cache have no fingerprint: the version published then
        # is unknown, so it is taken to be this one rather than republished.
        changed = cached.content_hash not in (None, content_hash)
        if changed:
            normalize_generic_event(event, checked_pictures)
            upload_response = self.update_individual_event(cached.remote_id, event)
            self.logger.info(f"Updated {event.title} on {site}: {upload_response}")
        elif (
            cached.content_hash is not None
            and cached.site is not None
            and (cached.source_event_id or None) == (event.source_event_id or None)
        ):
            return False  # Unchanged, and nothing to fill in.

        event_row, event_source = self._cachable_response(
            {"id": cached.remote_id, "uuid": cached.uuid, "groupId": None},
            event_kernel,
            event,
            calendar_id,
            site,
            content_hash,
        )
        self.cache_db.update_cached_event(
            cached, event_row, event_source, republished=changed
        )
        return changed

    def _cachable_response(
        self,
        upload_response: dict,
        event_kernel: GroupEventsKernel,
        event: GenericEvent,
        calendar_id: str,
        site: str,
        content_hash: str,
    ) -> tuple[UploadedEventRow, EventSource]:
        event_row, event_source = self.create_cachable_response(
            upload_response, event_kernel, event, calendar_id
        )
        event_row.site = site
        event_row.content_hash = content_hash
        event_source.source_event_id = event.source_event_id
        return event_row, event_source

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
    def update_individual_event(
        self, remote_event_id: str, event_to_update: GenericEvent
    ) -> dict:
        """
        Replace an already published event with a new version of it.

        :param remote_event_id: The publisher's ID for the event, as returned under
            "id" by `upload_individual_event`.
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
