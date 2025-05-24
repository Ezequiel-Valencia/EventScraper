import json
import os

from aiohttp import ClientError

from src.db_cache import UploadedEventRow, UploadSource, SQLiteDB
from src.logger import create_logger_from_designated_logger
from src.parser.types.submission import EventsToUploadFromCalendarID
from src.parser.types.generics import GenericEvent
from src.publishers.abc_publisher import Publisher
from src.publishers.mobilizon.api import MobilizonAPI
from src.publishers.mobilizon.types import MobilizonEvent, EventParameters
import validators

logger = create_logger_from_designated_logger(__name__)

def none_if_not_present(x, dictionary):
    return None if x not in dictionary else dictionary[x]

class MobilizonUploader(Publisher):
    mobilizonAPI: MobilizonAPI
    cache_db: SQLiteDB
    test_mode: bool
    fakeUUIDForTests = 0

    def __init__(self, test_mode, cache_db):
        self.cache_db = cache_db
        self.testMode = test_mode

    def close(self):
        if not self.testMode:
            self.mobilizonAPI.logout()

    def upload(self, groups_events_to_upload: list[EventsToUploadFromCalendarID]):
        for events_to_upload in groups_events_to_upload:
            all_events = events_to_upload.events
            event_kernel = events_to_upload.eventKernel
            source_id = events_to_upload.calendar_id
            for generic_event in all_events:
                event: MobilizonEvent = self.generic_event_converter(generic_event)
                upload_response: dict = {}
                try:
                    if not self.cache_db.entry_already_in_cache(event.beginsOn, event.title, source_id):
                        if self.testMode:
                            self.fakeUUIDForTests += 1
                            upload_response = {"id": 1, "uuid": self.fakeUUIDForTests}
                        else:
                            if event.picture is not None and validators.url(event.picture.mediaId):
                                potential_id = self.mobilizonAPI.upload_file(event.picture.mediaId)
                                if potential_id != "":
                                    event.picture.mediaId = potential_id
                            upload_response = self.mobilizonAPI.bot_created_event(event)
                        logger.info(f"{event.title}: {upload_response}")

                        upload_row = UploadedEventRow(uuid=upload_response["uuid"], id=upload_response["id"],
                                                      title=event.title, date=event.beginsOn,
                                                      group_id=event.attributedToId, group_name=event_kernel.group_name)
                        upload_source = UploadSource(uuid=upload_response["uuid"], website_url=event.onlineAddress,
                                                     source=source_id, source_type=event_kernel.scraper_type)
                        self.cache_db.insert_uploaded_event(upload_row, upload_source)
                except Exception as e:
                    logger.error(f"Unable to upload the following event: {event}")


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



























