import hashlib
import re
from collections import defaultdict
from statistics import median
from difflib import SequenceMatcher

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

NAME_SCORE_RE = re.compile(r"([가-힣A-Za-z0-9]{2,12})\s+([0-9]{1,5})")


CONFUSION_MAP = str.maketrans({
    "0": "o",
    "1": "l",
    "|": "l",
    "5": "s",
    "$": "s",
})


def normalize_nickname(name: str) -> str:
    compact = "".join(ch for ch in name.strip().lower() if ch.isalnum() or ('가' <= ch <= '힣'))
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
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    resized = cv2.resize(enhanced, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    thresh = cv2.adaptiveThreshold(
        resized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5,
    )
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(thresh, -1, kernel)
    return sharpened


def run_ocr(preprocessed):
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed. Install requirements.txt first.")
    data = pytesseract.image_to_data(
        preprocessed,
        lang="kor+eng",
        output_type=pytesseract.Output.DICT,
        config="--psm 6",
    )
    words = []
    for i, word in enumerate(data["text"]):
        cleaned = word.strip()
        if not cleaned:
            continue
        conf_raw = data["conf"][i]
        try:
            conf = float(conf_raw)
        except ValueError:
            conf = 0.0
        words.append({"text": cleaned, "conf": conf})

    joined = " ".join(w["text"] for w in words)
    avg_conf = sum(w["conf"] for w in words) / max(1, len(words))
    return joined, avg_conf


def parse_name_scores(text: str):
    normalized = text.replace("O", "0").replace("I", "1")
    results = []
    for name, score in NAME_SCORE_RE.findall(normalized):
        value = int(score)
        if 0 <= value <= 99999:
            results.append({"name": name, "score": value})
    return results


def best_member_match(raw_name: str, members: list[dict]):
    best = None
    best_ratio = 0.0
    candidates = []
    for member in members:
        aliases = [member["nickname"]] + [a.strip() for a in member.get("nickname_aliases", "").split(",") if a.strip()]
        for alias in aliases:
            ratio = SequenceMatcher(None, normalize_nickname(raw_name), normalize_nickname(alias)).ratio()
            candidates.append((ratio, member["id"], member["nickname"]))
            if ratio > best_ratio:
                best_ratio = ratio
                best = member
    if not best or best_ratio < 0.65:
        return None, best_ratio
    return best, best_ratio


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
