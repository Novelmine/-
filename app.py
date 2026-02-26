import os
from datetime import datetime
from pathlib import Path
from threading import Thread

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from db import init_db
from guild_api import GuildAPIError, fetch_guild_members
from storage import Storage, StorageError
from utils_dates import compute_previous_week_thursday_key
from ocr_utils import (
    compute_file_hash,
    merge_consensus,
    match_parsed_rows,
    parse_name_scores,
    preprocess_image,
    run_ocr,
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = "maple-dev-secret"
store = Storage()


def _append_ocr_log(batch_id: int, image_id: int, payload: dict):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"ocr_batch_{batch_id}.log"
    timestamp = datetime.now().isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] image_id={image_id} {payload}\n")


def _process_batch_async(batch_id: int, week_key: str, jobs: list[dict]):
    processed_count = 0
    try:
        members = [dict(r) if not isinstance(r, dict) else r for r in store.list_active_members()]
        extracted_records = []

        for job in jobs:
            image_id = job["image_id"]
            path = job["path"]
            try:
                pre = preprocess_image(path)
                raw_text, avg_conf = run_ocr(pre)
                parsed = parse_name_scores(raw_text)
            except Exception:
                parsed = []
                raw_text = ""
                avg_conf = 0.0

            matched_rows = match_parsed_rows(parsed, members)
            _append_ocr_log(
                batch_id,
                image_id,
                {
                    "ocr_conf": round(avg_conf, 2),
                    "raw_text_preview": raw_text[:400].replace("\n", " | "),
                    "parsed_count": len(parsed),
                    "matched_count": len([r for r in matched_rows if r["member_id"]]),
                    "rows": [
                        {
                            "raw_name": r["raw_name"],
                            "corrected_name": r["corrected_name"],
                            "score": r["score"],
                            "member_id": r["member_id"],
                            "similarity": round(r["similarity"], 3),
                            "strategy": r["strategy"],
                        }
                        for r in matched_rows
                    ],
                },
            )

            for row in matched_rows:
                member_id = row["member_id"]
                store.add_ocr_line(image_id, row["raw_name"], row["score"], avg_conf)
                if member_id:
                    extracted_records.append(
                        {
                            "member_id": member_id,
                            "score": row["score"],
                            "source_image_id": image_id,
                            "similarity": row["similarity"],
                        }
                    )

            processed_count += 1
            store.update_batch_progress(batch_id, processed_count, status="processing")

        merged = merge_consensus(extracted_records)
        for row in merged:
            store.add_weekly_record(week_key, row["member_id"], row["score"], row["source_image_id"], row["confirmed"])

        store.mark_batch_done(batch_id)
    except StorageError:
        store.mark_batch_failed(batch_id, processed_count)


@app.route("/")
def index():
    try:
        batches = store.list_recent_batches(limit=20)
    except StorageError as exc:
        flash(str(exc), "error")
        batches = []
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
        inserted = store.import_members(member_names)
    except (GuildAPIError, StorageError) as exc:
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
    files = [f for f in request.files.getlist("images") if f and f.filename]

    if not files:
        flash("이미지를 최소 1장 이상 업로드하세요.", "error")
        return redirect(url_for("upload"))

    try:
        batch_id = store.create_batch(week_key, len(files))
        jobs = []
        for file in files:
            target = UPLOAD_DIR / f"{batch_id}_{file.filename}"
            file.save(target)
            image_hash = compute_file_hash(str(target))
            image_id = store.create_image(batch_id, str(target), image_hash)
            jobs.append({"image_id": image_id, "path": str(target)})

        Thread(target=_process_batch_async, args=(batch_id, week_key, jobs), daemon=True).start()
    except StorageError as exc:
        flash(str(exc), "error")
        return redirect(url_for("upload"))

    return redirect(url_for("batch_progress", batch_id=batch_id))


@app.route("/batch/<int:batch_id>/progress")
def batch_progress(batch_id: int):
    batch = store.get_batch(batch_id)
    if not batch:
        flash("배치를 찾을 수 없습니다.", "error")
        return redirect(url_for("index"))
    return render_template("batch_progress.html", batch=batch)


@app.route("/batch/<int:batch_id>/status")
def batch_status(batch_id: int):
    try:
        batch = store.get_batch(batch_id)
    except StorageError as exc:
        return jsonify({"error": str(exc)}), 500

    if not batch:
        return jsonify({"error": "not found"}), 404

    uploaded = int(batch.get("uploaded_count", 0) or 0)
    processed = int(batch.get("processed_count", 0) or 0)
    status = batch.get("status", "processing")
    done = status == "done"
    failed = status == "failed"

    return jsonify(
        {
            "batch_id": batch_id,
            "status": status,
            "uploaded_count": uploaded,
            "processed_count": processed,
            "progress": 100 if uploaded == 0 else int((processed / uploaded) * 100),
            "done": done,
            "failed": failed,
            "result_url": url_for("batch_result", batch_id=batch_id),
        }
    )


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
