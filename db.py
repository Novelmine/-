import sqlite3
from contextlib import closing

DB_PATH = "maple_guild.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_conn()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT UNIQUE NOT NULL,
                rank TEXT NOT NULL DEFAULT '길드원',
                is_active INTEGER NOT NULL DEFAULT 1,
                nickname_aliases TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS weekly_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_key TEXT NOT NULL,
                uploaded_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'processing',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                image_hash TEXT,
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(batch_id) REFERENCES weekly_batches(id)
            );

            CREATE TABLE IF NOT EXISTS ocr_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER NOT NULL,
                raw_name TEXT,
                raw_score INTEGER,
                confidence REAL,
                FOREIGN KEY(image_id) REFERENCES images(id)
            );

            CREATE TABLE IF NOT EXISTS weekly_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_key TEXT NOT NULL,
                member_id INTEGER NOT NULL,
                score INTEGER NOT NULL,
                source_image_id INTEGER,
                confirmed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(member_id) REFERENCES members(id),
                FOREIGN KEY(source_image_id) REFERENCES images(id)
            );
            """
        )
        conn.commit()
