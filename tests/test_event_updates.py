"""Published events that change are updated, and the site each went to is recorded."""

import copy
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from calendar_event_engine.Runner import _publish
from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.publishers.mobilizon.uploader import MobilizonUploader
from calendar_event_engine.types.generics import GenericEvent
from calendar_event_engine.types.submission import (
    AllEventsFromAGroup,
    GroupEventsKernel,
    ScraperTypes,
)

_START = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
_START_ISO = _START.isoformat()


class _Uploader(MobilizonUploader):
    """A test-mode uploader that records what it created and updated."""

    def __init__(self, cache_db, site_name="ctgrassroots"):
        super().__init__(test_mode=True, cache_db=cache_db, site_name=site_name)
        self.created: list[str] = []
        self.updated: list[tuple[str, str]] = []

    def upload_individual_event(self, event_to_upload):
        self.created.append(event_to_upload.title)
        return super().upload_individual_event(event_to_upload)

    def update_individual_event(self, remote_event_id, event_to_update):
        self.updated.append((remote_event_id, event_to_update.title))
        return super().update_individual_event(remote_event_id, event_to_update)


def _event(title="Jazz", source_event_id=None, begins_on=_START_ISO, **fields):
    return GenericEvent(
        {"mobilizon": {"groupID": 1}},
        title,
        begins_on,
        description=fields.pop("description", "About it"),
        source_event_id=source_event_id,
        **fields,
    )


def _batch(*events, calendar_id="cal"):
    kernel = GroupEventsKernel(_event(), "Group", [calendar_id], ScraperTypes.ICAL, "")
    return [AllEventsFromAGroup(list(events), kernel, calendar_id)]


def _rows(cache_db):
    """(title, date, site, user_id, updated) of each cached event."""
    return cache_db.sql_db_connection.execute(
        "SELECT title, date, site, user_id, updated_at IS NOT NULL "
        "FROM uploaded_events ORDER BY id"
    ).fetchall()


def test_unchanged_events_are_skipped(cache_db):
    uploader = _Uploader(cache_db)
    assert len(uploader.upload(_batch(_event(source_event_id="uid-1")))) == 1
    assert uploader.upload(_batch(_event(source_event_id="uid-1"))) == []
    assert uploader.created == ["Jazz"]
    assert uploader.updated == []


def test_changed_event_is_updated_not_republished(cache_db):
    uploader = _Uploader(cache_db)
    uploader.upload(_batch(_event(source_event_id="uid-1")))
    [(_, _, _, remote_id, _)] = _rows(cache_db)

    later = (_START + timedelta(hours=1)).isoformat()
    changed = _event("Jazz Night", "uid-1", begins_on=later, description="New")
    assert [e.title for e in uploader.upload(_batch(changed))] == ["Jazz Night"]

    assert uploader.created == ["Jazz"]
    assert uploader.updated == [(remote_id, "Jazz Night")]
    assert _rows(cache_db) == [("Jazz Night", later, "ctgrassroots", remote_id, 1)]
    # The updated version is now the cached one.
    assert uploader.upload(_batch(_event("Jazz Night", "uid-1", later, description="New"))) == []


def test_without_source_id_a_changed_description_is_updated(cache_db):
    uploader = _Uploader(cache_db)
    uploader.upload(_batch(_event()))
    uploader.upload(_batch(_event(description="Now with a band")))
    assert uploader.created == ["Jazz"]
    assert [title for _, title in uploader.updated] == ["Jazz"]


def test_without_source_id_a_new_title_is_a_new_event(cache_db):
    uploader = _Uploader(cache_db)
    uploader.upload(_batch(_event("Jazz")))
    uploader.upload(_batch(_event("Blues")))
    assert uploader.created == ["Jazz", "Blues"]
    assert uploader.updated == []


def test_a_reused_source_id_falls_back_to_title_and_date(cache_db):
    # e.g. a page listing two shows that both link to the same URL.
    uploader = _Uploader(cache_db)
    later = (_START + timedelta(days=1)).isoformat()
    batch = _batch(_event("Show", "url"), _event("Show", "url", later))
    assert len(uploader.upload(copy.deepcopy(batch))) == 2
    assert uploader.upload(copy.deepcopy(batch)) == []
    assert uploader.updated == []


