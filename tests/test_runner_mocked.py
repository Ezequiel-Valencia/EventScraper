"""Unit tests for the runner loop, notifications and event normalization."""

import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx2
import pytest

from calendar_event_engine import notifications
from calendar_event_engine.Runner import _days_to_sleep, _runner
from calendar_event_engine.filter import normalize_generic_event
from calendar_event_engine.publishers.mobilizon.uploader import MobilizonUploader
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.scrapers.statics.scraper import (
    hydrate_event_template_with_legitimate_times,
)
from calendar_event_engine.types.generics import GenericEvent
from calendar_event_engine.types.submission import (
    AllEventsFromAGroup,
    GroupEventsKernel,
    GroupPackage,
    ScraperTypes,
    TimeInfo,
)
from calendar_event_engine.types.submission_handlers import RunnerSubmission


def _event(title: str = "Event", **kwargs) -> GenericEvent:
    info = {"mobilizon": {"groupID": 1}}
    return GenericEvent(info, title, "2030-01-01T10:00:00+00:00", **kwargs)


def _kernel(name: str, scraper_type=ScraperTypes.ICAL, time_info=None):
    return GroupEventsKernel(_event(), name, [name], scraper_type, "", time_info)


@pytest.fixture
def slack():
    hook = MagicMock()
    notifications.set_slack_webhook(hook)
    yield hook
    notifications.set_slack_webhook(None)


class _FlakyScraper(Scraper):
    """Fails for the group named "broken", returns one event for any other."""

    def __init__(self):
        self.closed = False

    def connect_to_source(self):
        pass

    def close_connection_to_source(self):
        self.closed = True

    def get_source_type(self):
        return ScraperTypes.ICAL

    def retrieve_from_source(self, event_kernel=None):
        if event_kernel.group_name == "broken":
            raise KeyError("unexpected format")
        return [
            AllEventsFromAGroup(
                [_event(event_kernel.group_name)], event_kernel, event_kernel.group_name
            )
        ]


# --- Scheduling ---------------------------------------------------------------


@pytest.mark.parametrize(
    "now, expected_hours",
    [
        (datetime(2026, 1, 1, 1, 0), 1),  # before 2am: later today
        (datetime(2026, 1, 1, 2, 0), 24),  # exactly 2am: tomorrow
        (datetime(2026, 1, 1, 23, 30), 2.5),  # late evening: tomorrow 2am
    ],
)
def test_days_to_sleep_targets_next_2am(now, expected_hours):
    assert _days_to_sleep(0, now) == expected_hours * 3600
    assert _days_to_sleep(2, now) == expected_hours * 3600 + 2 * 86400


# --- Notifications ------------------------------------------------------------


def test_slack_webhook_is_stored_and_used(slack):
    assert notifications.get_slack_webhook() is slack
    notifications.send_slack_alert("Title", "Text", notifications.Priority.HIGH)
    attachment = slack.send.call_args.kwargs["attachments"][0]
    assert attachment["title"] == "Title"
    assert attachment["color"] == notifications.Priority.HIGH.value


def test_slack_failure_does_not_raise(slack):
    slack.send.side_effect = RuntimeError("slack is down")
    notifications.send_slack_alert("Title", "Text", notifications.Priority.MEDIUM)


# --- Runner -------------------------------------------------------------------


def test_runner_continues_after_a_source_fails(cache_db, slack):
    scraper = _FlakyScraper()
    publisher = MobilizonUploader(test_mode=True, cache_db=cache_db)
    package = GroupPackage(
        {ScraperTypes.ICAL: [_kernel("broken"), _kernel("working")]}, "pkg", None
    )
    submission = RunnerSubmission(
        cache_db, {publisher: [package]}, True, {ScraperTypes.ICAL: scraper}
    )

    _runner(submission)

    titles = [row[3] for row in cache_db.select_all_from_upload_table()]
    assert titles == ["working"]
    assert scraper.closed
    assert slack.send.call_count == 1


def test_runner_skips_scraper_types_without_a_scraper(cache_db):
    publisher = MobilizonUploader(test_mode=True, cache_db=cache_db)
    package = GroupPackage({ScraperTypes.CUSTOM: [_kernel("custom")]}, "pkg", None)
    _runner(RunnerSubmission(cache_db, {publisher: [package]}, True, {}))
    assert cache_db.select_all_from_upload_table().fetchall() == []


# --- Normalization ------------------------------------------------------------


def _head_response(content_type: str, status: int = 200) -> httpx2.Response:
    return httpx2.Response(
        status,
        headers={"Content-Type": content_type},
        request=httpx2.Request("HEAD", "https://example.com/a.png"),
    )


def test_normalize_checks_each_picture_once():
    events = [_event(picture="https://example.com/a.png") for _ in range(3)]
    checked: dict[str, bool] = {}
    with patch(
        "httpx2.head", return_value=_head_response("image/png; charset=binary")
    ) as head:
        for event in events:
            normalize_generic_event(event, checked)
    assert head.call_count == 1
    assert all(e.picture == "https://example.com/a.png" for e in events)


@pytest.mark.parametrize(
    "head_kwargs",
    [
        {"return_value": _head_response("text/html")},
        {"return_value": _head_response("image/png", status=404)},
        {"side_effect": httpx2.ConnectError("down")},
    ],
)
def test_normalize_blanks_unusable_pictures(head_kwargs):
    event = _event(picture="https://example.com/a.png", online_address="not a url")
    with patch("httpx2.head", **head_kwargs):
        normalize_generic_event(event)
    assert event.picture == ""
    assert event.online_address == ""


def test_publisher_does_not_check_pictures_of_cached_events(cache_db):
    publisher = MobilizonUploader(test_mode=True, cache_db=cache_db)
    event = _event(picture="https://example.com/a.png")
    batch = [AllEventsFromAGroup([event], _kernel("cal"), "cal")]
    with patch("httpx2.head", return_value=_head_response("image/png")) as head:
        assert len(publisher.upload(copy.deepcopy(batch))) == 1
        assert publisher.upload(copy.deepcopy(batch)) == []
    assert head.call_count == 1


# --- Static scraper -----------------------------------------------------------


def test_static_scraper_keeps_slots_before_the_end_date():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    end_date = now + timedelta(days=3)
    # Next occurrence of `soon` is before the end date, `late` is after it.
    soon, late = now + timedelta(days=1), now + timedelta(days=5)
    times = [
        [late.isoformat(), (late + timedelta(hours=1)).isoformat()],
        [soon.isoformat(), (soon + timedelta(hours=1)).isoformat()],
    ]
    kernel = _kernel(
        "market", ScraperTypes.STATIC, TimeInfo(times, end_date.isoformat())
    )

    events = hydrate_event_template_with_legitimate_times(kernel)

    assert [datetime.fromisoformat(e.begins_on) for e in events] == [soon]
