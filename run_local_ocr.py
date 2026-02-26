import argparse
import csv
from pathlib import Path

from ocr_utils import best_member_match, extract_maple_table_rows


def load_members_csv(path: str):
    if not path:
        return []
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        idx = 1
        for row in reader:
            nickname = (row.get("nickname") or row.get("name") or "").strip()
            if not nickname:
                continue
            aliases = (row.get("aliases") or row.get("nickname_aliases") or "").strip()
            rows.append({"id": idx, "nickname": nickname, "nickname_aliases": aliases})
            idx += 1
    return rows


def load_alias_map(path: str):
    if not path:
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = (row.get("raw") or "").strip()
            canon = (row.get("canonical") or "").strip()
            if raw and canon:
                out[raw] = canon
    return out


def main():
    parser = argparse.ArgumentParser(description="Maple table OCR runner (no web UI)")
    parser.add_argument("--input-dir", default="uploads", help="이미지 폴더 경로")
    parser.add_argument("--output", default="ocr_result.csv", help="출력 CSV 파일")
    parser.add_argument("--rows", type=int, default=18, help="이미지당 최대 행 수")
    parser.add_argument("--engine", default="auto", choices=["auto", "paddle", "easyocr", "tesseract"], help="OCR 엔진")
    parser.add_argument("--table-top", type=float, default=0.16, help="테이블 시작 Y 비율")
    parser.add_argument("--table-bottom", type=float, default=0.78, help="테이블 끝 Y 비율")
    parser.add_argument("--members-csv", default="", help="닉네임 마스터 CSV(nickname,aliases)")
    parser.add_argument("--alias-csv", default="", help="보정 CSV(raw,canonical)")
    parser.add_argument("--min-confidence", type=float, default=75.0, help="검수 필요 confidence 임계치")
    parser.add_argument("--min-similarity", type=float, default=0.78, help="매칭 성공 similarity 임계치")
    args = parser.parse_args()

    if not (0 < args.table_top < args.table_bottom < 1):
        print("[ERROR] table-top/table-bottom은 0~1 사이 비율이며 top < bottom 이어야 합니다.")
        return 1

    input_dir = Path(args.input_dir)
    files = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        files.extend(sorted(input_dir.glob(ext)))

    if not files:
        print(f"[ERROR] 이미지 파일이 없습니다: {input_dir}")
        print("- uploads 폴더에 png/jpg 파일을 넣고 다시 실행하세요.")
        return 1

    members = load_members_csv(args.members_csv)
    alias_map = load_alias_map(args.alias_csv)

    all_rows = []
    for file in files:
        try:
            rows = extract_maple_table_rows(
                str(file),
                row_count=args.rows,
                engine=args.engine,
                table_top_ratio=args.table_top,
                table_bottom_ratio=args.table_bottom,
            )

            for idx, row in enumerate(rows, start=1):
                raw_nickname = row.get("nickname", "")
                corrected_nickname = alias_map.get(raw_nickname, raw_nickname)

                matched_name = ""
                similarity = 0.0
                needs_review = False

                if members and corrected_nickname:
                    matched, sim = best_member_match(corrected_nickname, members)
                    similarity = sim
                    if matched and sim >= args.min_similarity:
                        matched_name = matched["nickname"]
                    else:
                        needs_review = True

                conf = float(row.get("confidence", 0) or 0)
                if conf < args.min_confidence:
                    needs_review = True

                all_rows.append(
                    {
                        "image": file.name,
                        "row_index": idx,
                        "raw_nickname": raw_nickname,
                        "nickname": corrected_nickname,
                        "matched_name": matched_name,
                        "similarity": round(similarity, 3),
                        "job": row.get("job", ""),
                        "level": row.get("level", ""),
                        "rank": row.get("rank", ""),
                        "mission": row.get("mission", ""),
                        "sewer": row.get("score", 0),
                        "flag": row.get("flag", ""),
                        "confidence": round(conf, 2),
                        "needs_review": 1 if needs_review else 0,
                    }
                )

            review_count = sum(1 for r in all_rows if r["image"] == file.name and r["needs_review"] == 1)
            print(f"[OK] {file.name}: {len(rows)} rows, review {review_count}")
        except Exception as exc:
            print(f"[FAIL] {file.name}: {exc}")

    output = Path(args.output)
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "image",
                "row_index",
                "raw_nickname",
                "nickname",
                "matched_name",
                "similarity",
                "job",
                "level",
                "rank",
                "mission",
                "sewer",
                "flag",
                "confidence",
                "needs_review",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    total_review = sum(1 for r in all_rows if r["needs_review"] == 1)
    print(f"\n[RESULT] total rows: {len(all_rows)}")
    print(f"[RESULT] needs_review: {total_review}")
    print(f"[RESULT] csv: {output.resolve()}")
    print("[NEXT] csv 내용을 그대로 붙여주면 제가 보정(aliases/threshold/ratio)값까지 바로 제안합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