def test_a_source_id_of_a_past_event_is_not_reused(cache_db):
    uploader = _Uploader(cache_db)
    past = (_START - timedelta(days=7)).isoformat()
    uploader.upload(_batch(_event("Weekly", "url", past)))
    uploader.upload(_batch(_event("Weekly", "url")))
    assert uploader.created == ["Weekly", "Weekly"]
    assert uploader.updated == []


def test_failed_update_keeps_the_old_version_cached(cache_db):
    uploader = _Uploader(cache_db)
    uploader.upload(_batch(_event(source_event_id="uid-1")))

    def fail(remote_event_id, event_to_update):
        raise ConnectionError("down")

    uploader.update_individual_event = fail
    assert uploader.upload(_batch(_event("Renamed", "uid-1"))) == []
    assert [row[0] for row in _rows(cache_db)] == ["Jazz"]


def test_site_is_recorded_and_events_are_tracked_per_site(cache_db):
    grassroots = _Uploader(cache_db, site_name="ctgrassroots")
    underground = _Uploader(cache_db, site_name="underground")
    grassroots.upload(_batch(_event(source_event_id="uid-1")))
    underground.upload(_batch(_event(source_event_id="uid-1")))
    grassroots.upload(_batch(_event(source_event_id="uid-1")))

    assert [row[2] for row in _rows(cache_db)] == ["ctgrassroots", "underground"]
    assert (grassroots.created, underground.created) == (["Jazz"], ["Jazz"])


def test_routed_publishers_record_their_name_as_the_site(cache_db):
    uploader = _Uploader(cache_db, site_name=None)
    _publish(uploader, _batch(_event()), "underground")
    assert [row[2] for row in _rows(cache_db)] == ["underground"]


@pytest.mark.parametrize(
    "endpoint, site",
    [("https://ctgrassroots.org/api", "ctgrassroots.org"), (None, "mobilizon")],
)
def test_default_site_name_is_the_endpoint_host(monkeypatch, cache_db, endpoint, site):
    monkeypatch.delenv("MOBILIZON_ENDPOINT", raising=False)
    uploader = MobilizonUploader(True, cache_db, endpoint=endpoint)
    assert uploader.site_name == site


def test_old_cache_is_migrated_and_its_events_are_not_republished(
    monkeypatch, tmp_path
):
    # The schema before sites, fingerprints and source IDs were recorded.
    with sqlite3.connect(tmp_path / "event_cache.db") as old:
        old.execute(
            """CREATE TABLE uploaded_events (id INTEGER PRIMARY KEY, uuid text,
               user_id text, title text, date DATE, group_id integer, group_name text)"""
        )
        old.execute(
            """CREATE TABLE event_source (id INTEGER, uuid text, websiteURL text,
               calendar_id text, sourceType text)"""
        )
        old.execute(
            "INSERT INTO uploaded_events VALUES (1, 'u', '42', 'Jazz', ?, 1, 'Group')",
            (_START_ISO,),
        )
        old.execute("INSERT INTO event_source VALUES (1, 'u', '', 'cal', 'ICAL')")
    old.close()
    monkeypatch.setenv("CACHE_DB_PATH", str(tmp_path))

    with SQLiteDB() as cache_db:
        uploader = _Uploader(cache_db)
        # The version published back then is unknown, so it isn't republished...
        assert uploader.upload(_batch(_event(source_event_id="uid-1"))) == []
        assert uploader.created == uploader.updated == []
        # ...but is adopted, so later changes are noticed.
        assert _rows(cache_db) == [("Jazz", _START_ISO, "ctgrassroots", "42", 0)]
        uploader.upload(_batch(_event("Renamed", "uid-1")))
        assert uploader.updated == [("42", "Renamed")]

    # Reopening an already migrated cache works too.
    with SQLiteDB() as cache_db:
        assert [row[0] for row in _rows(cache_db)] == ["Renamed"]
