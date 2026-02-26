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
