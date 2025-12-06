import json
import os

import validators
from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.db.event_source_driver import EventSource
from calendar_event_engine.db.uploaded_events_driver import UploadedEventRow
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.publishers.abc_publisher import Publisher
from calendar_event_engine.publishers.mobilizon.api import MobilizonAPI
from calendar_event_engine.publishers.mobilizon.types import MobilizonEvent, EventParameters
from calendar_event_engine.types.generics import GenericEvent
from calendar_event_engine.types.submission import AllEventsFromAGroup, GroupEventsKernel

logger = create_logger_from_designated_logger(__name__)

def none_if_not_present(x, dictionary):
    return None if x not in dictionary else dictionary[x]

class MobilizonUploader(Publisher):

    mobilizonAPI: MobilizonAPI
    cache_db: SQLiteDB
    __fakeUUIDForTests = 0

    def __init__(self, test_mode, cache_db):
        super().__init__(cache_db, logger)
        self.testMode = test_mode

    def close(self):
        if not self.testMode:
            self.mobilizonAPI.logout()

    def update(self) -> None:
        pass

    def monitor(self) -> None:
        pass

    def upload_individual_event(self, event_to_upload: GenericEvent) -> dict:
        event: MobilizonEvent = self.generic_event_converter(event_to_upload)
        if self.testMode:
            self.__fakeUUIDForTests += 1
            return {"id": 1, "uuid": self.__fakeUUIDForTests, "groupId": event.attributedToId}
        else:
            upload_response: dict = {}
            if event.picture is not None and validators.url(event.picture.mediaUuid):
                potential_id = self.mobilizonAPI.upload_file(event.picture.mediaUuid)
                if potential_id != "":
                    event.picture.mediaUuid = potential_id
            upload_response = self.mobilizonAPI.bot_created_event(event)
            upload_response["groupId"] = event.attributedToId
            return upload_response

    def create_cachable_response(self, upload_response: dict, event_kernel: GroupEventsKernel, event: GenericEvent, source_id):
        upload_row = UploadedEventRow(uuid=upload_response["uuid"], user_id=upload_response["id"],
                                      title=event.title, date=event.begins_on,
                                      group_id=upload_response["groupId"], group_name=event_kernel.group_name)
        upload_source = EventSource(uuid=upload_response["uuid"], website_url=event.online_address,
                                    calendar_id=source_id, source_type=event_kernel.scraper_type.value)
        return upload_row, upload_source

    def connect(self):
        if not self.testMode:
            endpoint = os.environ.get("MOBILIZON_ENDPOINT")
            email = os.environ.get("MOBILIZON_EMAIL")
            passwd = os.environ.get("MOBILIZON_PASSWORD")

            if email is None and passwd is None:
                login_file_path = os.environ.get("MOBILIZON_LOGIN_FILE")
                with open(login_file_path, "r") as f:
                    secrets = json.load(f)
                    email = secrets["email"]
                    passwd = secrets["password"]

            self.mobilizonAPI = MobilizonAPI(endpoint, email, passwd)

    def generic_event_converter(self, generic_event: GenericEvent):
        mobilizon_metadata = generic_event.publisher_specific_info["mobilizon"]
        category = None if "defaultCategory" not in mobilizon_metadata else EventParameters.Categories[mobilizon_metadata["defaultCategory"]]

        if validators.url(generic_event.picture):
            mobilizon_picture = EventParameters.MediaInput(generic_event.picture)
        else:
            mobilizon_picture = None if "defaultImageID" not in mobilizon_metadata else EventParameters.MediaInput(mobilizon_metadata["defaultImageID"])


        mobilizon_tags = None if "defaultTags" not in mobilizon_metadata else mobilizon_metadata["defaultTags"]
        generic_physical_address = generic_event.physical_address
        mobilizon_physical_address = None if generic_physical_address == None else EventParameters.Address(locality=generic_physical_address.locality,
                                                             postalCode=generic_physical_address.postalCode,
                                                             street=generic_physical_address.street,
                                                             geom=generic_physical_address.geom,
                                                             country=generic_physical_address.country,
                                                             region=generic_physical_address.region,
                                                             timezone=generic_physical_address.timezone,
                                                             description=generic_physical_address.description)
        mobilizon_event = MobilizonEvent(mobilizon_metadata["groupID"], generic_event.title,
                                         description=generic_event.description, beginsOn=generic_event.begins_on,
                                         endsOn=generic_event.ends_on, tags=mobilizon_tags,
                                         onlineAddress=generic_event.online_address, physicalAddress=mobilizon_physical_address,
                                         category=category, picture=mobilizon_picture)
        return mobilizon_event



























