import datetime
import os
import time

from slack_sdk.webhook import WebhookClient

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.logger import create_logger_from_designated_logger
from calendar_event_engine.notifications import (
    Priority,
    send_slack_alert,
    set_slack_webhook,
)
from calendar_event_engine.parser.submission import get_runner_submission
from calendar_event_engine.publishers.abc_publisher import Publisher
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.scrapers.google_calendar.api import ExpiredToken
from calendar_event_engine.types.custom_scraper import CustomScraperJob
from calendar_event_engine.types.submission import (
    AllEventsFromAGroup,
    GroupPackage,
    ScraperTypes,
)
from calendar_event_engine.types.submission_handlers import RunnerSubmission

logger = create_logger_from_designated_logger(__name__)

# Days between scrapes, and how long to back off after an unexpected error.
DAYS_BETWEEN_SCRAPES = 2
DAYS_AFTER_UNKNOWN_ERROR = 7
# The submission is fetched from a remote server; a network blip there
# shouldn't cost a whole scraping cycle.
SECONDS_BEFORE_SUBMISSION_RETRY = 60 * 60
# Scrapes start at this hour of the day, local time.
SCRAPE_HOUR = 2


def _publish(publisher: Publisher, events: list[AllEventsFromAGroup]) -> None:
    try:
        publisher.upload(events)
    except Exception as err:
        msg = (
            f"The publisher {publisher.__class__.__name__} was unable to upload events."
        )
        logger.error(msg, exc_info=err)
        send_slack_alert("Publisher Error", f"{msg} {err}", Priority.MEDIUM)


def _scraper_scrapes_and_publishes(
    scraper: Scraper,
    scraper_type: ScraperTypes,
    publisher: Publisher,
    group_package: GroupPackage,
) -> None:
    scraper.connect_to_source()
    try:
        for event_kernel in group_package.scraper_type_and_kernels[scraper_type]:
            # One broken source must not stop the remaining ones from being scraped.
            try:
                events = scraper.retrieve_from_source(event_kernel)
            except ExpiredToken:
                raise
            except Exception as err:
                msg = (
                    f"The scraper {scraper.get_source_type().value} produced an error "
                    f"when grabbing from the source {event_kernel.group_name}."
                )
                logger.error(msg, exc_info=err)
                send_slack_alert(
                    "Scraper Request Error", f"{msg} {err}", Priority.MEDIUM
                )
                continue

            _publish(publisher=publisher, events=events)
    finally:
        scraper.close_connection_to_source()


def _custom_scrapers(
    custom_scrapers: dict[Publisher, list[CustomScraperJob]],
) -> None:
    for publisher, jobs in custom_scrapers.items():
        publisher.connect()
        try:
            for job in jobs:
                try:
                    logger.info(f"Using custom scraper {job.scraper_name}")
                    job.custom_scraper.connect_to_source()
                    try:
                        events = job.custom_scraper.retrieve_from_source(None)
                    finally:
                        job.custom_scraper.close_connection_to_source()
                    publisher.upload(events)
                except Exception as custom_err:
                    logger.error(
                        f"Exception for custom scraper: {job.scraper_name}",
                        exc_info=custom_err,
                    )
        finally:
            publisher.close()


def _runner(
    runner_submission: RunnerSubmission,
    custom_scrapers: dict[Publisher, list[CustomScraperJob]] | None = None,
) -> None:
    for publisher, group_packages in runner_submission.publishers.items():
        publisher.connect()
        try:
            for group_package in group_packages:
                logger.info(f"Reading Group Package: {group_package.package_name}")

                for scraper_type in group_package.scraper_type_and_kernels:
                    scraper = runner_submission.respective_scrapers.get(scraper_type)
                    if scraper is None:
                        logger.warning(
                            f"No scraper available for type {scraper_type.value}, "
                            f"skipping it in {group_package.package_name}"
                        )
                        continue
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
                        send_slack_alert(
                            "Expired Token", "Replace token.json", Priority.MEDIUM
                        )
        finally:
            publisher.close()

    if custom_scrapers:
        _custom_scrapers(custom_scrapers=custom_scrapers)


def _days_to_sleep(days: int, now: datetime.datetime | None = None) -> float:
    """Seconds until the next SCRAPE_HOUR o'clock, plus `days` whole days."""
    now = now or datetime.datetime.now()
    next_run = now.replace(hour=SCRAPE_HOUR, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += datetime.timedelta(days=1)
    next_run += datetime.timedelta(days=days)
    return (next_run - now).total_seconds()


def start_event_engine(
    remote_json_url: str,
    cache_db: SQLiteDB,
    slack_webhook: WebhookClient | None = None,
    custom_scrapers: dict[Publisher, list[CustomScraperJob]] | None = None,
    test_mode: bool = False,
):
    logger.info("Scraper Started")
    set_slack_webhook(slack_webhook)
    while True:
        #####################
        # Create Submission #
        #####################
        try:
            submission: RunnerSubmission = get_runner_submission(
                remote_json_url, test_mode, cache_db
            )
        except Exception as err:
            logger.error(
                f"Unable to load the runner submission, retrying in "
                f"{SECONDS_BEFORE_SUBMISSION_RETRY // 60} minutes",
                exc_info=err,
            )
            send_slack_alert(
                "Submission Error",
                f"Unable to load the runner submission: {err}",
                Priority.MEDIUM,
            )
            time.sleep(SECONDS_BEFORE_SUBMISSION_RETRY)
            continue

        ######################
        # Execute Submission #
        ######################
        days_to_sleep = DAYS_BETWEEN_SCRAPES
        logger.info("Scraping")
        try:
            # Old events can no longer be scraped again, so they don't need caching.
            cache_db.delete_all_month_old_events()
            _runner(submission, custom_scrapers)
        except Exception as e:
            logger.error("Unknown Error", exc_info=e)
            send_slack_alert(
                "Event Scraper Unknown Error", "Check logs for error.", Priority.HIGH
            )
            days_to_sleep = DAYS_AFTER_UNKNOWN_ERROR

        logger.info(f"Sleeping {days_to_sleep} Days Until Next Scrape")
        time.sleep(_days_to_sleep(days_to_sleep))


if __name__ == "__main__":
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK")
    env_webhook = (
        None if slack_webhook_url is None else WebhookClient(slack_webhook_url)
    )
    env_test_mode = "TEST_MODE" in os.environ
    submission_json_path = os.getenv("RUNNER_SUBMISSION_JSON_PATH")
    if submission_json_path is None:
        raise SystemExit("RUNNER_SUBMISSION_JSON_PATH is not set")

    with SQLiteDB(env_test_mode) as env_cache_db:
        start_event_engine(
            submission_json_path, env_cache_db, env_webhook, None, env_test_mode
        )
