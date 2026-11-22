"""Unit tests for publishing to several named publishers with a router."""

from unittest.mock import MagicMock, patch

import pytest

from calendar_event_engine.Runner import _runner, start_event_engine
from calendar_event_engine.publishers.mobilizon.uploader import MobilizonUploader
from calendar_event_engine.scrapers.abc_scraper import Scraper
from calendar_event_engine.types.custom_scraper import CustomScraperJob
from calendar_event_engine.types.generics import GenericEvent
from calendar_event_engine.types.submission import (
    AllEventsFromAGroup,
    GroupEventsKernel,
    GroupPackage,
    ScraperTypes,
)
from calendar_event_engine.types.submission_handlers import RunnerSubmission


def _event(title: str) -> GenericEvent:
    return GenericEvent(
        {"mobilizon": {"groupID": 1}}, title, "2030-01-01T10:00:00+00:00"
    )


def _kernel(name: str, **source_info) -> GroupEventsKernel:
    return GroupEventsKernel(
        _event(name), name, [name], ScraperTypes.ICAL, "", source_info=source_info
    )


class _RecordingUploader(MobilizonUploader):
    """A test-mode uploader that remembers the titles it uploaded."""

    def __init__(self, cache_db, fail_connect: bool = False):
        super().__init__(test_mode=True, cache_db=cache_db)
        self.fail_connect = fail_connect
        self.uploaded: list[str] = []
        self.connects = 0
        self.closes = 0

    def connect(self):
        self.connects += 1
        if self.fail_connect:
            raise ConnectionError("instance is down")

    def close(self):
        self.closes += 1

    def upload_individual_event(self, event_to_upload):
        self.uploaded.append(event_to_upload.title)
        return super().upload_individual_event(event_to_upload)


class _TitlesScraper(Scraper):
    """Returns one batch per kernel with the given event titles."""

    def __init__(self, titles: list[str]):
        self.titles = titles

    def connect_to_source(self):
        pass

    def close_connection_to_source(self):
        pass

    def get_source_type(self):
        return ScraperTypes.ICAL

    def retrieve_from_source(self, event_kernel=None):
        return [
            AllEventsFromAGroup(
                [_event(t) for t in self.titles],
                event_kernel,
                event_kernel.group_name,
            )
        ]


def _submission(cache_db, kernels, titles, submission_publisher=None):
    package = GroupPackage({ScraperTypes.ICAL: kernels}, "pkg", None)
    submission_publisher = submission_publisher or MagicMock()
    return RunnerSubmission(
        cache_db,
        {submission_publisher: [package]},
        True,
        {ScraperTypes.ICAL: _TitlesScraper(titles)},
    )


def _cached_titles(cache_db) -> list[str]:
    return sorted(row[3] for row in cache_db.select_all_from_upload_table())


def _by_family_friendly(event, kernel):
    return "family" if kernel.source_info.get("family_friendly") else "nightlife"


def test_events_go_only_to_their_routed_publisher(cache_db):
    family, nightlife = _RecordingUploader(cache_db), _RecordingUploader(cache_db)
    submission = _submission(
        cache_db,
        [_kernel("park", family_friendly=True), _kernel("bar", family_friendly=False)],
        ["a", "b"],
    )

    _runner(
        submission,
        publishers={"family": family, "nightlife": nightlife},
        route_event=_by_family_friendly,
    )

    assert family.uploaded == ["a", "b"]
    assert nightlife.uploaded == ["a", "b"]
    groups = [row[6] for row in cache_db.select_all_from_upload_table()]
    assert sorted(groups) == ["bar", "bar", "park", "park"]
    assert (family.connects, family.closes) == (1, 1)
    assert (nightlife.connects, nightlife.closes) == (1, 1)


def test_one_group_can_be_split_across_publishers(cache_db):
    family, nightlife = _RecordingUploader(cache_db), _RecordingUploader(cache_db)
    submission = _submission(
        cache_db, [_kernel("venue")], ["Kids Show", "Late Show", "Kids Art"]
    )

    def route(event, kernel):
        return "family" if event.title.startswith("Kids") else "nightlife"

    with patch.object(family, "upload", wraps=family.upload) as family_upload:
        _runner(
            submission,
            publishers={"family": family, "nightlife": nightlife},
            route_event=route,
        )

    assert family.uploaded == ["Kids Show", "Kids Art"]
    assert nightlife.uploaded == ["Late Show"]
    (batch,) = family_upload.call_args.args
    assert batch[0].event_kernel.group_name == "venue"
    assert batch[0].calendar_id == "venue"


