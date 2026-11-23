import datetime
import functools
import os
import signal
import sys
import time
from collections.abc import Callable

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
    EventRouter,
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


# Where a batch of scraped events goes once it has been scraped.
_PublishFn = Callable[[list[AllEventsFromAGroup]], object]

CustomScrapers = dict[Publisher, list[CustomScraperJob]] | list[CustomScraperJob]


def _publish(
    publisher: Publisher, events: list[AllEventsFromAGroup], name: str | None = None
) -> None:
    try:
        publisher.upload(events, site=name)
    except Exception as err:
        label = name if name is not None else publisher.__class__.__name__
        msg = f"The publisher {label} was unable to upload events."
        logger.error(msg, exc_info=err)
        send_slack_alert("Publisher Error", f"{msg} {err}", Priority.MEDIUM)


class _RoutedPublishers:
    """
    Named publishers that share one scrape cycle. Each event goes only to the
    publisher `route_event` picks for it (or to the only publisher when there is
    no router).
    """

    def __init__(
        self, publishers: dict[str, Publisher], route_event: EventRouter | None
    ):
        self.publishers = publishers
        self.route_event = route_event
        self._connected: list[str] = []

    def connect(self) -> None:
        """Connect every publisher. One that fails is skipped for this cycle."""
        for name, publisher in self.publishers.items():
            try:
                publisher.connect()
            except Exception as err:
                msg = (
                    f"The publisher '{name}' was unable to connect, "
                    f"its events will be skipped this cycle."
                )
                logger.error(msg, exc_info=err)
                send_slack_alert(
                    "Publisher Connection Error", f"{msg} {err}", Priority.MEDIUM
                )
            else:
                self._connected.append(name)

    def close(self) -> None:
        for name in self._connected:
            try:
                self.publishers[name].close()
            except Exception as err:
                logger.warning(f"Unable to close the publisher '{name}'", exc_info=err)
        self._connected = []

    def publish(self, groups: list[AllEventsFromAGroup]) -> None:
        for name, routed_groups in self._route(groups).items():
            if name not in self._connected:
                count = sum(len(group.events) for group in routed_groups)
                logger.warning(
                    f"Skipping {count} event(s) for the publisher '{name}', "
                    f"it is not connected."
                )
                continue
            _publish(self.publishers[name], routed_groups, name)

    def _route(
        self, groups: list[AllEventsFromAGroup]
    ) -> dict[str, list[AllEventsFromAGroup]]:
        if self.route_event is None:
            (only_name,) = self.publishers
            return {only_name: groups}

        routed: dict[str, list[AllEventsFromAGroup]] = {}
        for group in groups:
            kernel = group.event_kernel
            # This group's events, split by publisher.
            group_by_name: dict[str, AllEventsFromAGroup] = {}
            for event in group.events:
                try:
                    name = self.route_event(event, kernel)
                except Exception as err:
                    logger.error(
                        f"route_event failed for '{event.title}' from "
                        f"{kernel.group_name}, skipping it.",
                        exc_info=err,
                    )
                    continue
                if name is None:
                    logger.info(
                        f"Skipping '{event.title}' from {kernel.group_name}: "
                        f"route_event sent it to no publisher."
                    )
                    continue
                if name not in self.publishers:
                    logger.error(
                        f"route_event sent '{event.title}' from {kernel.group_name} "
                        f"to the unknown publisher '{name}', skipping it."
                    )
                    continue
                if name not in group_by_name:
                    group_by_name[name] = AllEventsFromAGroup(
                        [], kernel, group.calendar_id
                    )
                    routed.setdefault(name, []).append(group_by_name[name])
                group_by_name[name].events.append(event)
        return routed


def _validate_publishing_options(
    publishers: dict[str, Publisher] | None,
    route_event: EventRouter | None,
    custom_scrapers: CustomScrapers | None,
) -> None:
    if publishers is None:
        if route_event is not None:
            raise ValueError("route_event needs named publishers: pass `publishers`.")
        if isinstance(custom_scrapers, list):
            raise ValueError(
                "Custom scrapers given as a list need named publishers: pass "
                "`publishers`, or give custom_scrapers as {publisher: [jobs]}."
            )
        return
    if not publishers:
        raise ValueError("`publishers` must name at least one publisher.")
    if route_event is None and len(publishers) > 1:
        raise ValueError(
            f"{len(publishers)} publishers were given ({', '.join(publishers)}) but "
            f"no route_event to choose between them."
        )


