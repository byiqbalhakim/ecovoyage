import sqlite3
from pathlib import Path

from ..config import BASE_DIR

# Single-file SQLite database, lives at data/database/ecovoyage.db
DB_PATH = BASE_DIR / 'data' / 'database' / 'ecovoyage.db'


def get_connection(db_path=DB_PATH) -> sqlite3.Connection:
    """
    Open a connection to the SQLite database file, creating the parent
    folder if needed. `db_path.parent.mkdir` avoids a confusing
    'unable to open database file' error the first time this runs.

    sqlite3.Row lets query results come back as dict-like rows
    (row['fuel_t'] instead of row[2]) — much easier to work with
    than plain tuples once you're not staring at the schema.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # SQLite has foreign keys support but ships with it OFF by default
    # for backwards-compatibility reasons. We turn it on per-connection
    # so that e.g. deleting a route also fails loudly (or cascades, see
    # schema.py) instead of silently leaving orphaned rows in route_legs.
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db(db_path=DB_PATH):
    """Create all tables if they don't already exist. Safe to call every
    time the app starts — CREATE TABLE IF NOT EXISTS is a no-op if the
    schema is already there."""
    from .schema import ALL_SCHEMAS
    conn = get_connection(db_path)
    try:
        with conn:  # `with conn` auto-commits on success, rolls back on exception
            for ddl in ALL_SCHEMAS:
                conn.execute(ddl)
    finally:
        conn.close()