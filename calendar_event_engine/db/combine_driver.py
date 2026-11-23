import sqlite3
from dataclasses import dataclass
from datetime import datetime

from calendar_event_engine.db.event_source_driver import EventSourceDriver
from calendar_event_engine.db.uploaded_events_driver import UploadedEventsDriver
from calendar_event_engine.logger import create_logger_from_designated_logger

logger = create_logger_from_designated_logger(__name__)

_UE = UploadedEventsDriver.uploaded_events_table_name
_ES = EventSourceDriver.event_source_table_name
_JOIN = f"{_UE} INNER JOIN {_ES} ON {_UE}.id = {_ES}.id"


@dataclass
class CachedEvent:
    """
    An event that was already published.

    Args:
        row_id: Primary key of the cached row
        remote_id: The publishers ID for the event, used to update it
        uuid: The publishers UUID for the event
        site: The site it was published to, None for rows cached before sites
            were recorded
        content_hash: Fingerprint of the published version, None for rows cached
            before fingerprints were recorded
        source_event_id: The source's own ID for the event, if known
    """

    row_id: int
    remote_id: str
    uuid: str
    site: str | None
    content_hash: str | None
    source_event_id: str | None


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

    def find_uploaded_event(
        self,
        calendar_id: str,
        site: str,
        source_event_id: str | None,
        date: str,
        title: str,
    ) -> CachedEvent | None:
        """
        The cached row for a scraped event published to `site`, if any.

        An event is first looked up by the source's own ID, which survives a change
        of title or time. Only events that haven't started more than a day ago are
        matched that way, so a source reusing an ID (e.g. a page URL) for a later
        occurrence doesn't move the earlier one. Otherwise the event is looked up
        by its start time and title, as older caches and sources without IDs require.
        Rows cached before the site was recorded match every site.
        """
        columns = f"""{_UE}.id, {_UE}.user_id, {_UE}.uuid, {_UE}.site,
            {_UE}.content_hash, {_ES}.source_event_id"""
        site_matches = f"({_UE}.site IS NULL OR {_UE}.site = ?)"
        # Prefer the row recorded for this very site over a legacy one.
        order = f"ORDER BY {_UE}.site IS NULL, {_UE}.id DESC LIMIT 1"

        fetched = None
        if source_event_id is not None:
            fetched = self._connection.execute(
                f"""SELECT {columns} FROM {_JOIN}
                    WHERE calendar_id = ? AND source_event_id = ? AND {site_matches}
                    AND datetime(date) >= datetime('now', '-1 day')
                    {order}""",
                (calendar_id, source_event_id, site),
            ).fetchone()
        if fetched is None:
            fetched = self._connection.execute(
                f"""SELECT {columns} FROM {_JOIN}
                    WHERE calendar_id = ? AND date = ? AND title = ? AND {site_matches}
                    AND (source_event_id IS NULL OR source_event_id = ?)
                    {order}""",
                (calendar_id, date, title, site, source_event_id),
            ).fetchone()
        if fetched is None:
            return None
        return CachedEvent(*fetched)
