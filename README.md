# Maple Guild OCR MVP

메이플 길드 주간 점수 스크린샷(다중 업로드, 주 10장 기준)을 업로드해서 OCR로 이름/점수를 추출하고,
길드원 매칭 + 합의(중앙값)로 주간 점수를 저장하는 최소 구현입니다.

## 기능
- 길드원 등록(별칭/오타 사전 포함)
- 넥슨 Open API로 길드원 목록 동기화(서버/길드명 기준)
- 주차별 다중 이미지 업로드
- OCR 전처리(CLAHE + adaptive threshold + sharpen)
- OCR 결과 파싱(이름/점수)
- 길드원 유사도 매칭
- 다중 이미지 합의 점수(중앙값)
- 배치 결과 확인

## 실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

브라우저: `http://localhost:8000`

## 필수
- 시스템에 `tesseract` 실행파일과 한글 데이터(`kor`)가 설치되어 있어야 OCR이 동작합니다.

## 테스트
```bash
python -m unittest -v
```


## 길드원 목록 가져오기(권장)
- `/members` 페이지에서 API Key, 서버명(엘리시움), 길드명(설아)을 입력하면 자동 동기화됩니다.
- Nexon Open API Key가 필요하며, 요청 헤더 `x-nxopen-api-key`로 호출합니다.
- API 직접 확인 시 308 Redirect가 나오면 URL 끝 슬래시(`/`)가 필요한 경우입니다. `curl -L`을 사용하거나 `/guild/id/`, `/guild/basic/` 경로를 사용하세요.


## OCR 엔진 우선순위(정확도 개선)
현재 코드의 OCR 엔진 선택 순서는 다음과 같습니다.
1. PaddleOCR (권장, 한국어 UI 표 데이터 정확도 우수)
2. EasyOCR
3. pytesseract (fallback)

`ocr_utils.py`는 고정 UI 표(닉네임/직업/레벨/직위/주간미션/지하수로/플래그레이스) 기준으로 셀 단위 OCR을 먼저 시도하고,
실패 시 기존 전체 문장 파싱 방식으로 자동 폴백합니다.

권장 설치(로컬):
```bash
pip install paddleocr paddlepaddle
```


## 바로 실행(웹 없이, 이미지만 넣고 CSV 추출)
1) `uploads/` 폴더에 스크린샷들을 넣습니다.
2) 아래 명령 실행:

```bash
python run_local_ocr.py --input-dir uploads --output ocr_result.csv --engine auto
```

3) 생성된 `ocr_result.csv` 내용을 그대로 붙여주면, 제가 매핑/검수 결과를 이어서 정리할 수 있습니다.


### 빠른 보정 반복(추천)
이미지 결과를 계속 붙여주면 보정하기 쉽게 아래 파일/옵션을 추가했습니다.

- `--table-top`, `--table-bottom`: 표 시작/끝 비율 튜닝
- `--members-csv`: 길드원 마스터 매칭
- `--alias-csv`: OCR 오타 교정 사전(`raw,canonical`)
- `--min-confidence`, `--min-similarity`: 검수 대상 판정 기준

실행 예시:
```bash
python run_local_ocr.py   --input-dir uploads   --output ocr_result.csv   --engine auto   --table-top 0.16 --table-bottom 0.79   --members-csv members_master.csv   --alias-csv alias_map.csv   --min-confidence 78 --min-similarity 0.80
```
