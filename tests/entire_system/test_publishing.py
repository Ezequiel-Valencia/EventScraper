"""End to end: scrape -> normalize -> publish to a real Mobilizon -> cache."""

from datetime import datetime, timedelta, timezone

import pytest

from calendar_event_engine.Runner import _runner
from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.parser.submission import get_runner_submission
from calendar_event_engine.publishers.mobilizon.api import MobilizonAPI
from calendar_event_engine.publishers.mobilizon.uploader import MobilizonUploader
from calendar_event_engine.types.generics import GenericAddress, GenericEvent
from calendar_event_engine.types.submission import (
    AllEventsFromAGroup,
    GroupEventsKernel,
    ScraperTypes,
)
from tests.helpers import LocalHTTPServer
from tests.entire_system.helpers import (
    MobilizonGroup,
    MobilizonServer,
    create_group,
    fetch_event,
    fetch_group_events,
)

pytestmark = pytest.mark.entire_system

# Column positions in the uploaded_events table.
UUID, TITLE, GROUP_ID, GROUP_NAME = 1, 3, 5, 6


def _address() -> GenericAddress:
    return GenericAddress(
        geom="-72.6796498;41.7677107",
        locality="Hartford",
        postalCode="06103",
        street="350 Asylum St.",
        region="CT",
    )


def _mobilizon_info(group: MobilizonGroup) -> dict:
    return {
        "mobilizon": {
            "groupID": group.id,
            "defaultCategory": "music",
            "defaultTags": ["Music"],
        }
    }


def _upload_rows(cache_db: SQLiteDB) -> list[tuple]:
    return cache_db.select_all_from_upload_table().fetchall()


@pytest.mark.usefixtures("mobilizon_env")
def test_uploader_publishes_and_caches_events(
    fresh_api: MobilizonAPI, picture_url: str, cache_db: SQLiteDB
):
    # The uploader logs in as the same user that owns the group.
    mobilizon_group = create_group(fresh_api)
    mobilizon_api = fresh_api
    uploader = MobilizonUploader(test_mode=False, cache_db=cache_db)
    uploader.connect()

    template = GenericEvent(_mobilizon_info(mobilizon_group), "Template", "")
    kernel = GroupEventsKernel(
        template, "Uploader Group", ["cal-1"], ScraperTypes.ICAL, ""
    )
    events = [
        GenericEvent(
            _mobilizon_info(mobilizon_group),
            title=f"Uploaded event {i}",
            begins_on=f"2030-06-0{i}T19:00:00-04:00",
            ends_on=f"2030-06-0{i}T21:00:00-04:00",
            description="Scraped",
            online_address="https://example.com/event",
            physical_address=_address(),
            picture=picture_url,
        )
        for i in (1, 2)
    ]
    batch = [AllEventsFromAGroup(events, kernel, "cal-1")]

    uploaded = uploader.upload(batch)
    # A second upload of the same events is served from the cache.
    uploaded_again = uploader.upload(batch)
    uploader.close()

    assert len(uploaded) == 2
    assert uploaded_again == []

    rows = _upload_rows(cache_db)
    assert len(rows) == 2
    for row, event in zip(rows, events):
        assert row[TITLE] == event.title
        assert row[GROUP_ID] == mobilizon_group.id
        assert row[GROUP_NAME] == "Uploader Group"

        stored = fetch_event(mobilizon_api, row[UUID])
        assert stored["title"] == event.title
        assert stored["attributedTo"]["id"] == str(mobilizon_group.id)
        assert stored["category"] == "MUSIC"
        assert stored["picture"] is not None
        assert stored["physicalAddress"]["locality"] == "Hartford"

    assert len(fetch_group_events(mobilizon_api, mobilizon_group)) == 2


