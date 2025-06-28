import os
import sqlite3
from datetime import datetime

from calendar_event_engine.db.combine_driver import CombineDBDriver
from calendar_event_engine.db.event_source_driver import EventSourceDriver, EventSource
from calendar_event_engine.db.uploaded_events_driver import UploadedEventsDriver, UploadedEventRow
from calendar_event_engine.logger import create_logger_from_designated_logger

from sqlite3 import Cursor

logger = create_logger_from_designated_logger(__name__)


class SQLiteDB:
    sql_db_connection: sqlite3.Connection
    es_driver: EventSourceDriver
    ue_driver: UploadedEventsDriver
    com_driver: CombineDBDriver
    __fake_UUID: int = 0

    def __init__(self, test_mode: bool = False):
        if test_mode:
            self.sql_db_connection = sqlite3.connect(":memory:")
        else:
            cache_db_path = os.environ.get("CACHE_DB_PATH")
            if cache_db_path is not None:
                self.sql_db_connection = sqlite3.connect(cache_db_path + "/event_cache.db")
            else:
                self.sql_db_connection = sqlite3.connect("../event_cache.db")

        self.ue_driver = UploadedEventsDriver(self.sql_db_connection)
        self.es_driver = EventSourceDriver(self.sql_db_connection)
        self.com_driver = CombineDBDriver()

    def close(self):
        self.sql_db_connection.close()

    def delete_all_month_old_events(self):
        self.ue_driver.delete_all_month_old_events(self.sql_db_connection)

    def select_all_rows_with_calendar_id(self, source) -> Cursor:
        return self.com_driver.select_all_rows_with_calendar_id(self.sql_db_connection, source)
    
    def get_last_event_date_for_source_id(self, calendar_id) -> datetime:
        return self.com_driver.get_last_event_date_for_source_id(self.sql_db_connection, calendar_id)
    
    def no_entries_with_source_id(self, calendar_id: str) -> bool:
        res = self.select_all_rows_with_calendar_id(calendar_id)
        return len(res.fetchall()) == 0
    
    def entry_already_in_cache(self, date:str, title:str, source_id:str) -> bool:
        return self.com_driver.entry_already_in_cache(self.sql_db_connection, date, title, source_id)

    def insert_uploaded_event(self, row_to_add: UploadedEventRow, event_source: EventSource):
        primary_key = self.ue_driver.insert_uploaded_event(self.sql_db_connection, row_to_add)
        self.es_driver.insert_uploaded_event(self.sql_db_connection, primary_key, event_source)
    
    def select_all_from_upload_table(self) -> sqlite3.Cursor:
        return self.ue_driver.select_all_from_upload_table(self.sql_db_connection)

    def select_all_from_event_source_table(self) -> sqlite3.Cursor:
        return self.es_driver.select_all_from_event_source_table(self.sql_db_connection)
    
        
        
    