import json
import os
import urllib.request

from event_scraper_generics.types.generics import GenericAddress, GenericEvent
from event_scraper_generics.types.submission import ScraperTypes, TimeInfo, GroupEventsKernel, GroupPackage, \
    PublisherTypes

from src.logger import create_logger_from_designated_logger
from src.parser.types.submission_handlers import *
from src.scrapers.ical.scraper import ICALScraper

logger = create_logger_from_designated_logger(__name__)


def none_if_not_present(x, dictionary):
    return None if x not in dictionary else dictionary[x]

def retrieve_source_type(source_type_string):
    match source_type_string:
        case "STATIC":
            return ScraperTypes.STATIC
        case "GOOGLE_CAL":
            return ScraperTypes.GOOGLE_CAL
        case "ICAL":
            return ScraperTypes.ICAL
    raise TypeError("Expected a string that resolves to a scraper type, instead got: " + source_type_string)

def get_group_package(json_path: str) -> GroupPackage:
    group_schema: dict = None
    with urllib.request.urlopen(json_path) as f:
        group_schema = json.load(f)
    
    group_package: GroupPackage = GroupPackage({}, none_if_not_present("name", group_schema),
                                               none_if_not_present("description", group_schema))

    for group_name, group_info in group_schema["groupKernels"].items():

        event_address = None if "defaultLocation" not in group_info else GenericAddress(**group_info["defaultLocation"])
        event_kernel = GenericEvent(group_info["publisherInfo"], none_if_not_present("title", group_info),
                     none_if_not_present("beginsOn", group_info), none_if_not_present("defaultDescription", group_info),
                     none_if_not_present("endsOn", group_info),
                     group_info["onlineAddress"], none_if_not_present("phoneAddress", group_info),
                     event_address)

        calendar_ids = group_info["calendarIDs"]
        scraper_type: ScraperTypes = retrieve_source_type(group_info["calendarType"])
        time_info = None
        if scraper_type == ScraperTypes.STATIC:
            time_info = TimeInfo(group_info["defaultTimes"], group_info["endDate"])

        if scraper_type not in group_package.scraper_type_and_kernels:
            group_package.scraper_type_and_kernels[scraper_type] = []

        group_package.scraper_type_and_kernels[scraper_type].append(
            GroupEventsKernel(event_kernel, group_name, calendar_ids=calendar_ids,
                              scraper_type=scraper_type, json_source_url=json_path, time_info=time_info))
    
    return group_package


from src.scrapers.google_calendar.scraper import GoogleCalendarScraper
from src.scrapers.statics.scraper import StaticScraper
from src.publishers.mobilizon.uploader import MobilizonUploader


def get_runner_submission(test_mode, cache_db, submission_path=None) -> RunnerSubmission:
    json_submission: dict = None
    submission_json_path = os.getenv("RUNNER_SUBMISSION_JSON_PATH") if submission_path is None else submission_path
    with urllib.request.urlopen(submission_json_path) as f:
        json_submission = json.load(f)

    publisher_package: {Publisher: [GroupPackage]} = dict()
    respective_scrapers: {ScraperTypes: Scraper} = dict()
    for publisher in json_submission.keys():
        publisher_instance: Publisher
        match publisher:
            case PublisherTypes.MOBILIZON.value:
                publisher_instance = MobilizonUploader(test_mode, cache_db)
            case _:
                raise TypeError("Expected publisher that is accepted, instead got: " + publisher)
        publisher_package[publisher_instance] = []
        for group_package_source_path in json_submission[publisher]:
            group_package: GroupPackage = get_group_package(group_package_source_path)
            publisher_package[publisher_instance].append(group_package)
            for scraper_type in list(group_package.scraper_type_and_kernels.keys()):
                if scraper_type not in respective_scrapers:
                    logger.info(f"Creating scraper of type: {scraper_type}")
                    match scraper_type:
                        case ScraperTypes.GOOGLE_CAL:
                            respective_scrapers[scraper_type] = GoogleCalendarScraper(cache_db)
                        case ScraperTypes.STATIC:
                            respective_scrapers[scraper_type] = StaticScraper()
                        case ScraperTypes.ICAL:
                            respective_scrapers[scraper_type] = ICALScraper(cache_db)

    return RunnerSubmission(cache_db, publisher_package, test_mode, respective_scrapers)