@pytest.mark.usefixtures("mobilizon_env")
def test_runner_publishes_static_events_end_to_end(
    fresh_api: MobilizonAPI,
    local_http_server: LocalHTTPServer,
    cache_db: SQLiteDB,
):
    mobilizon_api = fresh_api
    stonington, stamford = create_group(fresh_api), create_group(fresh_api)

    # Recurring weekly events whose first occurrence is in the past, so the
    # static scraper rolls them forward to next week.
    first_start = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )
    end_date = (first_start + timedelta(days=365)).isoformat()

    def static_kernel(group: MobilizonGroup, title: str, url: str) -> dict:
        return {
            "publisherInfo": {
                "mobilizon": {
                    "groupID": group.id,
                    "defaultCategory": "food_drink",
                    "defaultTags": ["Farmer Market"],
                }
            },
            "title": title,
            "defaultDescription": f"{title} description",
            "onlineAddress": url,
            "calendarIDs": [title],
            "calendarType": "STATIC",
            "defaultTimes": [
                [
                    first_start.isoformat(),
                    (first_start + timedelta(hours=4)).isoformat(),
                ]
            ],
            "endDate": end_date,
            "defaultLocation": {
                "locality": "Stonington",
                "postalCode": "06378",
                "street": "1 Main St.",
                "region": "CT",
                "geom": "-71.9056;41.3359",
            },
        }

    package_url = local_http_server.add_json(
        "farmers_market.json",
        {
            "name": "Farmers Markets",
            "description": "Test package",
            "groupKernels": {
                "Stonington": static_kernel(
                    stonington,
                    "Stonington Farmers Market",
                    "https://www.sviastonington.org/farmers-market",
                ),
                "Stamford": static_kernel(
                    stamford,
                    "Stamford Downtown Farmers Market",
                    "http://stamford-downtown.com/events/farmers-market/",
                ),
            },
        },
    )
    submission_url = local_http_server.add_json(
        "submission.json", {"Mobilizon": [package_url]}
    )

    submission = get_runner_submission(submission_url, False, cache_db)
    _runner(submission)

    rows = _upload_rows(cache_db)
    assert [(r[TITLE], r[GROUP_ID], r[GROUP_NAME]) for r in rows] == [
        ("Stonington Farmers Market", stonington.id, "Stonington"),
        ("Stamford Downtown Farmers Market", stamford.id, "Stamford"),
    ]

    sources = cache_db.select_all_from_event_source_table().fetchall()
    assert [(s[2], s[3], s[4]) for s in sources] == [
        ("https://www.sviastonington.org/farmers-market", "Stonington", "JSON"),
        ("http://stamford-downtown.com/events/farmers-market/", "Stamford", "JSON"),
    ]

    for row, group in zip(rows, (stonington, stamford)):
        stored = fetch_event(mobilizon_api, row[UUID])
        assert stored["title"] == row[TITLE]
        assert stored["attributedTo"]["id"] == str(group.id)
        assert stored["category"] == "FOOD_DRINK"
        assert [t["title"] for t in stored["tags"]] == ["Farmer Market"]
        assert stored["description"].startswith("Automatically scraped by event bot")
        assert datetime.fromisoformat(stored["beginsOn"]) > datetime.now(timezone.utc)

    # Running again must not publish duplicates.
    _runner(submission)
    assert _upload_rows(cache_db) == rows
    for group in (stonington, stamford):
        assert len(fetch_group_events(mobilizon_api, group)) == 1


def test_runner_does_not_publish_in_test_mode(
    mobilizon_server: MobilizonServer,
    mobilizon_api: MobilizonAPI,
    mobilizon_group: MobilizonGroup,
    local_http_server: LocalHTTPServer,
    monkeypatch: pytest.MonkeyPatch,
    cache_db: SQLiteDB,
):
    # Even with a reachable Mobilizon, test mode must never touch it.
    monkeypatch.setenv("MOBILIZON_ENDPOINT", mobilizon_server.endpoint)
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
    package_url = local_http_server.add_json(
        "test_mode_package.json",
        {
            "name": "Test mode",
            "groupKernels": {
                "Dry Run": {
                    "publisherInfo": {"mobilizon": {"groupID": mobilizon_group.id}},
                    "title": "Dry run event",
                    "onlineAddress": "https://example.com",
                    "calendarIDs": ["Dry run event"],
                    "calendarType": "STATIC",
                    "defaultTimes": [
                        [start.isoformat(), (start + timedelta(hours=1)).isoformat()]
                    ],
                    "endDate": (start + timedelta(days=30)).isoformat(),
                }
            },
        },
    )
    submission_url = local_http_server.add_json(
        "test_mode_submission.json", {"Mobilizon": [package_url]}
    )

    _runner(get_runner_submission(submission_url, True, cache_db))

    assert len(_upload_rows(cache_db)) == 1
    assert fetch_group_events(mobilizon_api, mobilizon_group) == []
