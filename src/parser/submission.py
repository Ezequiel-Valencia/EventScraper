import json
import os
import urllib

from src.logger import create_logger_from_designated_logger
from src.parser.package import get_group_package
from src.publishers.abc_publisher import Publisher
from src.publishers.mobilizon.uploader import MobilizonUploader
from src.scrapers.abc_scraper import Scraper
from src.scrapers.google_calendar.scraper import GoogleCalendarScraper
from src.scrapers.ical.scraper import ICALScraper
from src.scrapers.statics.scraper import StaticScraper
from src.types.submission import PublisherTypes, ScraperTypes, GroupPackage
from src.types.submission_handlers import RunnerSubmission

logger = create_logger_from_designated_logger(__name__)


def get_runner_submission(test_mode, cache_db, submission_path=None) -> RunnerSubmission:
    json_submission: dict = None
    submission_json_path = os.getenv("RUNNER_SUBMISSION_JSON_PATH") if submission_path is None else submission_path
    with urllib.request.urlopen(submission_json_path) as f:
        json_submission = json.load(f)

    publisher_package: dict[Publisher, list[GroupPackage]] = dict()
    respective_scrapers: dict[ScraperTypes, Scraper] = dict()
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


