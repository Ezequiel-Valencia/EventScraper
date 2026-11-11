import json
import os

import validators

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.db.event_source_driver import EventSource
from calendar_event_engine.db.uploaded_events_driver import UploadedEventRow
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.publishers.abc_publisher import Publisher
from calendar_event_engine.publishers.mobilizon.api import MobilizonAPI
from calendar_event_engine.publishers.mobilizon.types import (
    MobilizonEvent,
    EventParameters,
    to_mobilizon_geom,
)
from calendar_event_engine.types.generics import GenericEvent
from calendar_event_engine.types.submission import GroupEventsKernel

logger = create_logger_from_designated_logger(__name__)


class MobilizonUploader(Publisher):
    mobilizonAPI: MobilizonAPI | None
    cache_db: SQLiteDB

    def __init__(self, test_mode: bool, cache_db: SQLiteDB):
        super().__init__(cache_db, logger)
        self.testMode = test_mode
        self.mobilizonAPI = None
        self._fake_uuid_for_tests = 0

    def close(self):
        if self.mobilizonAPI is None:
            return
        try:
            self.mobilizonAPI.logout()
        except Exception as err:
            # The access token expires on its own; nothing else to clean up.
            logger.warning("Unable to log out of Mobilizon", exc_info=err)
        finally:
            self.mobilizonAPI = None

    def _api(self) -> MobilizonAPI:
        if self.mobilizonAPI is None:
            raise RuntimeError("MobilizonUploader.connect() must be called first")
        return self.mobilizonAPI

    def update(self) -> None:
        pass

    def monitor(self) -> None:
        pass

    def upload_individual_event(self, event_to_upload: GenericEvent) -> dict:
        event: MobilizonEvent = self.generic_event_converter(event_to_upload)
        if self.testMode:
            self._fake_uuid_for_tests += 1
            return {
                "id": 1,
                "uuid": self._fake_uuid_for_tests,
                "groupId": event.attributedToId,
            }
        picture_url = event_to_upload.picture
        if picture_url is not None and validators.url(picture_url):
            # On failure the event keeps its default picture (if any).
            media_uuid = self._api().upload_file(picture_url)
            if media_uuid is not None:
                event.picture = EventParameters.MediaInput(mediaUuid=media_uuid)
        upload_response = self._api().create_event(event)
        upload_response["groupId"] = event.attributedToId
        return upload_response

    def create_cachable_response(
        self,
        upload_response: dict,
        event_kernel: GroupEventsKernel,
        event: GenericEvent,
        source_id,
    ):
        upload_row = UploadedEventRow(
            uuid=upload_response["uuid"],
            user_id=upload_response["id"],
            title=event.title,
            date=event.begins_on,
            group_id=upload_response["groupId"],
            group_name=event_kernel.group_name,
        )
        upload_source = EventSource(
            uuid=upload_response["uuid"],
            website_url=event.online_address or "",
            calendar_id=source_id,
            source_type=event_kernel.scraper_type.value,
        )
        return upload_row, upload_source

    def connect(self):
        if self.testMode:
            return
        endpoint = os.environ["MOBILIZON_ENDPOINT"]
        email = os.environ.get("MOBILIZON_EMAIL")
        passwd = os.environ.get("MOBILIZON_PASSWORD")
        if email is None or passwd is None:
            with open(os.environ["MOBILIZON_LOGIN_FILE"], "r") as f:
                secrets = json.load(f)
            email, passwd = secrets["email"], secrets["password"]
        self.mobilizonAPI = MobilizonAPI(endpoint, email, passwd)

    @staticmethod
    def generic_event_converter(generic_event: GenericEvent) -> MobilizonEvent:
        metadata: dict = generic_event.publisher_specific_info["mobilizon"]
        category = metadata.get("defaultCategory")
        default_image = metadata.get("defaultImageID")
        address = generic_event.physical_address
        return MobilizonEvent(
            attributedToId=metadata["groupID"],
            title=generic_event.title,
            description=generic_event.description or "",
            beginsOn=generic_event.begins_on,
            endsOn=generic_event.ends_on,
            tags=metadata.get("defaultTags"),
            onlineAddress=generic_event.online_address,
            category=None if category is None else EventParameters.Categories[category],
            picture=(
                None
                if default_image is None
                else EventParameters.MediaInput(mediaUuid=default_image)
            ),
            physicalAddress=(
                None
                if address is None
                else EventParameters.Address(
                    locality=address.locality or "",
                    postalCode=address.postalCode or "",
                    street=address.street or "",
                    geom=to_mobilizon_geom(address.latitude, address.longitude),
                    country=address.country,
                    region=address.region or "",
                    timezone=address.timezone,
                    description=address.description,
                )
            ),
        )
