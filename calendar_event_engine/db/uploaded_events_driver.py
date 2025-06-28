import sqlite3

class UploadedEventRow:
    uuid: str
    user_id: str
    title: str
    date: str
    groupID: int
    groupName: str

    def __init__(self, uuid: str, user_id: str, title: str, date: str, group_id: int, group_name: str):
        """_summary_

        Args:
            uuid (str): The publishers UUID for the event uploaded
            user_id (str): The publishers id of the user who uploaded this event
            title (str): Title of the event
            date (str): Has to be of format ISO8601 that is YYYY-MM-DD HH:MM:SS.SSS. Can also have T in the center if desired.
            group_id (int): The publishers UUID for the group affiliated with this event
            group_name (str): Name of the group affiliated with this event
        """

        self.uuid = uuid
        self.user_id = user_id
        self.title = title
        self.date = date
        self.groupID = group_id
        self.groupName = group_name

class UploadedEventsDriver:
    uploaded_events_table_name = "uploaded_events"


    def __init__(self, db_connection: sqlite3.Connection):
        db_cursor = db_connection.cursor()
        db_cursor.execute(f"""CREATE TABLE IF NOT EXISTS {self.uploaded_events_table_name} 
                                  (id INTEGER PRIMARY KEY, uuid text, user_id text, 
                                  title text, date DATE, group_id integer, group_name text)""")

        # https://www.sqlite.org/lang_datefunc.html
        # Uses built in date time function
    def delete_all_month_old_events(self, db_connection: sqlite3.Connection):
        db_cursor = db_connection.cursor()
        db_cursor.execute(
            f"DELETE FROM {self.uploaded_events_table_name} WHERE datetime(date) < datetime('now', '-1 month')")
        db_connection.commit()

    def select_all_from_upload_table(self, db_connection: sqlite3.Connection) -> sqlite3.Cursor:
        db_cursor = db_connection.cursor()
        res = db_cursor.execute(f"SELECT * FROM {self.uploaded_events_table_name}")
        return res

    def insert_uploaded_event(self, db_connection: sqlite3.Connection, row_to_add: UploadedEventRow) -> int:
        """
        Returns the primary key for the row when it gets inserted.
        """
        db_cursor: sqlite3.Cursor = db_connection.cursor()
        insert_row = (row_to_add.uuid, row_to_add.user_id, row_to_add.title, row_to_add.date, row_to_add.groupID,
                      row_to_add.groupName)

        db_cursor.execute(f"INSERT INTO {self.uploaded_events_table_name} (uuid, user_id, title, date, group_id, group_name)" +
                          f"VALUES (?, ?, ?, ? , ?, ?)", insert_row)
        primary_key = db_cursor.lastrowid
        db_connection.commit()
        return primary_key



