import hashlib
import re
from collections import defaultdict
from difflib import SequenceMatcher
from statistics import median

try:
    import cv2
    import numpy as np
    import pytesseract
    from PIL import Image
except ModuleNotFoundError:
    cv2 = None
    np = None
    pytesseract = None
    Image = None

NAME_RE = re.compile(r"[가-힣A-Za-z0-9._-]{2,12}")
SCORE_TOKEN_RE = re.compile(r"[0-9OIl|S$BZDQ,.'`]{1,8}")
NAME_SCORE_RE = re.compile(r"\b([가-힣A-Za-z0-9._-]{2,12})\b\s*[:|/\\-]\s*([0-9OIl|S$BZDQ,.'`]{1,12})")

CONFUSION_MAP = str.maketrans({
    "0": "o",
    "1": "l",
    "|": "l",
    "5": "s",
    "$": "s",
})

SCORE_FIX_MAP = str.maketrans({
    "O": "0",
    "o": "0",
    "D": "0",
    "Q": "0",
    "I": "1",
    "l": "1",
    "|": "1",
    "S": "5",
    "s": "5",
    "$": "5",
    "B": "8",
    "Z": "2",
    "'": "",
    "`": "",
    ".": "",
    ",": "",
})

MAX_SCORE = 9_999_999


def normalize_nickname(name: str) -> str:
    compact = "".join(ch for ch in name.strip().lower() if ch.isalnum() or ("가" <= ch <= "힣"))
    return compact.translate(CONFUSION_MAP)


def compute_file_hash(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def preprocess_image(path: str):
    if cv2 is None or Image is None or np is None:
        raise RuntimeError("OCR dependencies are not installed. Install requirements.txt first.")

    image = np.array(Image.open(path).convert("RGB"))
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    denoised = cv2.bilateralFilter(gray, 7, 50, 50)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    scaled = cv2.resize(enhanced, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, otsu = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = np.ones((2, 2), np.uint8)
    cleaned = cv2.morphologyEx(otsu, cv2.MORPH_OPEN, kernel)
    return cleaned


def _ocr_with_config(image, config: str):
    data = pytesseract.image_to_data(
        image,
        lang="kor+eng",
        output_type=pytesseract.Output.DICT,
        config=config,
    )

    lines = defaultdict(list)
    conf_values = []

    for i, word in enumerate(data["text"]):
        cleaned = (word or "").strip()
        if not cleaned:
            continue

        conf_raw = data["conf"][i]
        try:
            conf = float(conf_raw)
        except ValueError:
            conf = -1.0

        if conf >= 25:
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines[key].append(cleaned)
            conf_values.append(conf)

    if not lines:
        text = pytesseract.image_to_string(image, lang="kor+eng", config=config)
        return text, 0.0

    ordered = [" ".join(lines[k]) for k in sorted(lines.keys())]
    avg_conf = sum(conf_values) / max(1, len(conf_values))
    return "\n".join(ordered), avg_conf


def run_ocr(preprocessed):
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed. Install requirements.txt first.")

    variants = [preprocessed]
    if np is not None:
        variants.append(cv2.bitwise_not(preprocessed))

    configs = ["--psm 6", "--psm 11", "--psm 4"]
    best_text = ""
    best_conf = -1.0

    for image in variants:
        for cfg in configs:
            text, conf = _ocr_with_config(image, cfg)
            if conf > best_conf and text.strip():
                best_text = text
                best_conf = conf

    return best_text, max(0.0, best_conf)


def _score_to_int(raw: str):
    token = raw.translate(SCORE_FIX_MAP)
    digits = "".join(ch for ch in token if ch.isdigit())
    if not digits:
        return None
    value = int(digits)
    if 0 <= value <= MAX_SCORE:
        return value
    return None


def parse_name_scores(text: str):
    results = []
    seen = set()

    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue

        tokens = [token for token in line.split(" ") if token]
        if len(tokens) >= 2 and NAME_RE.fullmatch(tokens[0]):
            score_candidates = []
            for token in tokens[1:]:
                for piece in SCORE_TOKEN_RE.findall(token):
                    score = _score_to_int(piece)
                    if score is not None:
                        score_candidates.append(score)

            if score_candidates:
                key = (tokens[0], max(score_candidates))
                if key not in seen:
                    seen.add(key)
                    results.append({"name": key[0], "score": key[1]})
                continue

        matched = False
        for name, score_token in NAME_SCORE_RE.findall(line):
            score = _score_to_int(score_token)
            if score is None:
                continue
            key = (name, score)
            if key not in seen:
                seen.add(key)
                results.append({"name": name, "score": score})
                matched = True

        if matched:
            continue

    return results


def best_member_match(raw_name: str, members: list[dict]):
    indexed_member = None
    if raw_name:
        lookup = normalize_nickname(raw_name)
        if lookup:
            indexed_member = build_member_name_index(members).get(lookup)
    if indexed_member:
        return indexed_member, 1.0

    best = None
    best_ratio = 0.0
    for member in members:
        aliases = [member["nickname"]] + [a.strip() for a in member.get("nickname_aliases", "").split(",") if a.strip()]
        for alias in aliases:
            ratio = SequenceMatcher(None, normalize_nickname(raw_name), normalize_nickname(alias)).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best = member
    if not best or best_ratio < 0.65:
        return None, best_ratio
    return best, best_ratio


def build_member_name_index(members: list[dict]):
    index = {}
    for member in members:
        aliases = [member["nickname"]] + [a.strip() for a in member.get("nickname_aliases", "").split(",") if a.strip()]
        for alias in aliases:
            normalized = normalize_nickname(alias)
            if normalized and normalized not in index:
                index[normalized] = member
    return index


def match_parsed_rows(parsed_rows: list[dict], members: list[dict]):
    """Match parsed OCR rows to known members and return detailed diagnostics."""
    if not parsed_rows:
        return []

    index = build_member_name_index(members)
    matched = []
    for item in parsed_rows:
        raw_name = item.get("name", "")
        normalized = normalize_nickname(raw_name)

        strategy = "fuzzy"
        member = index.get(normalized)
        similarity = 1.0 if member else 0.0
        if member is None:
            member, similarity = best_member_match(raw_name, members)
        else:
            strategy = "dictionary"

        matched.append(
            {
                "raw_name": raw_name,
                "score": item["score"],
                "member": member,
                "member_id": member["id"] if member else None,
                "corrected_name": member["nickname"] if member else raw_name,
                "similarity": similarity,
                "strategy": strategy if member else "unmatched",
            }
        )
    return matched


def merge_consensus(records: list[dict]):
    grouped = defaultdict(list)
    for r in records:
        grouped[r["member_id"]].append(r)

    merged = []
    for member_id, rows in grouped.items():
        scores = [r["score"] for r in rows]
        merged.append(
            {
                "member_id": member_id,
                "score": int(median(scores)),
                "source_image_id": rows[0]["source_image_id"],
                "confirmed": 1 if len(set(scores)) == 1 else 0,
            }
        )
    return merged
