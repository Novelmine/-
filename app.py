import os
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

from db import init_db
from guild_api import GuildAPIError, fetch_guild_members
from storage import Storage, StorageError
from utils_dates import compute_previous_week_thursday_key
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
store = Storage()


@app.route("/")
def index():
    batches = store.list_recent_batches(limit=20)
    return render_template("index.html", batches=batches)


@app.route("/members", methods=["GET", "POST"])
def members():
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        rank = request.form.get("rank", "길드원").strip() or "길드원"
        aliases = request.form.get("nickname_aliases", "").strip()
        if nickname:
            try:
                store.add_member(nickname, rank, aliases)
                flash(f"길드원 '{nickname}' 추가 완료", "success")
            except StorageError as exc:
                flash(str(exc), "error")
        return redirect(url_for("members"))

    rows = store.list_members()
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

    try:
        inserted = store.import_members(member_names)
    except StorageError as exc:
        flash(str(exc), "error")
        return redirect(url_for("members"))

    flash(f"길드원 동기화 완료: 전체 {len(member_names)}명 / 신규 {inserted}명", "success")
    return redirect(url_for("members"))


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    input_date = request.form.get("input_date", "").strip() or None
    week_key = compute_previous_week_thursday_key(input_date)
    files = request.files.getlist("images")

    files = [f for f in files if f and f.filename]
    if not files:
        flash("이미지를 최소 1장 이상 업로드하세요.", "error")
        return redirect(url_for("upload"))

    try:
        members = [dict(r) if not isinstance(r, dict) else r for r in store.list_active_members()]
        batch_id = store.create_batch(week_key, len(files))

        extracted_records = []

        for file in files:
            target = UPLOAD_DIR / f"{batch_id}_{file.filename}"
            file.save(target)

            image_hash = compute_file_hash(str(target))
            image_id = store.create_image(batch_id, str(target), image_hash)

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
                store.add_ocr_line(image_id, item["name"], item["score"], avg_conf)
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
            store.add_weekly_record(week_key, row["member_id"], row["score"], row["source_image_id"], row["confirmed"])

        store.mark_batch_done(batch_id)
    except StorageError as exc:
        flash(str(exc), "error")
        return redirect(url_for("upload"))

    flash(f"배치 처리 완료: {len(files)}장 업로드 (주차키: {week_key})", "success")
    return redirect(url_for("batch_result", batch_id=batch_id))


@app.route("/batch/<int:batch_id>")
def batch_result(batch_id: int):
    try:
        batch = store.get_batch(batch_id)
        images = store.get_images(batch_id)
        rows = store.get_weekly_rows(batch["week_key"]) if batch else []
    except StorageError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))
    return render_template("batch.html", batch=batch, images=images, rows=rows)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=True)
