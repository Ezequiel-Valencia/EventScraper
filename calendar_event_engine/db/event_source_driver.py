import sqlite3


class EventSource:
    uuid: str
    websiteURL: str
    calendar_id: str
    sourceType: str

    def __init__(self, uuid:str, website_url: str, calendar_id:str, source_type: str):
        """
        Args:
            uuid(str): The publishers UUID for the event uploaded
            website_url(str): The events website of origin
            calendar_id(str): The calendar where the event was sourced from
            source_type(str): Source type
        """
        self.uuid = uuid
        self.websiteURL = website_url
        self.calendar_id = calendar_id
        self.sourceType = source_type


class EventSourceDriver:
    event_source_table_name = "event_source"

    def __init__(self, db_connection: sqlite3.Connection):
        db_cursor = db_connection.cursor()
        db_cursor.execute(f"""CREATE  TABLE IF NOT EXISTS {self.event_source_table_name}
                                  (id, uuid text, websiteURL text, calendar_id text, sourceType text, 
                                  FOREIGN KEY (id) REFERENCES uploaded_events(id) ON DELETE CASCADE)""")
        db_connection.commit()

    def select_all_from_event_source_table(self, db_connection: sqlite3.Connection) -> sqlite3.Cursor:
        db_cursor = db_connection.cursor()
        res = db_cursor.execute(f"SELECT * FROM {self.event_source_table_name}")
        return res

    def insert_uploaded_event(self, db_connection: sqlite3.Connection, foreign_key: int, event_source: EventSource):
        db_cursor: sqlite3.Cursor = db_connection.cursor()
        event_source_row = (foreign_key, event_source.uuid, event_source.websiteURL, event_source.calendar_id, event_source.sourceType)

        db_cursor.execute(f"INSERT INTO {self.event_source_table_name} VALUES (?, ?, ? , ?, ?)", event_source_row)
        db_connection.commit()


