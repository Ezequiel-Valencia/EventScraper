import sqlite3
from datetime import datetime

from calendar_event_engine.db.event_source_driver import EventSourceDriver
from calendar_event_engine.db.uploaded_events_driver import UploadedEventsDriver
from calendar_event_engine.logger import create_logger_from_designated_logger

logger = create_logger_from_designated_logger(__name__)

_UE = UploadedEventsDriver.uploaded_events_table_name
_ES = EventSourceDriver.event_source_table_name
_JOIN = f"{_UE} INNER JOIN {_ES} ON {_UE}.id = {_ES}.id"


class CombineDBDriver:
    """Queries that span the uploaded_events and event_source tables."""

    allColumns = f"""{_UE}.uuid, {_UE}.user_id, {_UE}.title, {_UE}.date,
        {_UE}.group_id, {_UE}.group_name,
        {_ES}.websiteURL, {_ES}.calendar_id, {_ES}.sourceType"""

    def __init__(self, db_connection: sqlite3.Connection):
        self._connection = db_connection

    def select_all_rows_with_calendar_id(self, calendar_id: str) -> sqlite3.Cursor:
        return self._connection.execute(
            f"SELECT {self.allColumns} FROM {_JOIN} WHERE calendar_id = ?",
            (calendar_id,),
        )

    def has_entries_with_calendar_id(self, calendar_id: str) -> bool:
        res = self._connection.execute(
            f"SELECT EXISTS (SELECT 1 FROM {_JOIN} WHERE calendar_id = ?)",
            (calendar_id,),
        )
        return bool(res.fetchone()[0])

    def get_last_event_date_for_source_id(self, calendar_id: str) -> datetime | None:
        # Dates are stored with differing UTC offsets, so sort on the instant
        # they represent rather than on the raw string.
        res = self._connection.execute(
            f"""SELECT date FROM {_JOIN} WHERE calendar_id = ?
                ORDER BY datetime(date) DESC LIMIT 1""",
            (calendar_id,),
        )
        fetched = res.fetchone()
        if fetched is None:
            return None
        date_string = fetched[0]
        logger.debug(f"Last date found for calendar ID {calendar_id}: {date_string}")
        # Python < 3.11 cannot parse a trailing "Z", but "+00:00" is equivalent.
        return datetime.fromisoformat(date_string.replace("Z", "+00:00"))

    def entry_already_in_cache(self, date: str, title: str, calendar_id: str) -> bool:
        res = self._connection.execute(
            f"""SELECT EXISTS (SELECT 1 FROM {_JOIN}
                WHERE date = ? AND title = ? AND calendar_id = ?)""",
            (date, title, calendar_id),
        )
        return bool(res.fetchone()[0])
