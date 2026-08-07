# BITBOX

정류장에서 음성으로 버스 경로와 실시간 도착 정보를 안내하는 AI 승차 도우미입니다.

클라이언트(라즈베리파이 등)가 녹음한 음성 파일을 전송하면, 실시간 경로/도착 정보를 조회해 안내 문장과 TTS 음성으로 응답합니다.

**지원 기능**
- 경로 안내: "서울역에서 강남역 가는 버스 알려줘"
- 도착 정보: "서울역 정류장에 402번 언제 와?"
- 안심 승차: 저상·비만차·저혼잡 버스 우선 표시
- 접근 알림: 선택한 버스가 3정거장·1정거장 전에 도착 음성 안내

**사용 API**
- OpenAI — 음성 인식(STT), 발화 분석(LLM), 음성 합성(TTS)
- Kakao Local API — 장소명 → 좌표 변환
- ODsay API — 버스 전용 경로 조회
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
  "message": "서울역버스환승센터에서 402번 버스를 타고 강남역에 내리세요. 약 42분 소요됩니다.",
  "audio_base64": "<TTS 음성 base64>",
  "request_id": "e4e65e7f",
  "data": {
    "transcript": "서울역에서 강남역 가는 버스 알려줘.",
    "intent": "route",
    "origin": "서울역",
    "destination": "강남역",
    "transport_mode": "bus",
    "total_time_min": 42,
    "transfer_count": 0,
    "route_segments": [
      { "vehicle_type": "버스", "line": "402번", "start_name": "서울역버스환승센터", "end_name": "강남역" }
    ],
    "source": "odsay"
  }
}
```

Swagger UI에서 직접 테스트:

```
http://127.0.0.1:8000/docs
```
