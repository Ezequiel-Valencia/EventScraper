import sqlite3
from datetime import datetime
from sqlite3 import Cursor

from calendar_event_engine.db.event_source_driver import EventSourceDriver
from calendar_event_engine.db.uploaded_events_driver import UploadedEventsDriver
from calendar_event_engine.logger import create_logger_from_designated_logger

logger = create_logger_from_designated_logger(__name__)

class CombineDBDriver:
    event_source_table_name: str = EventSourceDriver.event_source_table_name
    uploaded_events_table_name: str = UploadedEventsDriver.uploaded_events_table_name

    allColumns = f"""{uploaded_events_table_name}.uuid, {uploaded_events_table_name}.user_id,
        {uploaded_events_table_name}.title, {uploaded_events_table_name}.date, 
        {uploaded_events_table_name}.group_id, {uploaded_events_table_name}.group_name,
        {event_source_table_name}.websiteURL, {event_source_table_name}.calendar_id, 
        {event_source_table_name}.sourceType"""



    def select_all_rows_with_calendar_id(self, db_connection: sqlite3.Connection, calendar_id: str) -> Cursor:
        db_cursor = db_connection.cursor()
        # Comma at the end of (groupID,) turns it into a tuple
        res = db_cursor.execute(f"""SELECT {self.allColumns} FROM {self.uploaded_events_table_name} 
                                INNER JOIN {self.event_source_table_name} ON 
                                {self.uploaded_events_table_name}.id={self.event_source_table_name}.id
                                WHERE calendar_id = ?""", (calendar_id,))
        return res

    def get_last_event_date_for_source_id(self, db_connection: sqlite3.Connection, calendar_id) -> datetime:
        db_cursor = db_connection.cursor()
        res = db_cursor.execute(f"""SELECT date FROM {self.uploaded_events_table_name}
                                INNER JOIN {self.event_source_table_name} ON 
                                {self.uploaded_events_table_name}.id={self.event_source_table_name}.id
                                WHERE calendar_id = ?
                                ORDER BY date DESC LIMIT 1""", (calendar_id,))
        # Conversion to ISO format does not like the Z, that represents UTC aka no time zone
        # so using +00:00 is an equivalent to it
        date_string = res.fetchone()[0]
        logger.debug(f"Last date found for calendar ID {calendar_id}: {date_string}")
        return datetime.fromisoformat(date_string)

    def entry_already_in_cache(self, db_connection: sqlite3.Connection, date:str, title:str, calendar_id:str) -> bool:
        db_cursor = db_connection.cursor()
        res = db_cursor.execute(f"""SELECT {self.allColumns} FROM {self.uploaded_events_table_name}
                                INNER JOIN {self.event_source_table_name} ON 
                                {self.uploaded_events_table_name}.id={self.event_source_table_name}.id
                                WHERE date = ? AND title = ? AND calendar_id = ?""", (date, title, calendar_id))
        query = res.fetchall()
        if len(query) > 0:
            return True
        return False

