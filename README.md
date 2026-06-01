# BITBOX

음성으로 대중교통 경로를 안내하는 백엔드 서버입니다.

클라이언트(라즈베리파이 등)가 녹음한 음성 파일을 전송하면, 실시간 경로/도착 정보를 조회해 안내 문장과 TTS 음성으로 응답합니다.

**지원 기능**
- 경로 안내: "서울역에서 강남역 가는 버스 알려줘"
- 도착 정보: "서울역 정류장에 402번 언제 와?"

**사용 API**
- OpenAI — 음성 인식(STT), 발화 분석(LLM), 음성 합성(TTS)
- Kakao Local API — 장소명 → 좌표 변환
- ODsay API — 대중교통 경로 조회
- 공공데이터포털 — 실시간 버스 도착 정보

---

## 1. 환경변수 설정

`.env.example`을 복사해 `.env`를 만들고 API 키를 입력합니다.

```powershell
# Windows
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

`.env` 필수 항목:

```env
USE_MOCK_EXTERNALS=false

OPENAI_API_KEY=
KAKAO_REST_API_KEY=
ODSAY_API_KEY=
PUBLIC_DATA_SERVICE_KEY=
```

기기 설치 위치 (출발지를 매번 말하지 않아도 되게 함):

```env
DEFAULT_ORIGIN_NAME=잠실역
```

---

## 2. 설치

```bash
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-backend.txt
```

---

## 3. 서버 실행

```bash
uvicorn app.main:app --reload
```

서버 상태 확인:

```
http://127.0.0.1:8000/health
```

---

## 4. API

`POST /api/process` — WAV 파일을 업로드하면 경로 안내 응답을 반환합니다.

**요청**
```
Content-Type: multipart/form-data
file: <WAV 파일>
```

**응답**
```json
{
  "status": "success",
  "message": "잠실에서 2호선을 타세요. 왕십리에서 경의중앙선으로 환승하시면 용산에 도착합니다. 약 41분 소요되며, 요금은 1,750원입니다.",
  "audio_base64": "<TTS 음성 base64>",
  "request_id": "e4e65e7f",
  "data": {
    "transcript": "용산역에 가고 싶어.",
    "intent": "route",
    "origin": "잠실역",
    "destination": "용산역",
    "transport_mode": "transit",
    "total_time_min": 41,
    "payment": 1750,
    "transfer_count": 1,
    "route_segments": [
      { "vehicle_type": "지하철", "line": "2호선", "start_name": "잠실", "end_name": "왕십리" },
      { "vehicle_type": "지하철", "line": "경의중앙선", "start_name": "왕십리", "end_name": "용산" }
    ],
    "source": "odsay"
  }
}
```

Swagger UI에서 직접 테스트:

```
http://127.0.0.1:8000/docs
```
