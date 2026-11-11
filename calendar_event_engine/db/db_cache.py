import os
import sqlite3
from datetime import datetime

from calendar_event_engine.db.combine_driver import CombineDBDriver
from calendar_event_engine.db.event_source_driver import EventSourceDriver, EventSource
from calendar_event_engine.db.uploaded_events_driver import (
    UploadedEventsDriver,
    UploadedEventRow,
)
from calendar_event_engine.logger import create_logger_from_designated_logger

logger = create_logger_from_designated_logger(__name__)


def _database_path() -> str:
    cache_db_dir = os.environ.get("CACHE_DB_PATH")
    if cache_db_dir is not None:
        return os.path.join(cache_db_dir, "event_cache.db")
    return os.path.join("..", "event_cache.db")


class SQLiteDB:
    """Records which events were already published, so they are not published twice."""

    sql_db_connection: sqlite3.Connection

    def __init__(self, test_mode: bool = False):
        self.sql_db_connection = sqlite3.connect(
            ":memory:" if test_mode else _database_path()
        )
        # SQLite ignores FOREIGN KEY clauses (and so ON DELETE CASCADE) unless
        # this is enabled on every connection.
        self.sql_db_connection.execute("PRAGMA foreign_keys = ON")

        self.ue_driver = UploadedEventsDriver(self.sql_db_connection)
        self.es_driver = EventSourceDriver(self.sql_db_connection)
        self.com_driver = CombineDBDriver(self.sql_db_connection)

    def close(self):
        self.sql_db_connection.close()

    def __enter__(self) -> "SQLiteDB":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def delete_all_month_old_events(self) -> None:
        self.ue_driver.delete_all_month_old_events()

    def select_all_rows_with_calendar_id(self, calendar_id: str) -> sqlite3.Cursor:
        return self.com_driver.select_all_rows_with_calendar_id(calendar_id)

    def get_last_event_date_for_source_id(self, calendar_id: str) -> datetime | None:
        return self.com_driver.get_last_event_date_for_source_id(calendar_id)

    def no_entries_with_source_id(self, calendar_id: str) -> bool:
        return not self.com_driver.has_entries_with_calendar_id(calendar_id)

    def entry_already_in_cache(self, date: str, title: str, source_id: str) -> bool:
        return self.com_driver.entry_already_in_cache(date, title, source_id)

    def insert_uploaded_event(
        self, row_to_add: UploadedEventRow, event_source: EventSource
    ) -> None:
        # Both rows are written in one transaction so a failure can't leave an
        # uploaded event without its source (or vice versa).
        with self.sql_db_connection:
            primary_key = self.ue_driver.insert_uploaded_event(row_to_add)
            self.es_driver.insert_uploaded_event(primary_key, event_source)

    def select_all_from_upload_table(self) -> sqlite3.Cursor:
        return self.ue_driver.select_all_from_upload_table()

    def select_all_from_event_source_table(self) -> sqlite3.Cursor:
        return self.es_driver.select_all_from_event_source_table()
