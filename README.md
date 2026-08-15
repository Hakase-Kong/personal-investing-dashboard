# My Market NiceGUI v0.1

Python만으로 만든 개인 투자 대시보드입니다.

## 구조

```text
main.py          NiceGUI 화면 + 웹서버
kis.py           한국투자증권 REST 현재가
market_data.py   종목 검색 + 미국 현재가
storage.py       관심종목 저장
```

Node.js, Next.js, Streamlit, Docker가 필요 없습니다.

## 로컬 실행

### 1. Python 확인

```bash
python --version
```

Python 3.11~3.12 권장.

### 2. 가상환경

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. 설치

```bash
pip install -r requirements.txt
```

### 4. 환경설정

```bash
copy .env.example .env
notepad .env
```

입력:

```env
KIS_APP_KEY=본인_APP_KEY
KIS_APP_SECRET=본인_APP_SECRET
KIS_ENV=real
REFRESH_SECONDS=5
PORT=8080
```

### 5. 실행

```bash
python main.py
```

브라우저:

```text
http://localhost:8080
```

## Render

GitHub에 이 폴더를 올리고 Render에서:

```text
New → Blueprint
```

로 repository를 선택합니다.

`render.yaml`이 설정을 자동으로 잡습니다.

Render Environment에서:

```text
KIS_APP_KEY
KIS_APP_SECRET
```

만 실제 값으로 입력합니다.

배포 후:

```text
https://my-market-nicegui-xxxx.onrender.com
```

형태의 주소를 받습니다.

UptimeRobot은:

```text
https://my-market-nicegui-xxxx.onrender.com/health
```

를 모니터링 대상으로 사용하면 됩니다.

## 현재 기능

- Python + NiceGUI
- 한국/미국 통합 검색창
- 관심종목 추가/삭제
- 한국 KIS 실제 현재가
- 미국 무료 현재가
- 5초 자동 업데이트
- 휴장일 마지막 가격 표시
- Render 배포 설정
- `/health`

## v0.2에서 할 것

- KIS 전체 국내 종목 마스터 자동 다운로드
- 관심종목 Supabase 영구 저장
- 보유수량/평단
- 평가금액/손익
- USD/KRW
- 미국 KIS 데이터 통합

## v0.3

- KIS WebSocket 실시간 체결
- 뉴스
- FRED / ECOS
- Telegram Alert
