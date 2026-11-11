import sqlite3
from dataclasses import dataclass

from calendar_event_engine.db.uploaded_events_driver import UploadedEventsDriver


@dataclass
class EventSource:
    """
    Args:
        uuid: The publishers UUID for the event uploaded
        website_url: The events website of origin
        calendar_id: The calendar where the event was sourced from
        source_type: Source type
    """

    uuid: str
    website_url: str
    calendar_id: str
    source_type: str


class EventSourceDriver:
    event_source_table_name = "event_source"

    def __init__(self, db_connection: sqlite3.Connection):
        self._connection = db_connection
        uploaded = UploadedEventsDriver.uploaded_events_table_name
        with db_connection:
            db_connection.execute(f"""CREATE TABLE IF NOT EXISTS {self.event_source_table_name}
                                      (id INTEGER, uuid text, websiteURL text, calendar_id text, sourceType text,
                                      FOREIGN KEY (id) REFERENCES {uploaded}(id) ON DELETE CASCADE)""")
            # Every cache lookup filters on calendar_id and joins on id.
            db_connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.event_source_table_name}_calendar_id "
                f"ON {self.event_source_table_name} (calendar_id, id)"
            )
            db_connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.event_source_table_name}_id "
                f"ON {self.event_source_table_name} (id)"
            )
            # Databases created before foreign keys were enforced can hold rows
            # whose uploaded event was already deleted.
            db_connection.execute(
                f"DELETE FROM {self.event_source_table_name} "
                f"WHERE id NOT IN (SELECT id FROM {uploaded})"
            )

    def select_all_from_event_source_table(self) -> sqlite3.Cursor:
        return self._connection.execute(f"SELECT * FROM {self.event_source_table_name}")

    def insert_uploaded_event(
        self, foreign_key: int, event_source: EventSource
    ) -> None:
        """Does not commit; the caller owns the transaction."""
        self._connection.execute(
            f"INSERT INTO {self.event_source_table_name} VALUES (?, ?, ?, ?, ?)",
            (
                foreign_key,
                event_source.uuid,
                event_source.website_url,
                event_source.calendar_id,
                event_source.source_type,
            ),
        )
