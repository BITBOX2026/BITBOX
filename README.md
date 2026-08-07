# BITBOX

정류장에서 음성으로 버스 경로와 실시간 도착 정보를 안내하는 AI 승차 도우미입니다.

클라이언트(라즈베리파이 등)가 녹음한 음성 파일을 전송하면, 실시간 경로/도착 정보를 조회해 안내 문장과 TTS 음성으로 응답합니다.

**지원 기능**
- 경로 안내: "서울역에서 강남역 가는 버스 알려줘"
- 도착 정보: "서울역 정류장에 402번 언제 와?"
- 저상·여유 우선: 현재 정류장의 저상·비만차·저혼잡 도착 차량 우선 표시
- 도착 단계 알림: 선택한 차량이 3정거장 이내·1정거장·도착 단계에 진입하면 음성 안내

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
DEFAULT_ORIGIN_NAME=올림픽공원역
DEFAULT_BUS_STOP_NAME=올림픽공원역
DEFAULT_BUS_STATION_ID=24245
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

---

## 5. 운영 배포 전제조건

브라우저 음성 녹음은 안전한 컨텍스트에서만 동작하므로 운영 화면은 HTTPS로 제공해야 합니다.
GitHub Actions 통합 배포 전에 다음 저장소 비밀값을 설정합니다.

```text
EC2_HOST
EC2_SSH_KEY
API_AUTH_TOKEN
KAKAO_MAP_APPKEY
OPENAI_API_KEY
KAKAO_REST_API_KEY
ODSAY_API_KEY
PUBLIC_DATA_SERVICE_KEY
BITBOX_SERVER_NAME
BITBOX_TLS_CERT_PATH
BITBOX_TLS_KEY_PATH
```

- `API_AUTH_TOKEN`: URL-safe 난수 문자열을 사용합니다.
- `BITBOX_SERVER_NAME`: EC2 주소로 해석되는 실제 도메인입니다.
- 인증서가 없으면 배포 작업이 EC2 인스턴스 IAM 역할로 보안 그룹의 `80/443`을 열고 Certbot 인증서를 발급합니다. 해당 역할에는 보안 그룹 인바운드 규칙 변경 권한이 필요합니다.
- 인증서와 개인 키는 EC2에만 저장되며 저장소에 커밋하지 않습니다.
- Kakao Developers 웹 플랫폼에는 `https://도메인`과 기존 호환 주소 `https://도메인:8000`을 등록합니다.

병합 브랜치 푸시 시 GitHub 러너가 백엔드 테스트, 프론트 테스트·타입 검사·빌드를 수행합니다.
검증된 정적 파일만 EC2로 전송하며, 필수 비밀값·IAM 권한·TLS 발급 중 하나라도 실패하면 서비스 전환 전에 배포를 중단합니다.

## 6. 안내 정확도 범위

- 지도 선은 ODsay 정류장 순서와 구간 좌표를 연결한 예상 경로이며 도로 중심선과 완전히 같지 않을 수 있습니다.
- 도착 단계 알림은 서울 버스 도착정보를 15초마다 갱신한 결과이며 GPS 연속 추적이 아닙니다.
- 저상·여유 우선 정렬은 현재 정류장 도착 차량에 적용되며 목적지 경로 자체를 재계산하지 않습니다.
