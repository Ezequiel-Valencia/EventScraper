import asyncio
import json
import logging
import os
from datetime import timezone, timedelta, datetime
from urllib.error import HTTPError
from geopy.geocoders import Nominatim

from src.db_cache import UploadedEventRow, SQLiteDB, UploadSource
from src.parser.jsonParser import get_group_package
from src.parser.types.generics import GenericEvent
from src.parser.types.submission import ScraperTypes, GroupEventsKernel, GroupPackage
from src.publishers.mobilizon.api import MobilizonAPI
from src.publishers.mobilizon.types import EventParameters, MobilizonEvent
from src.scrapers.google_calendar.api import GCalAPI
from src.scrapers.ical.scraper import ICALScraper

endpoint = os.environ.get("MOBILIZON_ENDPOINT")
email = os.environ.get("MOBILIZON_EMAIL")
passwd = os.environ.get("MOBILIZON_PASSWORD")


def manual_test_creation():

    mobilizon_api = MobilizonAPI(endpoint, email, passwd)
    # Time object requires timeZone
    begins_on = datetime(2024, 7, 7, 14, 35, tzinfo=timezone.utc)
    ends_on = datetime(2024, 7, 7, 17, 45, tzinfo=timezone.utc)
    geo_locator = Nominatim(user_agent="manual test creation")
    location = geo_locator.geocode("250 State St, New Haven, CT 06510").raw
    geom = f"{location['lon']};{location['lat']}"
    print(geom)
    cafe9_local = EventParameters.Address(locality="New Haven",
                                         postalCode="06510", street="250 State St", 
                                         country="United States", geom=geom,
                                         originId=f"nominatim:{location['place_id']}",
                                         type=location['addresstype'])
    
    # print(mobilizonAPI.getActors())
    # with open("//home/zek/Documents/Code/CTEventScraper/src/Duck.jpg", "rb") as f:
    #     params = {"file": f}
    #     print(mobilizonAPI.upload_file("Duck", f))
    mobilizon_api.logout()
    print("Login and out")

def manual_test_file_upload():
    mobilizon_api = MobilizonAPI(endpoint, email, passwd)
    event = MobilizonEvent(25, "Test", "Description", "2025-05-27T00:00:00-04:00")
    result = mobilizon_api.upload_file("https://cdn.britannica.com/92/100692-050-5B69B59B/Mallard.jpg")
    event.picture = EventParameters.MediaInput(result)
    mobilizon_api.bot_created_event(event)

def manual_test_google_calendar(print_events:bool = False):
    google_calendar_api = GCalAPI()
    google_calendars: dict = None
    with open(f"{os.getcwd()}/src/scrapers/GCal.json", "r") as f:
        google_calendars = json.load(f)

    bsbco = google_calendars["Bradley Street Bike Co-Op"]
    example_time_offset = datetime.utcnow() + timedelta(days=3)
    example_time_offset = example_time_offset.isoformat() + "Z"
    db = SQLiteDB(True)
    all_events = google_calendar_api.getAllEventsAWeekFromNow(
        calendarDict=bsbco, calendarId=bsbco["googleIDs"][0], 
        checkCacheFunction=db.entry_already_in_cache)
    
    if(print_events):
        for event in all_events:
            print(f"Start: {event.beginsOn}, End: {event.endsOn}, Title: {event.title}\nDescription: {event.description}, Location: {None if event.physicalAddress is None else event.physicalAddress.locality}")

    return all_events


def manual_test_cache_db():
    all_events: [UploadedEventRow] = [
        UploadedEventRow("uuid1", "id1", "title1", "2022-05-05T16:00:00-04:00", "2", "group2"),
        UploadedEventRow("uuid5", "id1", "title1", "2022-05-05T10:00:00-04:00", "2", "group2"),
        UploadedEventRow("uuid3", "id1", "title1", "2022-05-04T10:00:00-04:00", "2", "group2")
    ]
    event_sources: [UploadSource] = [
        UploadSource("uuid1", "website", "123", ScraperTypes.GOOGLE_CAL),
        UploadSource("uuid5", "website", "123", ScraperTypes.GOOGLE_CAL),
        UploadSource("uuid3", "website", "123", ScraperTypes.GOOGLE_CAL)
    ]
    db = SQLiteDB(True)
    for k in range(len(all_events)):
        db.insert_uploaded_event(all_events[k], event_sources[k])
    # print(db.selectAllFromTable().fetchall())
    print(db.get_last_event_date_for_source_id("123").isoformat())
    db.close()

def get_event_bot_info():
    mobilizon_api = MobilizonAPI(endpoint, email, passwd)
    print(mobilizon_api.getActors())
    print(mobilizon_api.getGroups())
    mobilizon_api.logout()

def _get_address_info():
    calendar_locations = {
        "Cafe Nine": "250 State St, New Haven, CT 06510",
        "BSBCO": "138 Bradley St, New Haven, CT 06511",
        "Hartford Jazz Society": "56 Arbor St, Hartford, CT 06106",
        "Healing Meals": "140 Nod Rd, Simsbury, CT 06070",
        "The Institute Library": "847 Chapel St, New Haven, CT 06510",
        "Elm City Games": "71 Orange St, New Haven, CT 06510",
        "New Haven Library": "133 Elm St, New Haven, CT 06510",
        "Hartford Library": "500 Main St, Hartford, CT 06103",
        "WBT": "105 Whitney Ave, New Haven, CT 06510"
    }
    geo_locator = Nominatim(user_agent="test nominatim")
    for key, value in calendar_locations.items():
        location = geo_locator.geocode(value)
        print(key, location.raw)

def manual_test_ical():
    cache_db = SQLiteDB(True)
    scraper = ICALScraper(cache_db)

    event = GenericEvent({"mobilizon": {"groupID": 10}}, "Title", "", "", "", "", "", None)
    event_kernel = GroupEventsKernel(event, "",
         ["https://calendar.google.com/calendar/ical/6lrbqnpdr3unfvr8oolv089hqu37nal6%40import.calendar.google.com/public/basic.ics"],
                                     ScraperTypes.ICAL, "")
    scraper.retrieve_from_source(event_kernel)

def manual_test_upload():
    cache_db = SQLiteDB(True)
    group_package: GroupPackage = get_group_package("https://kernel.ctgrassroots.org/Group%Packages/volunteer.json")



if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    # try:
    #     manual_test_ical()
    # except HTTPError as err:
    #     if err.code == 404:
    #         print("Hello")
    #     else:
    #         raise
    # manual_test_file_upload()
    # manualTestCreation()
    # manualTestGoogleCalendar(False)
    # manualTestCacheDB()
    # getEventBotInfo()
    # _getAddressInfo()
    
    
    
    pass

