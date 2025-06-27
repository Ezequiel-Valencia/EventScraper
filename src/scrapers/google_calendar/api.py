import copy
import os
from datetime import datetime, timedelta

import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from src.logger import create_logger_from_designated_logger
from src.types.generics import GenericAddress, GenericEvent
from src.utils.location import find_geolocation_from_address

logger = create_logger_from_designated_logger(__name__)

# Subscribe to the calendars
# https://webapps.stackexchange.com/questions/5217/how-can-i-find-the-subscribe-url-from-the-google-calendar-embed-source-code
# http://www.google.com/calendar/feeds/HERE/public/basic

# Bike Shop Source 
# bsbc.co_c4dt5esnmutedv7p3nu01aerhk@group.calendar.google.com

# Save The Sound Source
# ctenvironment@gmail.com

# Google API Documentation
# https://console.cloud.google.com/apis/credentials/consent
# https://developers.google.com/calendar/api/quickstart/python
# https://developers.google.com/resources/api-libraries/documentation/calendar/v3/python/latest/calendar_v3.events.html#list


class ExpiredToken(Exception):
    pass


class GCalAPI:
    _apiClient: Resource
    
    def __init__(self):
        pass
    
    def init_calendar_read_client_browser(self, token_path: str):
        SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
        credentialTokens = None
        if os.path.exists(token_path):
            credentialTokens = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        if not credentialTokens or not credentialTokens.valid:
            try: 
                if credentialTokens and credentialTokens.expired and credentialTokens.refresh_token:
                    credentialTokens.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                            f"{os.getcwd()}/config/OAuthClientApp.json", SCOPES
                        )
                    credentialTokens = flow.run_local_server(port=9000)
                
                # When refreshed authentication token needs to be re-written, and if authenticating for the first time it needs to be just written
                with open(token_path, "w") as tokenFile:
                    tokenFile.write(credentialTokens.to_json())
            except Exception:
                raise ExpiredToken
        self._apiClient = build("calendar", "v3", credentials=credentialTokens)
        logger.info("Logged in Google Cal Browser")

    
    def init_calendar_read_client_adc(self):
        logger.info("Logged In Google Cal ADC")
        credentials, projectID = google.auth.default()
        
        self._apiClient = build("calendar", "v3", credentials=credentials)
    

    def getAllEventsAWeekFromNow(self, eventKernel: GenericEvent, calendarId: str,
                                 checkCacheFunction,
                                 dateOfLastEventScraped: datetime = None) -> list[GenericEvent]:
        """Get events all events for that specific calender a week from today.

        Args:
            service (Resource): Calender resource available from creating a client with 'read calender' scope
            calendarId (str): UUID of calender. Same ID used to subscribe to a calender
            dateOfLastEventScraped (str, optional): UTC date with timedelta following isoformat. Have to add 'Z' to isoformat to indicate its UTC time. Defaults to None.
        """
        try:
            # Call the Calendar API, 'Z' indicates UTC time
            stringDateLastEvent = datetime.utcnow().astimezone().isoformat()
            if dateOfLastEventScraped is not None: 
                stringDateLastEvent = dateOfLastEventScraped.isoformat()
            logger.debug(f"Time of last event: {stringDateLastEvent}")
            weekFromNow = datetime.utcnow().astimezone() + timedelta(days=7)
            weekFromNow = weekFromNow.isoformat()
            
            events_result = (
                self._apiClient.events()
                .list(
                    calendarId=calendarId,
                    timeMin=stringDateLastEvent,
                    timeMax=weekFromNow,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            googleEvents = events_result.get("items", [])
            if len(googleEvents) == 0:
                logger.info(f"No upcoming events for calendarID {calendarId}\n")
                return googleEvents

            events = []
            for googleEvent in googleEvents:
                _process_google_event(googleEvent=googleEvent, eventsToUpload=events,
                                    checkCacheForEvent=checkCacheFunction,calendarId=calendarId,
                                    eventKernel=copy.deepcopy(eventKernel))
            
            return events
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
    
    def close(self):
        self._apiClient.close()





def _process_google_event(googleEvent: dict, eventsToUpload: [], checkCacheForEvent, 
                          calendarId: str, eventKernel: GenericEvent):
    
    starTimeGoogleEvent = googleEvent["start"].get("dateTime")
    endTimeGooglEvent = googleEvent["end"].get("dateTime")
    title = googleEvent.get("summary")
    description = googleEvent.get("description")

    
    if None not in [starTimeGoogleEvent, endTimeGooglEvent, title, description]:
        startDateTime = datetime.fromisoformat(starTimeGoogleEvent.replace('Z', '+00:00')).astimezone()
        endDateTime = datetime.fromisoformat(endTimeGooglEvent.replace('Z', '+00:00')).astimezone()
        if not checkCacheForEvent(startDateTime.isoformat(), title, calendarId):
            eventAddress, default_location_notif = find_geolocation_from_address(parse_google_location(googleEvent.get("location"), eventKernel.physical_address), eventKernel.physical_address, title)
            eventKernel.begins_on = startDateTime.isoformat()
            eventKernel.ends_on = endDateTime.isoformat()
            eventKernel.physical_address = eventAddress
            eventKernel.title = title
            eventKernel.description = f"Automatically scraped by Event Bot {default_location_notif}: \n\n{description}"
            eventsToUpload.append(eventKernel)
            

def parse_google_location(location:str, default_location: GenericAddress):
    if location is None:
        logger.debug("No location provided, using default")
        return default_location
    tokens = location.split(",")
    address: GenericAddress
    match len(tokens):
        case 1:
            return default_location
        case 2:
            return default_location
        case 3:
            address = GenericAddress(locality=tokens[0], postalCode=tokens[1], street="", country=tokens[2])
        case 4:
            address = GenericAddress(locality=tokens[1], postalCode=tokens[2], street=tokens[0], country=tokens[3])
        case 5:
            address = GenericAddress(locality=tokens[2], postalCode=tokens[3], street=tokens[1], country=tokens[4])
        case _:
            return default_location

    return address

    

if __name__ == "__main__":
    gcal = GCalAPI()
    google_token_path = os.environ.get("GOOGLE_API_TOKEN_PATH")
    gcal.init_calendar_read_client_browser(google_token_path)

