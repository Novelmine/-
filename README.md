# Maple Guild OCR MVP

메이플 길드 주간 점수 스크린샷(다중 업로드, 주 10장 기준)을 업로드해서 OCR로 이름/점수를 추출하고,
길드원 매칭 + 합의(중앙값)로 주간 점수를 저장하는 최소 구현입니다.

기본 DB는 **Supabase Postgres** 기준으로 동작합니다.

## 기능
- 길드원 등록(별칭/오타 사전 포함)
- 넥슨 Open API로 길드원 목록 동기화(서버/길드명 기준)
- 주차별 다중 이미지 업로드 (주차키 자동 계산: 입력 날짜의 전주 목요일 KST)
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
# 권장: Supabase REST 모드 (DB 포트 직결 없이 HTTPS 사용)
export SUPABASE_URL="https://hewavzpynhozjtwwgfxg.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="YOUR_SERVICE_ROLE_KEY"
# 선택: 직접 DB 접속이 필요하면 DATABASE_URL도 설정
# export DATABASE_URL="postgresql://postgres:YOUR_DB_PASSWORD@db.hewavzpynhozjtwwgfxg.supabase.co:6543/postgres?sslmode=require"
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
- 동기화 시 길드에서 빠진 유저는 삭제하지 않고 `is_active = false`로 비활성 처리(기록 보존), 신규 유저는 자동 추가됩니다.
- Nexon Open API Key가 필요하며, 요청 헤더 `x-nxopen-api-key`로 호출합니다.
- API 직접 확인 시 308 Redirect가 나오면 URL 끝 슬래시(`/`)가 필요한 경우입니다. `curl -L`을 사용하거나 `/guild/id/`, `/guild/basic/` 경로를 사용하세요.


## DB 설정 / Supabase 연결
- **권장(무료/안정)**: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`를 사용한 REST 모드 (HTTPS 443)
- **선택(직접 DB 접속)**: `DATABASE_URL` (Postgres TCP)
- 앱은 `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`가 있으면 REST 모드를 우선 사용합니다.
- `.env.example`에 두 방식 템플릿이 모두 있습니다.

## 서버 배포 (Render, 바로 시작)
1. GitHub에 현재 저장소를 푸시합니다.
2. Render 대시보드에서 **New + > Blueprint**를 선택하고 이 저장소를 연결합니다.
3. `render.yaml`을 읽어 웹 서비스를 생성합니다.
4. Render 서비스의 Environment에서 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`를 먼저 설정합니다. (`DATABASE_URL`은 선택)
5. Deploy를 실행하면 `gunicorn wsgi:application`으로 서버가 기동됩니다.

> 주의: Render 무료 플랜은 디스크가 영속적이지 않으므로 `uploads/` 원본 파일은 영구 보관되지 않습니다. OCR 결과/점수는 Postgres에 저장됩니다.

- 현재 대상 Supabase 프로젝트 URL(`https://hewavzpynhozjtwwgfxg.supabase.co`) 기준으로 연결 예시를 반영했습니다.

### Render에서 Docker 모드로 만든 경우
- 이미 Docker 기반 Web Service로 생성했다면, 저장소 루트의 `Dockerfile`을 사용해 그대로 배포할 수 있습니다.
- 또는 기존 서비스를 삭제하고 `Blueprint(render.yaml)` 방식으로 다시 생성해도 됩니다.


## Render 부팅 에러(IPv6 Network is unreachable) 대응
- REST 모드(`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`)를 쓰면 이 이슈를 대부분 회피할 수 있습니다.
- Supabase 연결은 가능하면 **Connection Pooler(포트 6543)** 문자열을 사용하세요.
- `DATABASE_URL`에 호스트를 대괄호(`[]`)로 감싸면 URL 파서 오류가 날 수 있습니다. (예: `@[db....]`)
- 이 프로젝트는 DB 연결 시 호스트를 IPv4로 해석해 `hostaddr`를 자동 주입하도록 처리했습니다(IPv6 미지원 환경 대응).
- 부팅 시 DB가 잠시 불가해도 앱 프로세스가 즉시 죽지 않도록 `wsgi.py`에서 스키마 초기화는 best-effort로 동작합니다.
- 참고: 앱에서 흔한 대괄호 오입력(`@[host]`)은 자동 정규화하도록 보완했습니다.

- 주차키는 업로드 폼의 기준 날짜(`input_date`)를 바탕으로 전주 목요일(한국시간)로 자동 생성됩니다.
