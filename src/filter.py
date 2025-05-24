import requests
import validators

from src.parser.types.generics import GenericEvent
from src.parser.types.submission import EventsToUploadFromCalendarID

# https://www.geeksforgeeks.org/http-headers-content-type/

def normalize_generic_event(events_to_upload_list: list[EventsToUploadFromCalendarID]):
    allowed_image_content_type_header = ["image/gif", "image/jpeg", "image/png"]
    for events_to_upload in events_to_upload_list:
        generic_event: GenericEvent
        for generic_event in events_to_upload.events:
            # If valid URL but not a picture, set to empty string
            if validators.url(generic_event.picture):
                picture_head = requests.head(generic_event.picture)
                if picture_head.status_code != 200 and picture_head.headers.get("Content-type") not in allowed_image_content_type_header:
                    generic_event.picture = ""

            if not validators.url(generic_event.online_address):
                generic_event.online_address = ""






