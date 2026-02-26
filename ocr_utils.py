import hashlib
import importlib
import importlib.util
import re
from collections import defaultdict
from statistics import median
from difflib import SequenceMatcher

NAME_SCORE_RE = re.compile(r"([가-힣A-Za-z0-9._]{2,16})\s+([0-9,]{1,7})")

CONFUSION_MAP = str.maketrans(
    {
        "0": "o",
        "1": "l",
        "|": "l",
        "5": "s",
        "$": "s",
    }
)


def _optional_module(name: str):
    if importlib.util.find_spec(name) is None:
        return None
    return importlib.import_module(name)


cv2 = _optional_module("cv2")
np = _optional_module("numpy")
pytesseract = _optional_module("pytesseract")
Image = None
if importlib.util.find_spec("PIL") is not None:
    Image = importlib.import_module("PIL.Image")

paddleocr_mod = _optional_module("paddleocr")
easyocr_mod = _optional_module("easyocr")

_PADDLE_ENGINE = None
_EASY_ENGINE = None


MAPLE_TABLE_COLS = {
    "nickname": (40, 132),
    "job": (132, 222),
    "level": (222, 260),
    "rank": (260, 315),
    "mission": (315, 350),
    "sewer": (350, 438),
    "flag": (438, 510),
}


def normalize_nickname(name: str) -> str:
    compact = "".join(ch for ch in name.strip().lower() if ch.isalnum() or ("가" <= ch <= "힣"))
    return compact.translate(CONFUSION_MAP)


def compute_file_hash(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _load_image_rgb(path: str):
    if cv2 is None or Image is None or np is None:
        raise RuntimeError("OCR dependencies are not installed. Install requirements.txt first.")
    return np.array(Image.open(path).convert("RGB"))


def preprocess_image(path: str):
    image = _load_image_rgb(path)
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


def _get_paddle_engine():
    global _PADDLE_ENGINE
    if paddleocr_mod is None:
        return None
    if _PADDLE_ENGINE is None:
        _PADDLE_ENGINE = paddleocr_mod.PaddleOCR(use_angle_cls=True, lang="korean", show_log=False)
    return _PADDLE_ENGINE


def _get_easy_engine():
    global _EASY_ENGINE
    if easyocr_mod is None:
        return None
    if _EASY_ENGINE is None:
        _EASY_ENGINE = easyocr_mod.Reader(["ko", "en"], gpu=False)
    return _EASY_ENGINE


def _ocr_with_pytesseract(image, numeric: bool = False):
    if pytesseract is None:
        return None, 0.0
    config = "--psm 7"
    if numeric:
        config += " -c tessedit_char_whitelist=0123456789,"
    data = pytesseract.image_to_data(
        image,
        lang="kor+eng",
        output_type=pytesseract.Output.DICT,
        config=config,
    )
    words = []
    for i, word in enumerate(data["text"]):
        cleaned = word.strip()
        if not cleaned:
            continue
        conf_raw = data["conf"][i]
        conf = float(conf_raw) if str(conf_raw).replace(".", "", 1).isdigit() else 0.0
        words.append((cleaned, conf))
    if not words:
        return "", 0.0
    text = " ".join(w for w, _ in words)
    avg_conf = sum(c for _, c in words) / len(words)
    return text, avg_conf


def _ocr_with_paddle(image):
    engine = _get_paddle_engine()
    if engine is None:
        return None, 0.0
    result = engine.ocr(image, cls=True)
    lines = []
    scores = []
    for block in result:
        if not block:
            continue
        for item in block:
            text = item[1][0].strip()
            score = float(item[1][1]) * 100
            if text:
                lines.append(text)
                scores.append(score)
    if not lines:
        return "", 0.0
    return " ".join(lines), sum(scores) / len(scores)


def _ocr_with_easyocr(image):
    engine = _get_easy_engine()
    if engine is None:
        return None, 0.0
    result = engine.readtext(image)
    texts = [r[1].strip() for r in result if r[1].strip()]
    scores = [float(r[2]) * 100 for r in result if r[1].strip()]
    if not texts:
        return "", 0.0
    return " ".join(texts), sum(scores) / len(scores)


def ocr_text(image, engine: str = "auto", numeric: bool = False):
    if engine in ("auto", "paddle"):
        txt, conf = _ocr_with_paddle(image)
        if txt is not None:
            return txt, conf
    if engine in ("auto", "easyocr"):
        txt, conf = _ocr_with_easyocr(image)
        if txt is not None:
            return txt, conf
    txt, conf = _ocr_with_pytesseract(image, numeric=numeric)
    if txt is None:
        raise RuntimeError("No OCR engine available. Install pytesseract or paddleocr/easyocr.")
    return txt, conf


def parse_int(value: str) -> int:
    cleaned = re.sub(r"[^0-9]", "", value)
    return int(cleaned) if cleaned else 0


def extract_maple_table_rows(
    path: str,
    row_count: int = 17,
    engine: str = "auto",
    table_top_ratio: float = 0.16,
    table_bottom_ratio: float = 0.78,
):
    image = _load_image_rgb(path)
    h, w, _ = image.shape

    table_top = int(h * table_top_ratio)
    table_bottom = int(h * table_bottom_ratio)
    row_height = max(1, int((table_bottom - table_top) / row_count))
    rows = []

    for idx in range(row_count):
        y1 = table_top + idx * row_height
        y2 = y1 + row_height
        if y2 > h:
            break

        row_data = {}
        total_conf = 0.0
        hit = 0

        for key, (x1_base, x2_base) in MAPLE_TABLE_COLS.items():
            x1 = int(x1_base / 540 * w)
            x2 = int(x2_base / 540 * w)
            cell = image[y1:y2, x1:x2]
            if cell.size == 0:
                row_data[key] = ""
                continue

            gray = cv2.cvtColor(cell, cv2.COLOR_RGB2GRAY)
            gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            txt, conf = ocr_text(bw, engine=engine, numeric=key in {"level", "mission", "sewer", "flag"})
            row_data[key] = txt.replace(" ", "")
            if txt:
                total_conf += conf
                hit += 1

        if row_data.get("nickname"):
            row_data["confidence"] = round(total_conf / max(1, hit), 2)
            row_data["score"] = parse_int(row_data.get("sewer", "0"))
            row_data["mission"] = parse_int(row_data.get("mission", "0"))
            row_data["flag"] = parse_int(row_data.get("flag", "0"))
            rows.append(row_data)

    return rows


def run_ocr(preprocessed):
    return ocr_text(preprocessed, engine="auto")


def parse_name_scores(text: str):
    normalized = text.replace("O", "0").replace("I", "1")
    results = []
    for name, score in NAME_SCORE_RE.findall(normalized):
        value = parse_int(score)
        if 0 <= value <= 99999:
            results.append({"name": name, "score": value})
    return results


def best_member_match(raw_name: str, members: list[dict]):
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
