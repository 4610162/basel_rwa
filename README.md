# Basel III RWA Calculator

은행업감독업무시행세칙 [별표 3] 기반 신용위험 위험가중자산(RWA) 산출 시스템.

- **Backend**: FastAPI + RAG (ChromaDB + Gemini) → Docker
- **Frontend**: Next.js 15 (App Router) + Tailwind CSS → Vercel

---

## 프로젝트 구조

```
basel_bot/
├── docker-compose.yml        ← 로컬 Docker 실행
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example          ← 환경변수 템플릿
│   ├── data/
│   │   └── basel3.md         ← RAG 소스 세칙 문서
│   ├── rwa/                  ← SA 계산기 패키지
│   └── app/
│       ├── core/             config, rag_engine
│       ├── schemas/          Pydantic 입출력 모델
│       ├── routers/          chat (SSE), calculate
│       └── services/         rwa_service (계산기 디스패치)
└── frontend/
    ├── .env.example          ← 환경변수 템플릿
    ├── next.config.ts
    └── src/
        ├── app/              layout, page (탭 전환)
        ├── components/
        │   ├── Calculator.tsx   3-패널 RWA 계산기
        │   ├── Chat.tsx         실시간 스트리밍 Q&A
        │   ├── ExposureForm.tsx 동적 입력 폼
        │   └── RwaResultCard.tsx 결과 카드
        └── lib/
            ├── api.ts           API 클라이언트
            └── exposureConfig.ts 폼 구성 정의
```

---

## 로컬 개발 실행

### 사전 요구사항

| 항목 | 버전 |
|---|---|
| Python | 3.11 이상 |
| Node.js | 18 이상 |
| Google API Key | Gemini 접근 가능한 키 |

### Backend

```bash
cd backend
cp .env.example .env
# .env 에 GOOGLE_API_KEY 입력

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

uvicorn main:app --reload --port 8000
```

> 최초 실행 시 `data/basel3.md`를 자동으로 임베딩하여 `chroma_db/`에 저장합니다. (2~5분 소요)

### Frontend

```bash
cd frontend
cp .env.example .env.local     # 로컬 개발에서는 기본값으로 동작

npm install
npm run dev
```

`http://localhost:3000` 접속. `/api/*` 요청은 자동으로 `localhost:8000`으로 프록시됩니다.

---

## 프로덕션 배포

### Backend — Docker

#### 1. 환경변수 파일 준비

```bash
cp backend/.env.example backend/.env
```

`backend/.env` 에 다음 값을 설정합니다:

```dotenv
GOOGLE_API_KEY=your_google_api_key_here

# 프론트엔드 Vercel URL 포함 (배포 후 확인하여 추가)
CORS_ORIGINS=["http://localhost:3000","https://your-app.vercel.app"]
```

#### 2. Docker Compose로 실행

```bash
# 프로젝트 루트에서
docker compose up -d --build
```

헬스체크 확인:

```bash
curl http://localhost:8000/api/health
# → {"status":"ok","service":"Basel III RWA API"}
```

#### 3. 단독 Docker 실행 (Compose 없이)

```bash
docker build -t basel-bot-backend ./backend

docker run -d \
  --name basel-bot-backend \
  -p 8000:8000 \
  -e GOOGLE_API_KEY=your_key_here \
  -e CORS_ORIGINS='["https://your-app.vercel.app"]' \
  -v basel_chroma:/app/chroma_db \
  basel-bot-backend
```

> **ChromaDB 볼륨**: `-v basel_chroma:/app/chroma_db` 옵션으로 벡터 데이터를 영속화합니다.
> 컨테이너를 재생성해도 임베딩 데이터가 유지됩니다.

#### 4. 클라우드 배포 (Railway / Render / EC2)

플랫폼의 환경변수 설정에서 다음을 입력합니다:

| 환경변수 | 값 |
|---|---|
| `GOOGLE_API_KEY` | Gemini API 키 |
| `CORS_ORIGINS` | `["https://your-app.vercel.app"]` |