def _scraper_scrapes_and_publishes(
    scraper: Scraper,
    scraper_type: ScraperTypes,
    publish: _PublishFn,
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

            publish(events)
    finally:
        scraper.close_connection_to_source()


def _scrape_group_packages(
    runner_submission: RunnerSubmission,
    group_packages: list[GroupPackage],
    publish: _PublishFn,
) -> None:
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
                    publish=publish,
                    group_package=group_package,
                )
            except ExpiredToken:
                logger.warning(
                    "Expired token.json needs to be replaced. Will continue scraping other types"
                )
                send_slack_alert("Expired Token", "Replace token.json", Priority.MEDIUM)


def _run_custom_jobs(jobs: list[CustomScraperJob], publish: _PublishFn) -> None:
    for job in jobs:
        try:
            logger.info(f"Using custom scraper {job.scraper_name}")
            job.custom_scraper.connect_to_source()
            try:
                events = job.custom_scraper.retrieve_from_source(None)
            finally:
                job.custom_scraper.close_connection_to_source()
            publish(events)
        except Exception as custom_err:
            logger.error(
                f"Exception for custom scraper: {job.scraper_name}",
                exc_info=custom_err,
            )


def _custom_scrapers(
    custom_scrapers: dict[Publisher, list[CustomScraperJob]],
) -> None:
    for publisher, jobs in custom_scrapers.items():
        publisher.connect()
        try:
            _run_custom_jobs(jobs, publisher.upload)
        finally:
            publisher.close()


def _runner(
    runner_submission: RunnerSubmission,
    custom_scrapers: CustomScrapers | None = None,
    publishers: dict[str, Publisher] | None = None,
    route_event: EventRouter | None = None,
) -> None:
    _validate_publishing_options(publishers, route_event, custom_scrapers)

    if publishers is None:
        for publisher, group_packages in runner_submission.publishers.items():
            publisher.connect()
            try:
                _scrape_group_packages(
                    runner_submission,
                    group_packages,
                    functools.partial(_publish, publisher),
                )
            finally:
                publisher.close()
    else:
        # The submission's own publishers are replaced by the named ones.
        group_packages = [
            package
            for packages in runner_submission.publishers.values()
            for package in packages
        ]
        routed = _RoutedPublishers(publishers, route_event)
        routed.connect()
        try:
            _scrape_group_packages(runner_submission, group_packages, routed.publish)
            if isinstance(custom_scrapers, list):
                _run_custom_jobs(custom_scrapers, routed.publish)
        finally:
            routed.close()

    if isinstance(custom_scrapers, dict) and custom_scrapers:
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
    custom_scrapers: CustomScrapers | None = None,
    test_mode: bool = False,
    publishers: dict[str, Publisher] | None = None,
    route_event: EventRouter | None = None,
):
    """
    Scrape every DAYS_BETWEEN_SCRAPES days, forever.

    Args:
        custom_scrapers: Either {publisher: [jobs]}, or, when `publishers` is
            given, a plain list of jobs whose events are routed like the others.
        publishers: Named publishers that replace the one built from the
            submission JSON's key, e.g. {"family": MobilizonUploader(...),
            "nightlife": MobilizonUploader(...)}. Each is connected and closed
            once per scrape cycle.
        route_event: Picks a publisher name for each event, or None to skip it.
            Required when there is more than one publisher.
    """
    _validate_publishing_options(publishers, route_event, custom_scrapers)
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
            _runner(submission, custom_scrapers, publishers, route_event)
        except Exception as e:
            logger.error("Unknown Error", exc_info=e)
            send_slack_alert(
                "Event Scraper Unknown Error", "Check logs for error.", Priority.HIGH
            )
            days_to_sleep = DAYS_AFTER_UNKNOWN_ERROR

        logger.info(f"Sleeping {days_to_sleep} Days Until Next Scrape")
        time.sleep(_days_to_sleep(days_to_sleep))


if __name__ == "__main__":
    # As PID 1 in a container, SIGTERM is ignored unless handled. Exiting via
    # SystemExit lets the `with` block below close the cache DB cleanly.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

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