def test_none_and_unknown_routes_are_skipped_and_not_cached(cache_db):
    family = _RecordingUploader(cache_db)
    routes = {"keep": "family", "skip": None, "typo": "famly"}
    submission = _submission(cache_db, [_kernel("venue")], list(routes))

    _runner(
        submission,
        publishers={"family": family},
        route_event=lambda event, kernel: routes[event.title],
    )

    assert family.uploaded == ["keep"]
    assert _cached_titles(cache_db) == ["keep"]

    # Once routed somewhere, the previously skipped events are uploaded.
    _runner(
        submission, publishers={"family": family}, route_event=lambda e, k: "family"
    )
    assert family.uploaded == ["keep", "skip", "typo"]


def test_a_failing_router_skips_only_that_event(cache_db):
    family = _RecordingUploader(cache_db)

    def route(event, kernel):
        if event.title == "bad":
            raise KeyError("oops")
        return "family"

    _runner(
        _submission(cache_db, [_kernel("venue")], ["bad", "good"]),
        publishers={"family": family},
        route_event=route,
    )
    assert family.uploaded == ["good"]


def test_a_publisher_that_cannot_connect_does_not_stop_the_others(cache_db):
    down = _RecordingUploader(cache_db, fail_connect=True)
    up = _RecordingUploader(cache_db)
    submission = _submission(
        cache_db,
        [_kernel("park", family_friendly=True), _kernel("bar", family_friendly=False)],
        ["a"],
    )

    _runner(
        submission,
        publishers={"family": down, "nightlife": up},
        route_event=_by_family_friendly,
    )

    assert down.uploaded == []
    assert down.closes == 0
    assert up.uploaded == ["a"]
    # Only the nightlife event is cached, so the family one is retried later.
    assert [row[6] for row in cache_db.select_all_from_upload_table()] == ["bar"]


def test_single_named_publisher_without_router_gets_everything(cache_db):
    only = _RecordingUploader(cache_db)
    submission_publisher = MagicMock()
    _runner(
        _submission(cache_db, [_kernel("venue")], ["a", "b"], submission_publisher),
        publishers={"only": only},
    )
    assert only.uploaded == ["a", "b"]
    submission_publisher.connect.assert_not_called()
    submission_publisher.upload.assert_not_called()


def test_no_publishers_keeps_the_submission_publisher(cache_db):
    publisher = _RecordingUploader(cache_db)
    _runner(_submission(cache_db, [_kernel("venue")], ["a"], publisher))
    assert publisher.uploaded == ["a"]
    assert (publisher.connects, publisher.closes) == (1, 1)


def test_custom_scraper_list_is_routed(cache_db):
    family, nightlife = _RecordingUploader(cache_db), _RecordingUploader(cache_db)

    class _Custom(_TitlesScraper):
        def retrieve_from_source(self, event_kernel=None):
            return super().retrieve_from_source(_kernel("custom", family_friendly=True))

    _runner(
        _submission(cache_db, [], []),
        custom_scrapers=[CustomScraperJob("custom", "", _Custom(["c"]))],
        publishers={"family": family, "nightlife": nightlife},
        route_event=_by_family_friendly,
    )
    assert family.uploaded == ["c"]
    assert nightlife.uploaded == []


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"publishers": {"a": MagicMock(), "b": MagicMock()}}, "no route_event"),
        ({"publishers": {}}, "at least one"),
        ({"route_event": lambda e, k: "a"}, "needs named publishers"),
        ({"custom_scrapers": []}, "as a list"),
    ],
)
def test_invalid_options_fail_at_startup(cache_db, kwargs, message):
    with patch("calendar_event_engine.Runner.get_runner_submission") as load:
        with pytest.raises(ValueError, match=message):
            start_event_engine("https://example.com/s.json", cache_db, **kwargs)
    load.assert_not_called()
