import os
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row


def _inject_ipv4_hostaddr(database_url: str) -> str:
    """
    Force IPv4 for environments where IPv6 egress is unavailable.
    Adds hostaddr=<ipv4> to conninfo if hostname resolves.
    """
    parsed = urlparse(database_url)
    if not parsed.hostname:
        return database_url

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "hostaddr" in query:
        return database_url

    try:
        ipv4 = socket.getaddrinfo(parsed.hostname, None, socket.AF_INET)[0][4][0]
    except Exception:
        return database_url

    query["hostaddr"] = ipv4
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


def get_conn():
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL 환경변수가 필요합니다. (Supabase Postgres 연결 문자열)")

    conninfo = _inject_ipv4_hostaddr(database_url)
    return psycopg.connect(conninfo, row_factory=dict_row)


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
