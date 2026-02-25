import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL 환경변수가 필요합니다. (Supabase Postgres 연결 문자열)")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS members (
                    id BIGSERIAL PRIMARY KEY,
                    nickname TEXT UNIQUE NOT NULL,
                    rank TEXT NOT NULL DEFAULT '길드원',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    nickname_aliases TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS weekly_batches (
                    id BIGSERIAL PRIMARY KEY,
                    week_key TEXT NOT NULL,
                    uploaded_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'processing',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS images (
                    id BIGSERIAL PRIMARY KEY,
                    batch_id BIGINT NOT NULL REFERENCES weekly_batches(id),
                    file_path TEXT NOT NULL,
                    image_hash TEXT,
                    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS ocr_lines (
                    id BIGSERIAL PRIMARY KEY,
                    image_id BIGINT NOT NULL REFERENCES images(id),
                    raw_name TEXT,
                    raw_score INTEGER,
                    confidence REAL
                );

                CREATE TABLE IF NOT EXISTS weekly_records (
                    id BIGSERIAL PRIMARY KEY,
                    week_key TEXT NOT NULL,
                    member_id BIGINT NOT NULL REFERENCES members(id),
                    score INTEGER NOT NULL,
                    source_image_id BIGINT REFERENCES images(id),
                    confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()
