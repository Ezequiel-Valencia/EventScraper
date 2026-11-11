from datetime import datetime, timedelta, timezone

from calendar_event_engine.db.db_cache import SQLiteDB
from calendar_event_engine.db.event_source_driver import EventSource
from calendar_event_engine.db.uploaded_events_driver import UploadedEventRow
import unittest

from calendar_event_engine.types.submission import ScraperTypes


# TODO: Test getting the last event uploaded for a specific group


# Group 2's events must stay "recent" whenever the tests run, or the month-old
# cleanup would delete them too.
_SOON = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0)
_SOON_ISO = _SOON.isoformat()
_LATER_ISO = (_SOON + timedelta(days=31)).isoformat()


class TestEventTable(unittest.TestCase):
    group1Name = "groupName1"
    group2Name = "groupName2"
    sourceGroup1 = "source1"
    sourceGroup2 = "source2"

    group1: [UploadedEventRow] = [
        UploadedEventRow(
            "uuid1", "id1", "title1", "2022-05-04T10:00:00-04:00", "gID1", group1Name
        ),
        UploadedEventRow(
            "uuid2", "id1", "title1", "2022-05-04T10:00:00-04:00", "gID1", group1Name
        ),
        UploadedEventRow(
            "uuid3", "id1", "title1", "2022-05-04T10:00:00-04:00", "gID1", group1Name
        ),
    ]
    group1Source: [EventSource] = [
        EventSource("uuid1", "web", sourceGroup1, ScraperTypes.GOOGLE_CAL.value),
        EventSource("uuid2", "web", sourceGroup1, ScraperTypes.GOOGLE_CAL.value),
        EventSource("uuid3", "web", sourceGroup1, ScraperTypes.GOOGLE_CAL.value),
    ]

    group2: [UploadedEventRow] = [
        UploadedEventRow("uuid4", "id1", "title1", _SOON_ISO, "gID2", group2Name),
        UploadedEventRow("uuid5", "id1", "title1", _SOON_ISO, "gID2", group2Name),
        UploadedEventRow("uuid6", "id1", "title1", _SOON_ISO, "gID2", group2Name),
        UploadedEventRow("uuid7", "id1", "title1", _LATER_ISO, "gID2", group2Name),
    ]
    group2Source: [EventSource] = [
        EventSource("uuid4", "web", sourceGroup2, ScraperTypes.STATIC.value),
        EventSource("uuid5", "web", sourceGroup2, ScraperTypes.STATIC.value),
        EventSource("uuid6", "web", sourceGroup2, ScraperTypes.STATIC.value),
        EventSource("uuid7", "web", sourceGroup2, ScraperTypes.STATIC.value),
    ]

    def insertGroup(self, db: SQLiteDB, group: [], groupSource: []):
        for k in range(len(group)):
            db.insert_uploaded_event(group[k], groupSource[k])

    def test_GroupInsertionAndRetrieval(self):
        db = SQLiteDB(True)
        self.addCleanup(db.close)
        self.insertGroup(db, self.group1, self.group1Source)

        query = db.select_all_from_upload_table().fetchall()
        self.assertEqual(
            len(query), len(self.group1), "Ensure group 1 has been fully inserted"
        )

        query = db.select_all_rows_with_calendar_id(self.sourceGroup1).fetchall()
        self.assertEqual(len(query), len(self.group1), "Getting groups work when alone")

        self.insertGroup(db, self.group2, self.group2Source)
        query = db.select_all_from_upload_table().fetchall()
        self.assertEqual(
            len(query),
            (len(self.group1) + len(self.group2)),
            "Inserting another unique group ensures all are in",
        )

        query = db.select_all_rows_with_calendar_id(self.sourceGroup2).fetchall()
        self.assertEqual(
            len(query),
            len(self.group2),
            "Ensure only selected group is taken when there's multiple groups",
        )
        for row in query:
            self.assertEqual(row[7], self.sourceGroup2)

    def test_RemoveOldEvents(self):
        db = SQLiteDB(True)
        self.addCleanup(db.close)

        self.insertGroup(db, self.group1, self.group1Source)
        self.insertGroup(db, self.group2, self.group2Source)

        db.delete_all_month_old_events()
        query = db.select_all_from_upload_table().fetchall()
        self.assertEqual(
            len(query),
            len(self.group2),
            "Ensure that all old events are deleted and only new ones are left",
        )
        for row in query:
            self.assertEqual(row[6], self.group2Name)

    # TODO: Better test would be uniqueness based on combined constraints
    # def test_UniqueInsertion(self):
    #     db = SQLiteDB(True)
    #
    #     self.insertGroup(db, self.group1, self.group1Source)
    #     self.insertGroup(db, self.group2, self.group2Source)
    #     # Ensure only Unique UUIDs are inserted
    #     self.assertRaises(sqlite3.IntegrityError, db.insert_uploaded_event, self.group2[0], self.group2Source[0])
    #

    def test_IdempotentInsertionsAndCaching(self):
        db = SQLiteDB(True)
        self.addCleanup(db.close)

        self.insertGroup(db, self.group2, self.group2Source)
        query = db.select_all_from_upload_table().fetchall()

        for k in range(len(self.group2)):
            inCache = db.entry_already_in_cache(
                self.group2[k].date,
                self.group2[k].title,
                self.group2Source[k].calendar_id,
            )
            if not inCache:
                db.insert_uploaded_event(self.group2[k], self.group2Source[k])

        query2 = db.select_all_from_upload_table().fetchall()
        self.assertEqual(query, query2)

        self.assertEqual(False, db.no_entries_with_source_id(self.sourceGroup2))
        self.assertEqual(True, db.no_entries_with_source_id(self.sourceGroup1))

    def test_GetLastEvent(self):
        db = SQLiteDB(True)
        self.addCleanup(db.close)

        self.insertGroup(db, self.group2, self.group2Source)
        lastEventUploaded = db.get_last_event_date_for_source_id(self.sourceGroup2)
        assert lastEventUploaded is not None
        self.assertEqual(_LATER_ISO, lastEventUploaded.isoformat())

    def test_RemoveOldEventsCascadesToEventSource(self):
        db = SQLiteDB(True)
        self.addCleanup(db.close)
        self.insertGroup(db, self.group1, self.group1Source)
        self.insertGroup(db, self.group2, self.group2Source)

        db.delete_all_month_old_events()
        sources = db.select_all_from_event_source_table().fetchall()
        self.assertEqual(len(self.group2), len(sources))
        self.assertTrue(db.no_entries_with_source_id(self.sourceGroup1))

    def test_GetLastEventComparesInstantsNotStrings(self):
        db = SQLiteDB(True)
        self.addCleanup(db.close)
        # As strings "...T23:00:00-08:00" sorts first, but it is the later instant.
        rows = [
            ("a", "2030-01-01T23:00:00-08:00"),
            ("b", "2030-01-02T01:00:00+00:00"),
        ]
        for uuid, date in rows:
            db.insert_uploaded_event(
                UploadedEventRow(uuid, "id", "title", date, 1, "group"),
                EventSource(uuid, "web", "cal", ScraperTypes.ICAL.value),
            )
        last = db.get_last_event_date_for_source_id("cal")
        self.assertEqual("2030-01-01T23:00:00-08:00", last.isoformat())

    def test_FailedInsertLeavesNoPartialRows(self):
        db = SQLiteDB(True)
        self.addCleanup(db.close)
        bad_source = EventSource("uuid", "web", "cal", ScraperTypes.ICAL.value)
        bad_source.website_url = object()  # sqlite3 can't bind this
        with self.assertRaises(Exception):
            db.insert_uploaded_event(self.group1[0], bad_source)
        self.assertEqual([], db.select_all_from_upload_table().fetchall())


if __name__ == "__main__":
    unittest.main()