배포 후 서비스 URL (예: `https://basel-bot.railway.app`)을 메모해 둡니다.

---

### Frontend — Vercel

#### 1. Vercel 프로젝트 생성

```bash
# Vercel CLI 사용
npm i -g vercel
cd frontend
vercel
```

또는 [vercel.com](https://vercel.com)에서 GitHub 리포지토리를 연결합니다.

- **Framework Preset**: Next.js
- **Root Directory**: `frontend`

#### 2. 환경변수 설정

Vercel 대시보드 → Settings → Environment Variables 에서 추가:

| 변수명 | 값 | 환경 |
|---|---|---|
| `BACKEND_URL` | `https://your-backend-domain.com` | Production |
| `BACKEND_URL` | `http://localhost:8000` | Development |

#### 3. 배포

```bash
vercel --prod
```

> `BACKEND_URL` 은 Next.js `rewrites` 에서 서버사이드로만 사용되므로 `NEXT_PUBLIC_` 접두사가 불필요합니다.
> 클라이언트 브라우저에 백엔드 URL이 노출되지 않습니다.

---

## 환경변수 레퍼런스

### Backend (`backend/.env`)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `GOOGLE_API_KEY` | (필수) | Google Gemini API 키 |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | CORS 허용 Origin 목록 (JSON 배열) |
| `CHROMA_DB_PATH` | `./chroma_db` | ChromaDB 저장 경로 |
| `DATA_DIR` | `./data` | 세칙 문서 경로 |

### Frontend (`frontend/.env.local`)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `BACKEND_URL` | `http://localhost:8000` | FastAPI 백엔드 URL (서버사이드) |

---

## API 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/api/health` | 헬스체크 |
| `GET` | `/docs` | Swagger UI |
| `POST` | `/api/calculate/rwa` | RWA 산출 |
| `POST` | `/api/chat/stream` | RWA 챗봇 (SSE 스트리밍) |

### RWA 산출 예시

```bash
curl -X POST https://your-backend/api/calculate/rwa \
  -H "Content-Type: application/json" \
  -d '{
    "exposure_category": "gov",
    "entity_type": "central_gov",
    "exposure": 10000000000,
    "is_korea": true,
    "is_local_currency": true
  }'
```

```json
{
  "entity_type": "central_gov",
  "risk_weight": 0.0,
  "risk_weight_pct": "0.0%",
  "rwa": 0.0,
  "basis": "제29조"
}
```

---

## 지원 익스포져 카테고리

| 카테고리 | entity_type 값 | 적용 세칙 |
|---|---|---|
| **gov** 정부·공공기관 | `central_gov`, `zero_risk_entity`, `mdb_zero`, `mdb_general`, `pse_gov_like`, `pse_bank_like`, `pse_higher`, `pse_foreign`, `pse_foreign_gov_like` | 제29~34조 |
| **bank** 은행·금융회사 | `bank_ext`, `bank_dd`, `bank_short_ext`, `bank_short_dd`, `covered_bond_ext`, `covered_bond_unrated`, `securities_firm` | 제35~36조 |
| **corp** 기업·특수금융 | `general`, `general_short`, `sl_pf`, `sl_of`, `sl_cf`, `ipre`, `hvcre` | 제37~38조의2 |
| **ciu** 집합투자증권 | `lta`, `mba`, `fba` | 제44조 |
| **realestate** 부동산 | `cre_non_ipre`, `cre_ipre`, `adc`, `pf_consortium` | 제41~41조의2 |
| **equity** 주식 | `general_listed`, `unlisted_long_term`, `unlisted_speculative`, `govt_sponsored`, `subordinated_debt`, `other_capital_instrument`, `non_financial_large` | 제38조의3 |

---

## 트러블슈팅

**Q. Docker 빌드 시 `hnswlib` 컴파일 오류**
A. Dockerfile에 `build-essential`이 포함되어 있습니다. 빌드 시 자동으로 설치됩니다.

**Q. 컨테이너 시작 시 벡터스토어 초기화 실패**
A. 최초 실행 시 Gemini 임베딩 API를 호출합니다. `GOOGLE_API_KEY`가 올바른지 확인하세요.
헬스체크의 `start_period`가 60초로 설정되어 있으므로 초기화 완료까지 대기합니다.

**Q. CORS 오류 (Vercel → Backend)**
A. 백엔드 `CORS_ORIGINS` 환경변수에 Vercel 배포 URL을 추가하세요.
```
CORS_ORIGINS=["https://your-app.vercel.app"]
```

**Q. Vercel 배포 후 API 연결 실패**
A. Vercel 환경변수 `BACKEND_URL`이 설정되었는지 확인하세요.
설정 변경 후에는 재배포가 필요합니다.

**Q. 임베딩 중 `ResourceExhausted` (429) 오류**
A. Gemini API 무료 할당량 초과입니다. 잠시 후 재시작하거나 유료 플랜으로 전환하세요.

**Q. 로컬 SQLite 버전 오류 (ChromaDB)**
A. Python 3.11+ 환경에서 실행하거나 `pysqlite3-binary`를 추가 설치하세요.
```bash
pip install pysqlite3-binary
```


네. 순서는 백엔드 Railway -> 프론트 Vercel -> 다시 백엔드 CORS 보정이 가장 깔끔합니다.

1. 백엔드 Railway 배포

코드를 GitHub에 올립니다.
Railway에서 New Project를 누르고 Deploy from GitHub repo를 선택합니다.
이 저장소를 연결합니다.
서비스 설정에서 Root Directory를 /backend로 지정합니다.
Railway monorepo docs
backend/Dockerfile이 있으니 Railway가 이 Dockerfile을 사용해 빌드합니다.
Railway Dockerfile docs
Railway 서비스의 Variables에 아래를 넣습니다.
GOOGLE_API_KEY=실제_구글_API_키
CORS_ORIGINS=["http://localhost:3000"]
배포가 끝나면 서비스 Settings -> Networking에서 Generate Domain을 눌러 공개 주소를 만듭니다.
브라우저에서 아래처럼 확인합니다.
https://생성된-railway-주소/api/health
정상이라면 JSON이 보여야 합니다.

2. 프론트 Vercel 배포

Vercel에서 Add New -> Project를 선택합니다.
같은 GitHub 저장소를 import 합니다.
Root Directory를 frontend로 지정합니다.
Vercel monorepo docs
환경변수 BACKEND_URL을 추가합니다.
BACKEND_URL=https://생성된-railway-주소
중요: /api는 붙이지 않습니다.
5. Deploy 합니다.
6. 배포가 끝나면 Vercel 도메인 예: https://your-app.vercel.app 를 확인합니다.

3. Railway에서 CORS_ORIGINS 수정
이제 백엔드 Railway로 돌아가서 CORS_ORIGINS를 프론트 주소로 바꿉니다.

CORS_ORIGINS=["https://your-app.vercel.app"]
로컬도 같이 쓰려면:

CORS_ORIGINS=["http://localhost:3000","https://your-app.vercel.app"]
저장 후 재배포합니다.

4. 최종 확인

Vercel 프론트 주소에 접속합니다.
계산기 요청과 채팅 요청이 정상 동작하는지 봅니다.
Railway 백엔드 로그에서 에러가 없는지 확인합니다.
메뉴 위치 요약

Railway: Project -> Service -> Settings -> Root Directory / Networking, Variables
Vercel: Project -> Settings -> Environment Variables, import 시 Root Directory
주의

BACKEND_URL은 Railway 백엔드 주소 맞습니다.
CORS_ORIGINS는 JSON 배열 문자열이어야 합니다.
환경변수 추가 후에는 이전 배포에 자동 반영되지 않아서 재배포가 필요합니다.
Vercel env docs
Railway variables docs
원하시면 다음 답변에서 Railway 화면 기준으로 정말 클릭 순서대로, “어느 버튼 누르고 무슨 값 넣는지” 체크리스트 형태로 더 좁혀드릴게요.