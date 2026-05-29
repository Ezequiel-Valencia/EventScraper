import datetime
import os
import time
import traceback
from urllib.error import HTTPError

import requests

from slack_sdk.webhook import WebhookClient

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.filter import normalize_generic_event
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.parser.submission import get_runner_submission
from calendar_event_engine.publishers.abc_publisher import Publisher
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.types.custom_scraper import CustomScraperJob
from calendar_event_engine.types.submission import (
    GroupPackage,
    AllEventsFromAGroup,
    GroupEventsKernel,
    ScraperTypes,
)
from calendar_event_engine.types.submission_handlers import RunnerSubmission
from calendar_event_engine.scrapers.google_calendar.api import ExpiredToken
from calendar_event_engine.globals import get_slack_webhook, set_slack_webhook

logger = create_logger_from_designated_logger(__name__)


def _publish(publisher: Publisher, events: list[AllEventsFromAGroup]):
    for i in range(3):
        try:
            normalize_generic_event(events)
            publisher.upload(events)
            break
        except (HTTPError, requests.exceptions.RequestException, ValueError) as err:
            msg = f"The publisher {publisher.__class__.__name__} was unable to upload events."
            if isinstance(err, HTTPError) and "too many requests" in err.reason.lower():
                msg += f" The reason being to many requests where made to the publisher, and it returned a {err.code} error code."
                msg += f" This is attempt num: {i + 1}"
                logger.warning(msg=msg)
                time.sleep(120)
            else:
                logger.error(msg=msg, exc_info=err)
                msg += f" {err}"
                web_hook = get_slack_webhook()
                if web_hook is not None:
                    web_hook.send(
                        attachments=[
                            _produce_slack_message(
                                "#e6e209", "Publisher Error", msg, "Medium"
                            )
                        ]
                    )
                time.sleep(30)


def _scraper_scrapes_and_publishes(
    scraper: Scraper,
    scraper_type: ScraperTypes,
    publisher: Publisher,
    group_package: GroupPackage,
):
    scraper.connect_to_source()
    group_event_kernels: list[GroupEventsKernel] = (
        group_package.scraper_type_and_kernels[scraper_type]
    )
    for event_kernel in group_event_kernels:
        # Scrape
        events: list[AllEventsFromAGroup] | None = None
        try:
            events = scraper.retrieve_from_source(event_kernel)
        except (HTTPError, requests.exceptions.RequestException, ValueError) as err:
            msg = f"The scraper {scraper.get_source_type} produced an error when grabbing from the source {event_kernel.group_name}."
            if isinstance(err, HTTPError):
                msg += f" With HTTP error code {err.code}"
            logger.error(msg=msg, exc_info=err)
            web_hook = get_slack_webhook()
            if web_hook is not None:
                web_hook.send(
                    attachments=[
                        _produce_slack_message(
                            "#e6e209", "Scraper Request Error", msg, "Medium"
                        )
                    ]
                )

        # Publish
        if events is not None:
            _publish(publisher=publisher, events=events)

    scraper.close_connection_to_source()


def _custom_scrapers(custom_scrapers: dict[Publisher, list[CustomScraperJob]]):
    for publisher in custom_scrapers.keys():
        publisher.connect()
        for scrap in custom_scrapers[publisher]:
            try:
                logger.info(f"Using custom scraper {scrap.scraper_name}")
                scrap.custom_scraper.connect_to_source()
                events = scrap.custom_scraper.retrieve_from_source(None)
                normalize_generic_event(events)
                publisher.upload(events)
            except Exception as custom_err:
                logger.error(
                    "Exception for custom scraper: " + scrap.scraper_name,
                    custom_err,
                )
        publisher.close()


def _runner(
    runner_submission: RunnerSubmission,
    custom_scrapers: dict[Publisher, list[CustomScraperJob]] | None = None,
):
    submitted_publishers: dict[Publisher, list[GroupPackage]] = (
        runner_submission.publishers
    )
    for publisher in submitted_publishers.keys():
        publisher.connect()
        group_package: GroupPackage
        for group_package in submitted_publishers[publisher]:
            logger.info(f"Reading Group Package: {group_package.package_name}")

            for scraper_type in group_package.scraper_type_and_kernels.keys():
                scraper: Scraper = runner_submission.respective_scrapers[scraper_type]
                try:
                    _scraper_scrapes_and_publishes(
                        scraper=scraper,
                        scraper_type=scraper_type,
                        publisher=publisher,
                        group_package=group_package,
                    )
                except ExpiredToken:
                    logger.warning(
                        "Expired token.json needs to be replaced. Will continue scraping other types"
                    )

        publisher.close()

    if custom_scrapers:
        _custom_scrapers(custom_scrapers=custom_scrapers)


def _days_to_sleep(days):
    now = datetime.datetime.now()
    seconds_from_zero = now.hour * 60 * 60
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
        "fields": [{"title": "Priority", "value": priority, "short": "false"}],
        "footer": "CTEvent Scraper",
    }


def start_event_engine(
    remote_json_url: str,
    cache_db: SQLiteDB,
    slack_webhook: WebhookClient | None = None,
    custom_scrapers: dict[Publisher, list[CustomScraperJob]] | None = None,
    test_mode: bool = False,
):
    logger.info("Scraper Started")
    set_slack_webhook(slack_webhook)
    sleeping = 2
    while True:
        #####################
        # Create Submission #
        #####################

        submission: RunnerSubmission = get_runner_submission(
            remote_json_url, test_mode, cache_db
        )

        ######################
        # Execute Submission #
        ######################
        time_to_sleep = _days_to_sleep(sleeping)
        logger.info("Scraping")
        try:
            _runner(submission, custom_scrapers)
            logger.info("Sleeping " + str(sleeping) + " Days Until Next Scrape")
        except ExpiredToken:
            time_to_sleep = _days_to_sleep(2)
            logger.info("Sleeping " + str(sleeping) + " Days Until Next Scrape")
            if slack_webhook is not None:
                slack_webhook.send(
                    attachments=[
                        _produce_slack_message(
                            "#e6e209", "Expired Token", "Replace token.json", "Medium"
                        )
                    ]
                )

        except Exception as e:
            logger.error("Unknown Error")
            logger.error(e)
            logger.error(traceback.format_exc())
            logger.error("Going to Sleep for 7 days")
            if slack_webhook is not None:
                slack_webhook.send(
                    attachments=[
                        _produce_slack_message(
                            "#ab1a13",
                            "Event Scraper Unknown Error",
                            "Check logs for error.",
                            "High",
                        )
                    ]
                )
            time_to_sleep = _days_to_sleep(7)

        time.sleep(time_to_sleep)


if __name__ == "__main__":
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK")
    env_webhook = (
        None if slack_webhook_url is None else WebhookClient(slack_webhook_url)
    )
    env_test_mode = False if "TEST_MODE" not in os.environ else True
    submission_json_path = os.getenv("RUNNER_SUBMISSION_JSON_PATH")
    if submission_json_path is None:
        err = NotImplementedError("Did not find JSON submission path")
        logger.error(err)
        raise err

    start_event_engine(
        submission_json_path, SQLiteDB(env_test_mode), env_webhook, None, env_test_mode
    )
