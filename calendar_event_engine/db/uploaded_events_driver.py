import sqlite3
from dataclasses import dataclass


@dataclass
class UploadedEventRow:
    """
    Args:
        uuid: The publishers UUID for the event uploaded
        user_id: The publishers id of the user who uploaded this event
        title: Title of the event
        date: ISO 8601 start time, e.g. 2025-05-25T10:00:00-04:00
        group_id: The publishers ID for the group affiliated with this event
        group_name: Name of the group affiliated with this event
    """

    uuid: str
    user_id: str
    title: str
    date: str
    group_id: int
    group_name: str


class UploadedEventsDriver:
    uploaded_events_table_name = "uploaded_events"

    def __init__(self, db_connection: sqlite3.Connection):
        self._connection = db_connection
        db_connection.execute(f"""CREATE TABLE IF NOT EXISTS {self.uploaded_events_table_name}
                                  (id INTEGER PRIMARY KEY, uuid text, user_id text,
                                  title text, date DATE, group_id integer, group_name text)""")

    def delete_all_month_old_events(self) -> None:
        # https://www.sqlite.org/lang_datefunc.html
        # datetime() normalises the stored offsets to UTC before comparing.
        with self._connection:
            self._connection.execute(
                f"DELETE FROM {self.uploaded_events_table_name} WHERE datetime(date) < datetime('now', '-1 month')"
            )

    def select_all_from_upload_table(self) -> sqlite3.Cursor:
        return self._connection.execute(
            f"SELECT * FROM {self.uploaded_events_table_name}"
        )

    def insert_uploaded_event(self, row_to_add: UploadedEventRow) -> int:
        """
        Returns the primary key for the row when it gets inserted.
        Does not commit; the caller owns the transaction.
        """
        db_cursor = self._connection.execute(
            f"INSERT INTO {self.uploaded_events_table_name} (uuid, user_id, title, date, group_id, group_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                row_to_add.uuid,
                row_to_add.user_id,
                row_to_add.title,
                row_to_add.date,
                row_to_add.group_id,
                row_to_add.group_name,
            ),
        )
        primary_key = db_cursor.lastrowid
        assert primary_key is not None
        return primary_key
