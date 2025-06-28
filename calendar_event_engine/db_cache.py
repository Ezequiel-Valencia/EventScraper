import os
import sqlite3
from datetime import datetime

from calendar_event_engine.logger import create_logger_from_designated_logger

logger = create_logger_from_designated_logger(__name__)

class UploadedEventRow:
    uuid: str
    id: str
    title: str
    date: str
    groupID: str
    groupName: str
    
    def __init__(self, uuid: str, id: str, title: str, date: str, group_id: str, group_name: str):
        """_summary_

        Args:
            uuid (str): _description_
            id (str): _description_
            title (str): _description_
            date (str): Has to be of format ISO8601 that is YYYY-MM-DD HH:MM:SS.SSS. Can also have T in the center if desired.
            group_id (str): _description_
        """
        
        self.uuid = uuid
        self.id = id
        self.title = title
        self.date = date
        self.groupID = group_id
        self.groupName = group_name

class UploadSource:
    uuid: str
    websiteURL: str
    source: str
    sourceType: str
    
    def __init__(self, uuid:str, website_url: str, source:str, source_type: str):
        self.uuid = uuid
        self.websiteURL = website_url
        self.source = source
        self.sourceType = source_type



class SQLiteDB:
    sql_db_connection: sqlite3.Connection
    uploaded_events_table_name = "uploaded_events"
    event_source_table_name = "event_source"
    
    allColumns = f"""{uploaded_events_table_name}.uuid, {uploaded_events_table_name}.id,
    {uploaded_events_table_name}.title, {uploaded_events_table_name}.date, 
    {uploaded_events_table_name}.group_id, {uploaded_events_table_name}.group_name,
    {event_source_table_name}.websiteURL, {event_source_table_name}.source, {event_source_table_name}.sourceType"""
    
    def __init__(self, in_memory_sq_lite: bool = False):
        if in_memory_sq_lite:
            self.sql_db_connection = sqlite3.connect(":memory:")
        else:
            cache_db_path = os.environ.get("CACHE_DB_PATH")
            if cache_db_path is not None:
                self.sql_db_connection = sqlite3.connect(cache_db_path + "/event_cache.db")
            else:
                self.sql_db_connection = sqlite3.connect("event_cache.db")
        self.initialize_db()
    
    def initialize_db(self) -> sqlite3.Connection:
        db_cursor = self.sql_db_connection.cursor()
        db_cursor.execute(f"""CREATE TABLE IF NOT EXISTS {self.uploaded_events_table_name} 
                          (uuid PRIMARY KEY, id, title text, date text, group_id, group_name)""")
        db_cursor.execute(f"""CREATE  TABLE IF NOT EXISTS {self.event_source_table_name}
                          (uuid, websiteURL text, source text, sourceType text, 
                          FOREIGN KEY (uuid) REFERENCES uploaded_events(uuid) ON DELETE CASCADE)""" )

    def close(self):
        self.sql_db_connection.close()

    # https://www.sqlite.org/lang_datefunc.html
    # Uses built in date time function
    def delete_all_month_old_events(self):
        db_cursor = self.sql_db_connection.cursor()
        db_cursor.execute(f"DELETE FROM {self.uploaded_events_table_name} WHERE datetime(date) < datetime('now', '-1 month')")
        
        self.sql_db_connection.commit()

    def select_all_rows_with_calendar_id(self, source):
        db_cursor = self.sql_db_connection.cursor()
        # Comma at the end of (groupID,) turns it into a tuple
        res = db_cursor.execute(f"""SELECT {self.allColumns} FROM {self.uploaded_events_table_name} 
                                INNER JOIN {self.event_source_table_name} ON 
                                {self.uploaded_events_table_name}.uuid={self.event_source_table_name}.uuid
                                WHERE source = ?""", (source,))
        return res
    
    def get_last_event_date_for_source_id(self, calendar_id) -> datetime:
        db_cursor = self.sql_db_connection.cursor()
        res = db_cursor.execute(f"""SELECT date FROM {self.uploaded_events_table_name}
                                INNER JOIN {self.event_source_table_name} ON 
                                {self.uploaded_events_table_name}.uuid={self.event_source_table_name}.uuid
                                WHERE source = ?
                                ORDER BY date DESC LIMIT 1""", (calendar_id,))
        # Conversion to ISO format does not like the Z, that represents UTC aka no time zone
        # so using +00:00 is an equivalent to it
        date_string = res.fetchone()[0]
        logger.debug(f"Last date found for calendar ID {calendar_id}: {date_string}")
        return datetime.fromisoformat(date_string)
    
    def no_entries_with_source_id(self, calendar_id: str) -> bool:
        res = self.select_all_rows_with_calendar_id(calendar_id)
        return len(res.fetchall()) == 0
    
    def entry_already_in_cache(self, date:str, title:str, source_id:str) -> bool:
        db_cursor = self.sql_db_connection.cursor()
        res = db_cursor.execute(f"""SELECT {self.allColumns} FROM {self.uploaded_events_table_name}
                                INNER JOIN {self.event_source_table_name} ON 
                                {self.uploaded_events_table_name}.uuid={self.event_source_table_name}.uuid
                                WHERE date = ? AND title = ? AND source = ?""", (date, title, source_id))
        query = res.fetchall()
        if len(query) > 0:
            return True
        return False

    def insert_uploaded_event(self, row_to_add: UploadedEventRow, event_source: UploadSource):
        db_cursor: sqlite3.Cursor = self.sql_db_connection.cursor()
        insert_row = (row_to_add.uuid, row_to_add.id, row_to_add.title, row_to_add.date, row_to_add.groupID, row_to_add.groupName)
        event_source_row= (event_source.uuid, event_source.websiteURL, event_source.source, event_source.sourceType)
        
        db_cursor.execute(f"INSERT INTO {self.uploaded_events_table_name} VALUES (?, ?, ?, ? , ?, ?)", insert_row)
        db_cursor.execute(f"INSERT INTO {self.event_source_table_name} VALUES (?, ? , ?, ?)", event_source_row)
        self.sql_db_connection.commit()
    
    def select_all_from_upload_table(self) -> sqlite3.Cursor:
        db_cursor = self.sql_db_connection.cursor()
        res = db_cursor.execute(f"SELECT * FROM {self.uploaded_events_table_name}")
        return res

    def select_all_from_event_source_table(self) -> sqlite3.Cursor:
        db_cursor = self.sql_db_connection.cursor()
        res = db_cursor.execute(f"SELECT * FROM {self.event_source_table_name}")
        return res
    
        
        
    