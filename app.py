import os
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

from db import get_conn, init_db
from guild_api import GuildAPIError, fetch_guild_members
from ocr_utils import (
    best_member_match,
    compute_file_hash,
    merge_consensus,
    parse_name_scores,
    preprocess_image,
    run_ocr,
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = "maple-dev-secret"


@app.route("/")
def index():
    with get_conn() as conn:
        batches = conn.execute(
            "SELECT id, week_key, uploaded_count, status, created_at FROM weekly_batches ORDER BY id DESC LIMIT 20"
        ).fetchall()
    return render_template("index.html", batches=batches)


@app.route("/members", methods=["GET", "POST"])
def members():
    with get_conn() as conn:
        if request.method == "POST":
            nickname = request.form.get("nickname", "").strip()
            rank = request.form.get("rank", "길드원").strip() or "길드원"
            aliases = request.form.get("nickname_aliases", "").strip()
            if nickname:
                conn.execute(
                    "INSERT OR IGNORE INTO members (nickname, rank, nickname_aliases) VALUES (?, ?, ?)",
                    (nickname, rank, aliases),
                )
                conn.commit()
                flash(f"길드원 '{nickname}' 추가 완료", "success")
            return redirect(url_for("members"))

        rows = conn.execute("SELECT * FROM members ORDER BY nickname").fetchall()
    return render_template("members.html", members=rows)




@app.route("/members/import-guild", methods=["POST"])
def import_guild_members():
    api_key = request.form.get("api_key", "").strip()
    world_name = request.form.get("world_name", "").strip()
    guild_name = request.form.get("guild_name", "").strip()
    date = request.form.get("date", "").strip() or None

    if not api_key or not world_name or not guild_name:
        flash("API Key / 서버 / 길드명을 모두 입력하세요.", "error")
        return redirect(url_for("members"))

    try:
        member_names = fetch_guild_members(api_key, world_name, guild_name, date)
    except GuildAPIError as exc:
        flash(str(exc), "error")
        return redirect(url_for("members"))

    inserted = 0
    with get_conn() as conn:
        for name in member_names:
            cur = conn.execute(
                "INSERT OR IGNORE INTO members (nickname, rank, nickname_aliases) VALUES (?, '길드원', '')",
                (name,),
            )
            inserted += 1 if cur.rowcount else 0
        conn.commit()

    flash(f"길드원 동기화 완료: 전체 {len(member_names)}명 / 신규 {inserted}명", "success")
    return redirect(url_for("members"))


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    week_key = request.form.get("week_key", "").strip()
    files = request.files.getlist("images")
    if not week_key:
        flash("주차 키(예: 2026-W08)를 입력하세요.", "error")
        return redirect(url_for("upload"))

    files = [f for f in files if f and f.filename]
    if not files:
        flash("이미지를 최소 1장 이상 업로드하세요.", "error")
        return redirect(url_for("upload"))

    with get_conn() as conn:
        members = [dict(r) for r in conn.execute("SELECT * FROM members WHERE is_active = 1").fetchall()]
        batch_cursor = conn.execute(
            "INSERT INTO weekly_batches (week_key, uploaded_count, status) VALUES (?, ?, 'processing')",
            (week_key, len(files)),
        )
        batch_id = batch_cursor.lastrowid

        extracted_records = []

        for file in files:
            target = UPLOAD_DIR / f"{batch_id}_{file.filename}"
            file.save(target)

            image_hash = compute_file_hash(str(target))
            img_cursor = conn.execute(
                "INSERT INTO images (batch_id, file_path, image_hash) VALUES (?, ?, ?)",
                (batch_id, str(target), image_hash),
            )
            image_id = img_cursor.lastrowid

            try:
                pre = preprocess_image(str(target))
                raw_text, avg_conf = run_ocr(pre)
                parsed = parse_name_scores(raw_text)
            except Exception as exc:
                flash(f"OCR 처리 실패: {file.filename} ({exc})", "error")
                parsed = []
                avg_conf = 0.0

            for item in parsed:
                member, similarity = best_member_match(item["name"], members)
                member_id = member["id"] if member else None
                conn.execute(
                    "INSERT INTO ocr_lines (image_id, raw_name, raw_score, confidence) VALUES (?, ?, ?, ?)",
                    (image_id, item["name"], item["score"], avg_conf),
                )
                if member_id:
                    extracted_records.append(
                        {
                            "member_id": member_id,
                            "score": item["score"],
                            "source_image_id": image_id,
                            "similarity": similarity,
                        }
                    )

        merged = merge_consensus(extracted_records)
        for row in merged:
            conn.execute(
                "INSERT INTO weekly_records (week_key, member_id, score, source_image_id, confirmed) VALUES (?, ?, ?, ?, ?)",
                (week_key, row["member_id"], row["score"], row["source_image_id"], row["confirmed"]),
            )

        conn.execute("UPDATE weekly_batches SET status='done' WHERE id=?", (batch_id,))
        conn.commit()

    flash(f"배치 처리 완료: {len(files)}장 업로드", "success")
    return redirect(url_for("batch_result", batch_id=batch_id))


@app.route("/batch/<int:batch_id>")
def batch_result(batch_id: int):
    with get_conn() as conn:
        batch = conn.execute("SELECT * FROM weekly_batches WHERE id=?", (batch_id,)).fetchone()
        images = conn.execute("SELECT * FROM images WHERE batch_id=?", (batch_id,)).fetchall()
        rows = conn.execute(
            """
            SELECT wr.week_key, wr.score, wr.confirmed, m.nickname
            FROM weekly_records wr
            JOIN members m ON m.id = wr.member_id
            WHERE wr.week_key = ?
            ORDER BY wr.score DESC
            """,
            (batch["week_key"],),
        ).fetchall()
    return render_template("batch.html", batch=batch, images=images, rows=rows)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=True)
