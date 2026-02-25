import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from db import get_conn


class StorageError(RuntimeError):
    pass


class Storage:
    def __init__(self):
        self.supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.use_rest = bool(self.supabase_url and self.supabase_key)

    # ---------- Public API ----------
    def list_recent_batches(self, limit=20):
        if self.use_rest:
            return self._rest_select(
                "weekly_batches",
                select="id,week_key,uploaded_count,status,created_at",
                order="id.desc",
                limit=limit,
            )
        with get_conn() as conn:
            return conn.execute(
                "SELECT id, week_key, uploaded_count, status, created_at FROM weekly_batches ORDER BY id DESC LIMIT %s",
                (limit,),
            ).fetchall()

    def list_members(self):
        if self.use_rest:
            return self._rest_select("members", select="*", order="nickname.asc")
        with get_conn() as conn:
            return conn.execute("SELECT * FROM members ORDER BY nickname").fetchall()

    def add_member(self, nickname, rank, aliases):
        if self.use_rest:
            self._rest_insert(
                "members",
                [{"nickname": nickname, "rank": rank, "nickname_aliases": aliases}],
                on_conflict="nickname",
                ignore_duplicates=True,
            )
            return
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO members (nickname, rank, nickname_aliases) VALUES (%s, %s, %s) ON CONFLICT (nickname) DO NOTHING",
                (nickname, rank, aliases),
            )
            conn.commit()

    def import_members(self, names):
        incoming = sorted({n.strip() for n in names if n and n.strip()})

        if self.use_rest:
            existing = self._rest_select("members", select="id,nickname,is_active")
            existing_names = {m["nickname"] for m in existing}
            inserted_count = len([n for n in incoming if n not in existing_names])

            # Upsert incoming members and keep them active.
            rows = [{"nickname": n, "rank": "길드원", "nickname_aliases": "", "is_active": True} for n in incoming]
            if rows:
                self._rest_insert(
                    "members",
                    rows,
                    on_conflict="nickname",
                    ignore_duplicates=False,
                    merge_duplicates=True,
                )

            # Members missing from latest guild API list are kept but deactivated.
            to_deactivate = [m["id"] for m in existing if m["nickname"] not in set(incoming)]
            for member_id in to_deactivate:
                self._rest_patch("members", {"is_active": False}, {"id": f"eq.{member_id}"})

            return inserted_count

        inserted = 0
        with get_conn() as conn:
            existing = conn.execute("SELECT nickname FROM members").fetchall()
            existing_names = {r["nickname"] for r in existing}

            for name in incoming:
                cur = conn.execute(
                    """
                    INSERT INTO members (nickname, rank, nickname_aliases, is_active)
                    VALUES (%s, '길드원', '', TRUE)
                    ON CONFLICT (nickname) DO UPDATE SET is_active = TRUE
                    """,
                    (name,),
                )
                if name not in existing_names:
                    inserted += 1

            if incoming:
                conn.execute(
                    "UPDATE members SET is_active = FALSE WHERE nickname <> ALL(%s)",
                    (incoming,),
                )
            else:
                conn.execute("UPDATE members SET is_active = FALSE")

            conn.commit()
        return inserted

    def list_active_members(self):
        if self.use_rest:
            return self._rest_select("members", select="*", filters={"is_active": "eq.true"})
        with get_conn() as conn:
            return conn.execute("SELECT * FROM members WHERE is_active = TRUE").fetchall()

    def create_batch(self, week_key, uploaded_count):
        if self.use_rest:
            rows = self._rest_insert(
                "weekly_batches",
                [{"week_key": week_key, "uploaded_count": uploaded_count, "status": "processing"}],
            )
            return rows[0]["id"]
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO weekly_batches (week_key, uploaded_count, status) VALUES (%s, %s, 'processing') RETURNING id",
                (week_key, uploaded_count),
            )
            return cur.fetchone()["id"]

    def create_image(self, batch_id, file_path, image_hash):
        if self.use_rest:
            rows = self._rest_insert(
                "images",
                [{"batch_id": batch_id, "file_path": file_path, "image_hash": image_hash}],
            )
            return rows[0]["id"]
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO images (batch_id, file_path, image_hash) VALUES (%s, %s, %s) RETURNING id",
                (batch_id, file_path, image_hash),
            )
            return cur.fetchone()["id"]

    def add_ocr_line(self, image_id, raw_name, raw_score, confidence):
        if self.use_rest:
            self._rest_insert(
                "ocr_lines",
                [{
                    "image_id": image_id,
                    "raw_name": raw_name,
                    "raw_score": raw_score,
                    "confidence": confidence,
                }],
            )
            return
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO ocr_lines (image_id, raw_name, raw_score, confidence) VALUES (%s, %s, %s, %s)",
                (image_id, raw_name, raw_score, confidence),
            )
            conn.commit()

    def add_weekly_record(self, week_key, member_id, score, source_image_id, confirmed):
        if self.use_rest:
            self._rest_insert(
                "weekly_records",
                [{
                    "week_key": week_key,
                    "member_id": member_id,
                    "score": score,
                    "source_image_id": source_image_id,
                    "confirmed": bool(confirmed),
                }],
            )
            return
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO weekly_records (week_key, member_id, score, source_image_id, confirmed) VALUES (%s, %s, %s, %s, %s)",
                (week_key, member_id, score, source_image_id, confirmed),
            )
            conn.commit()

    def mark_batch_done(self, batch_id):
        if self.use_rest:
            self._rest_patch("weekly_batches", {"status": "done"}, {"id": f"eq.{batch_id}"})
            return
        with get_conn() as conn:
            conn.execute("UPDATE weekly_batches SET status='done' WHERE id=%s", (batch_id,))
            conn.commit()

    def get_batch(self, batch_id):
        if self.use_rest:
            rows = self._rest_select("weekly_batches", select="*", filters={"id": f"eq.{batch_id}"}, limit=1)
            return rows[0] if rows else None
        with get_conn() as conn:
            return conn.execute("SELECT * FROM weekly_batches WHERE id=%s", (batch_id,)).fetchone()

    def get_images(self, batch_id):
        if self.use_rest:
            return self._rest_select("images", select="*", filters={"batch_id": f"eq.{batch_id}"}, order="id.asc")
        with get_conn() as conn:
            return conn.execute("SELECT * FROM images WHERE batch_id=%s", (batch_id,)).fetchall()

    def get_weekly_rows(self, week_key):
        if self.use_rest:
            records = self._rest_select(
                "weekly_records",
                select="week_key,score,confirmed,member_id",
                filters={"week_key": f"eq.{week_key}"},
                order="score.desc",
            )
            member_ids = sorted({r["member_id"] for r in records})
            member_map = {}
            if member_ids:
                ids = ",".join(str(i) for i in member_ids)
                members = self._rest_select("members", select="id,nickname", filters={"id": f"in.({ids})"})
                member_map = {m["id"]: m["nickname"] for m in members}
            return [
                {
                    "week_key": r["week_key"],
                    "score": r["score"],
                    "confirmed": r.get("confirmed", False),
                    "nickname": member_map.get(r["member_id"], f"member#{r['member_id']}")
                }
                for r in records
            ]

        with get_conn() as conn:
            return conn.execute(
                """
                SELECT wr.week_key, wr.score, wr.confirmed, m.nickname
                FROM weekly_records wr
                JOIN members m ON m.id = wr.member_id
                WHERE wr.week_key = %s
                ORDER BY wr.score DESC
                """,
                (week_key,),
            ).fetchall()

    # ---------- REST helpers ----------
    def _rest_headers(self, extra=None):
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _rest_url(self, table, query=None):
        q = f"?{urlencode(query)}" if query else ""
        return f"{self.supabase_url}/rest/v1/{table}{q}"

    def _rest_request(self, method, table, query=None, body=None, headers=None):
        req = Request(
            self._rest_url(table, query),
            data=(json.dumps(body).encode("utf-8") if body is not None else None),
            headers=self._rest_headers(headers),
            method=method,
        )
        try:
            with urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else []
        except Exception as exc:
            raise StorageError(f"Supabase REST 요청 실패: {exc}") from exc

    def _rest_select(self, table, select="*", filters=None, order=None, limit=None):
        query = {"select": select}
        if filters:
            query.update(filters)
        if order:
            query["order"] = order
        if limit is not None:
            query["limit"] = str(limit)
        return self._rest_request("GET", table, query=query)

    def _rest_insert(self, table, rows, on_conflict=None, ignore_duplicates=False, merge_duplicates=False):
        query = {}
        if on_conflict:
            query["on_conflict"] = on_conflict
        prefer = "return=representation"
        if ignore_duplicates:
            prefer = "resolution=ignore-duplicates," + prefer
        if merge_duplicates:
            prefer = "resolution=merge-duplicates," + prefer
        return self._rest_request("POST", table, query=query, body=rows, headers={"Prefer": prefer})

    def _rest_patch(self, table, values, filters):
        return self._rest_request("PATCH", table, query=filters, body=values, headers={"Prefer": "return=representation"})
