import datetime
import os
import time
import traceback
from urllib.error import HTTPError

from slack_sdk.webhook import WebhookClient

from event_engine.db_cache import SQLiteDB
from event_engine.filter import normalize_generic_event
from event_engine.logger import create_logger_from_designated_logger
from event_engine.parser.submission import get_runner_submission
from event_engine.publishers.abc_publisher import Publisher
from event_engine.scrapers.abc_scraper import Scraper
from event_engine.types.submission import GroupPackage, EventsToUploadFromCalendarID, GroupEventsKernel
from event_engine.types.submission_handlers import RunnerSubmission
from event_engine.scrapers.Websites.cafe9 import Cafe9Scraper
from event_engine.scrapers.google_calendar.api import ExpiredToken

logger = create_logger_from_designated_logger(__name__)


def _runner(runner_submission: RunnerSubmission, custom_scrapers: list[Scraper] = None):
    continue_scraping = True
    num_retries = 0
    theres_an_expired_token = False
    while continue_scraping and num_retries < 5:
        try:
            submitted_publishers: {Publisher: list[GroupPackage]} = runner_submission.publishers
            for publisher in submitted_publishers.keys():
                publisher: Publisher
                publisher.connect()
                if custom_scrapers:
                    for scraper in custom_scrapers:
                        try:
                            scraper.connect_to_source()
                            events = scraper.retrieve_from_source(None)
                            normalize_generic_event(events)
                            publisher.upload(events)
                        except Exception as err:
                            logger.error("Exception for custom scraper: " + scraper.__class__.__name__, err)

                group_package: GroupPackage
                for group_package in submitted_publishers[publisher]:
                    logger.info(f"Reading Group Package: {group_package.package_name}")

                    for scraper_type in group_package.scraper_type_and_kernels.keys():
                        scraper: Scraper = runner_submission.respective_scrapers[scraper_type]
                        try:
                            scraper.connect_to_source()
                            group_event_kernels: list[GroupEventsKernel] = group_package.scraper_type_and_kernels[
                                scraper_type]
                            for event_kernel in group_event_kernels:
                                event_kernel: GroupEventsKernel
                                try:
                                    events: list[EventsToUploadFromCalendarID] = scraper.retrieve_from_source(event_kernel)
                                except HTTPError as err:
                                    if err.code == 404:
                                        logger.warning(f"The following group is no longer available: {event_kernel.group_name}")
                                    else:
                                        raise
                                normalize_generic_event(events)
                                publisher.upload(events)
                            scraper.close_connection_to_source()
                        except ExpiredToken:
                            theres_an_expired_token = True
                            logger.warning("Expired token.json needs to be replaced. Will continue scraping other types")
                            continue
                publisher.close()

            continue_scraping = False
        except HTTPError as err:
            if err.code == 500 and err.reason.lower() == 'Too many requests'.lower():
                num_retries += 1
                logger.warning("Going to sleep then retrying to scrape. Retry Num: " + num_retries)
                time.sleep(120)
    if theres_an_expired_token:
        raise ExpiredToken

def _days_to_sleep(days):
    now = datetime.datetime.now()
    seconds_from_zero = (now.hour * 60 * 60)
    time_at_2am = 2 * 60 * 60
    time_to_sleep = time_at_2am
    if seconds_from_zero > time_at_2am:
        time_to_sleep = ((23 * 60 * 60) - seconds_from_zero) + time_at_2am
    else:
        time_to_sleep = time_at_2am - seconds_from_zero
    
    return time_to_sleep + (60 * 60 * 24 * days)


def _produce_slack_message(color, title, text, priority):
    return {
            "color": color,
            "author_name": "CTEvent Scraper",
            "author_icon": "https://ctgrassroots.org/favicon.ico",
            "title": title,
            "title_link": "google.com",
            "text": text,
            "fields": [
                {
                    "title": "Priority",
                    "value": priority,
                    "short": "false"
                }
            ],
            "footer": "CTEvent Scraper",
        }

def start_event_engine(remote_json_url: str, webhook: WebhookClient = None, test_mode: bool = False):
    logger.info("Scraper Started")
    sleeping = 2
    while True:
        #####################
        # Create Submission #
        #####################

        cache_db: SQLiteDB = SQLiteDB(test_mode)
        submission: RunnerSubmission = get_runner_submission(remote_json_url, test_mode, cache_db)

        ######################
        # Execute Submission #
        ######################
        time_to_sleep = _days_to_sleep(sleeping)
        logger.info("Scraping")
        try:
            _runner(submission, [Cafe9Scraper()])
            logger.info("Sleeping " + str(sleeping) + " Days Until Next Scrape")
        except ExpiredToken:
            time_to_sleep = _days_to_sleep(2)
            logger.info("Sleeping " + str(sleeping) + " Days Until Next Scrape")
            if webhook is not None:
                response = webhook.send(attachments=[
                    _produce_slack_message("#e6e209", "Expired Token", "Replace token.json", "Medium")
                ])

        except Exception as e:
            logger.error("Unknown Error")
            logger.error(e)
            logger.error(traceback.format_exc())
            logger.error("Going to Sleep for 7 days")
            if webhook is not None:
                webhook.send(attachments=[
                    _produce_slack_message("#ab1a13", "Event Scraper Unknown Error", "Check logs for error.", "High")
                ])
            time_to_sleep = _days_to_sleep(7)

        cache_db.close()
        time.sleep(time_to_sleep)


if __name__ == "__main__":
    env_webhook = None if os.environ.get("SLACK_WEBHOOK") is None else WebhookClient(os.environ.get("SLACK_WEBHOOK"))
    env_test_mode = False if "TEST_MODE" not in os.environ else True
    submission_json_path = os.getenv("RUNNER_SUBMISSION_JSON_PATH")
    if submission_json_path is None:
        err = NotImplementedError("Did not find JSON submission path")
        logger.error(err)
        raise err


    start_event_engine(submission_json_path, env_webhook, env_test_mode)


