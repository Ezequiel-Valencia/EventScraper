import os
from datetime import datetime, timedelta

import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.types.generics import GenericAddress, GenericEvent
from calendar_event_engine.scrapers.common import (
    ScrapedEvent,
    hydrate_event_templates,
    parse_address_string,
)

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
                if (
                    credentialTokens
                    and credentialTokens.expired
                    and credentialTokens.refresh_token
                ):
                    credentialTokens.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        f"{os.getcwd()}/config/OAuthClientApp.json", SCOPES
                    )
                    credentialTokens = flow.run_local_server(port=9000)

                # When refreshed authentication token needs to be re-written, and if authenticating for the first time it needs to be just written
                with open(token_path, "w") as tokenFile:
                    tokenFile.write(credentialTokens.to_json())
            except Exception as err:
                raise ExpiredToken from err
        self._apiClient = build("calendar", "v3", credentials=credentialTokens)
        logger.info("Logged in Google Cal Browser")

    def init_calendar_read_client_adc(self):
        logger.info("Logged In Google Cal ADC")
        credentials, projectID = google.auth.default()

        self._apiClient = build("calendar", "v3", credentials=credentials)

    def getAllEventsAWeekFromNow(
        self,
        eventKernel: GenericEvent,
        calendarId: str,
        checkCacheFunction,
        dateOfLastEventScraped: datetime | None = None,
    ) -> list[GenericEvent]:
        """Get events all events for that specific calender a week from today.

        Args:
            service (Resource): Calender resource available from creating a client with 'read calender' scope
            calendarId (str): UUID of calender. Same ID used to subscribe to a calender
            dateOfLastEventScraped (str, optional): UTC date with timedelta following isoformat. Have to add 'Z' to isoformat to indicate its UTC time. Defaults to None.
        """
        try:
            # Call the Calendar API, 'Z' indicates UTC time
            stringDateLastEvent = datetime.now().astimezone().isoformat()
            if dateOfLastEventScraped is not None:
                stringDateLastEvent = dateOfLastEventScraped.isoformat()
            logger.debug(f"Time of last event: {stringDateLastEvent}")
            weekFromNow = datetime.now().astimezone() + timedelta(days=7)
            weekFromNowStr = weekFromNow.isoformat()

            events_api = self._apiClient.events()
            request = events_api.list(
                calendarId=calendarId,
                timeMin=stringDateLastEvent,
                timeMax=weekFromNowStr,
                singleEvents=True,
                orderBy="startTime",
            )
            # Results are paginated; keep requesting until there are no more pages.
            googleEvents: list[dict] = []
            while request is not None:
                events_result = request.execute()
                googleEvents.extend(events_result.get("items", []))
                request = events_api.list_next(request, events_result)
            if len(googleEvents) == 0:
                logger.info(f"No upcoming events for calendarID {calendarId}")
                return []

            scraped = [
                event
                for googleEvent in googleEvents
                if (
                    event := _to_scraped_event(
                        googleEvent, eventKernel.physical_address
                    )
                )
                is not None
            ]
            # The API was asked for just the wanted time range already.
            return hydrate_event_templates(
                scraped,
                eventKernel,
                is_cached=lambda start, title: checkCacheFunction(
                    start, title, calendarId
                ),
                within_scrape_window=False,
            )
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            return []

    def close(self):
        self._apiClient.close()


def _to_scraped_event(
    googleEvent: dict, default_address: GenericAddress | None
) -> ScrapedEvent | None:
    start = googleEvent["start"].get("dateTime")
    end = googleEvent["end"].get("dateTime")
    title = googleEvent.get("summary")
    description = googleEvent.get("description")
    if start is None or end is None or title is None or description is None:
        return None
    return ScrapedEvent(
        title=title,
        start=datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(),
        end=datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(),
        description=str(description),
        # Unparseable or missing locations fall back to the default, flagged as unverified.
        address_to_geocode=parse_address_string(googleEvent.get("location"))
        or default_address,
    )


if __name__ == "__main__":
    gcal = GCalAPI()
    google_token_path = os.environ.get("GOOGLE_API_TOKEN_PATH")
    if google_token_path is not None:
        gcal.init_calendar_read_client_browser(google_token_path)
