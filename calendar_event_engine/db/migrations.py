import sqlite3


def add_missing_columns(
    db_connection: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    """
    Add each of `columns` ({name: type}) that `table` doesn't have yet, so a cache
    created by an older version keeps working. New columns go at the end, leaving
    the position of the existing ones unchanged. Does not commit.
    """
    existing = {row[1] for row in db_connection.execute(f"PRAGMA table_info({table})")}
    for name, column_type in columns.items():
        if name not in existing:
            db_connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")
