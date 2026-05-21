# BITBOX

BITBOX는 음성으로 출발지와 목적지를 말하면 실제 대중교통 경로를 조회해 안내 문구를 반환하는 백엔드 중심 프로젝트입니다.

현재 백엔드는 mock mode와 real mode를 모두 지원합니다. real mode에서는 OpenAI, Kakao Local API, ODsay API를 순서대로 호출해 `/api/process` end-to-end 테스트까지 성공한 상태입니다.

## 프로젝트 개요

사용자는 음성으로 다음과 같은 요청을 합니다.

```text
서울역에서 강남역 가는 버스 알려줘
```

FastAPI 백엔드는 업로드된 음성 파일을 처리해 다음 형태의 응답을 반환합니다.

```json
{
  "status": "success",
  "message": "서울역에서 강남역까지 가는 경로를 찾았습니다.",
  "data": {
    "origin": "서울역",
    "destination": "강남역",
    "transport_mode": "bus",
    "bus_number": "402",
    "total_time_min": 41,
    "payment": 1500,
    "bus_transit_count": 1,
    "subway_transit_count": 0,
    "path_type": 2,
    "source": "odsay"
  }
}
```

## 전체 백엔드 처리 흐름

```text
음성 파일 업로드
-> FastAPI /api/process
-> OpenAI STT로 음성을 텍스트로 변환
-> OpenAI LLM으로 발화 구조화 JSON 추출
-> 필수값 검증
-> route 요청이면 Kakao Local API로 출발지/목적지 좌표 변환
-> route 요청이면 ODsay API로 실제 대중교통 경로 조회
-> arrival 요청이면 공공데이터 API로 버스 도착 정보 조회
-> 실제 API 결과에서 경로/요금/소요 시간/버스 번호/도착 정보 추출
-> status, message, data 응답 반환
```

## 교통 정보 생성 원칙

OpenAI는 실제 교통 정보를 생성하지 않습니다.

OpenAI LLM은 사용자 발화에서 아래 필드만 추출합니다.

```json
{
  "intent": "route",
  "origin_text": "서울역",
  "destination_text": "강남역",
  "stop_text": null,
  "transport_mode": "bus",
  "bus_number": null,
  "confidence": 1.0
}
```

역할 분리는 다음과 같습니다.

- OpenAI: STT와 발화 구조화만 담당
- Kakao Local API: 출발지와 목적지 장소명을 좌표로 변환
- ODsay API: 실제 경로, 요금, 소요 시간, 환승 정보, 버스 번호 조회
- 공공데이터 API: 실시간 버스 도착 정보 조회

따라서 route 응답의 `total_time_min`, `payment`, `bus_number`, `bus_transit_count`, `subway_transit_count`, `path_type`은 ODsay 결과에서만 가져옵니다. arrival 응답의 `arrival_time`은 공공데이터 API 결과에서만 가져옵니다.

## ODsay 경로 선택 정책

`transport_mode`가 `bus`일 때는 버스 구간이 포함된 ODsay path만 후보로 사용합니다.

- 일반 버스 경로가 있으면 일반 버스 중 최단 시간 경로를 선택합니다.
- `N75`처럼 `N`으로 시작하는 야간버스는 일반 버스보다 후순위입니다.
- 일반 버스가 없고 야간버스만 있으면 야간버스 중 최단 시간 경로를 선택합니다.
- 버스 경로가 아예 없으면 지하철 경로를 임의로 안내하지 않고 오류 메시지를 반환합니다.

## 필요한 API 키

`.env`에 아래 키를 설정합니다.

```env
OPENAI_API_KEY=
KAKAO_REST_API_KEY=
ODSAY_API_KEY=
PUBLIC_DATA_SERVICE_KEY=
```

용도:

- `OPENAI_API_KEY`: STT, LLM 발화 구조화
- `KAKAO_REST_API_KEY`: 장소명 좌표 변환
- `ODSAY_API_KEY`: 실제 대중교통 경로 조회
- `PUBLIC_DATA_SERVICE_KEY`: 실시간 버스 도착 정보 조회

## 환경변수 설정

`.env.example`을 복사해 `.env`를 만듭니다.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

실제 API 키는 `.env`에만 입력합니다. `.env`는 Git 추적 대상이 아니어야 합니다.

## 설치

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

패키지 설치:

```bash
pip install -r requirements.txt
```

## Mock Mode 실행

mock mode는 외부 API를 실제 호출하지 않고 백엔드 흐름을 확인하는 모드입니다.

`.env`:

```env
USE_MOCK_EXTERNALS=true
```

서버 실행:

```bash
uvicorn app.main:app --reload
```

서버 상태 확인:

```bash
curl http://127.0.0.1:8000/health
```

mock 요청 테스트:

```bash
python test_client.py
```

## Real Mode 실행

real mode는 OpenAI, Kakao, ODsay, 공공데이터 API를 실제 호출할 수 있습니다.

`.env`:

```env
USE_MOCK_EXTERNALS=false
OPENAI_API_KEY=
KAKAO_REST_API_KEY=
ODSAY_API_KEY=
PUBLIC_DATA_SERVICE_KEY=
```

API 키 값은 코드, README, 로그에 남기지 않습니다.

`PUBLIC_DATA_SERVICE_KEY`는 arrival 기능에서 필요합니다.
공공데이터포털의 Decoding 키와 Encoding 키를 모두 입력할 수 있으며, 서버는 호출 전에 decoded 형태로 정규화합니다.

## 외부 API 단독 테스트

Kakao, ODsay, OpenAI 연결을 단독으로 확인합니다.

```bash
python scripts/test_external_apis.py
```

이 스크립트는 다음을 확인합니다.

- Kakao Local API로 서울역/강남역 좌표 변환
- ODsay API로 서울역 -> 강남역 경로 조회
- ODsay API로 조회 가능한 경로 수 확인
- OpenAI가 교통 정보를 생성하지 않고 발화 구조화 JSON만 반환하는지 확인

공공데이터 서비스키 인증만 분리해서 확인하려면 아래 스크립트를 사용합니다. 이 스크립트는 키 값과 `serviceKey`가 포함된 URL을 출력하지 않고, `getBusRouteList`의 `resultCode`, `resultMsg`, `itemCount`만 출력합니다.

```bash
python scripts/test_public_data_key.py
```

버스 번호를 바꿔 확인할 수도 있습니다.

```bash
python scripts/test_public_data_key.py --bus-number 146
```

## 테스트 음성 생성

OpenAI TTS로 `/api/process` 테스트용 음성 파일을 생성합니다.

```bash
python scripts/make_test_audio.py --output test_audio.wav
```

문장을 바꾸고 싶으면 `--text`를 사용합니다.

```bash
python scripts/make_test_audio.py --text "서울역에서 강남역 가는 버스 알려줘" --output test_audio.wav
```

## /api/process Real Mode 테스트

서버를 foreground로 오래 켜지 않고 FastAPI TestClient로 `/api/process`를 직접 테스트합니다.

```bash
python scripts/test_process_real.py --file test_audio.wav
```

확인 항목:

- 음성 파일 업로드
- OpenAI STT 성공
- OpenAI LLM 발화 추출 성공
- Kakao Local API 좌표 변환 성공
- ODsay API 실제 경로 조회 성공
- `source=odsay` 응답 확인

## Real Mode 성공 예시

`test_audio.wav`에 `"서울역에서 강남역 가는 버스 알려줘"`가 들어 있는 경우 성공 응답은 다음과 같은 형태입니다.

```text
status: success
origin: 서울역
destination: 강남역
transport_mode: bus
bus_number: 402
total_time_min: 41
payment: 1500
bus_transit_count: 1
subway_transit_count: 0
path_type: 2
source: odsay
```

실제 결과는 ODsay 조회 시점의 경로 데이터에 따라 달라질 수 있습니다.

## Route 회귀 테스트

음성/STT 없이 transcript 텍스트를 주입해 route 흐름을 확인합니다. 기본 실행은 mock mode이며 외부 API를 호출하지 않습니다.

```bash
python scripts/test_route_cases.py
```

실제 OpenAI/Kakao/ODsay 호출까지 확인하려면 명시적으로 `--real`을 붙입니다.

```bash
python scripts/test_route_cases.py --real
```

## Arrival 기능

arrival 기능은 특정 정류장 기준 특정 버스의 도착 예정 정보를 조회합니다.

예시 발화:

```text
서울역에서 402번 언제 와?
강남역 정류장에 146번 언제 도착해?
```

LLM은 다음 값만 추출합니다.

```json
{
  "intent": "arrival",
  "origin_text": null,
  "destination_text": null,
  "stop_text": "서울역",
  "transport_mode": "bus",
  "bus_number": "402",
  "confidence": 0.91
}
```

검증 정책:

- `bus_number`가 없으면 버스 번호를 다시 요청합니다.
- `stop_text`가 없으면 어느 정류장 기준인지 다시 요청합니다.
- 도착 시간은 OpenAI가 만들지 않고 공공데이터 API 응답만 사용합니다.

현재 제한사항:

- 서울시 버스 API 기준 1차 구현입니다.
- `stop_text`와 `bus_number`가 모두 필요합니다.
- 정류장명이 중복되면 첫 번째 후보를 사용할 수 있습니다.
- 노선 방향과 정류장 후보 선택 고도화는 추가 작업이 필요합니다.

arrival dry-run 테스트:

```bash
python scripts/test_arrival_cases.py
```

실제 OpenAI/공공데이터 API 호출까지 확인하려면 명시적으로 `--real`을 붙입니다.

```bash
python scripts/test_arrival_cases.py --real
```

## 주요 파일

```text
app/main.py                         FastAPI 앱 진입점
app/api/gateway.py                  /api/process 업로드 API
app/services/pipeline.py            STT -> LLM -> 검증 -> 교통 API -> 응답 생성 흐름
app/services/llm_service.py         OpenAI LLM 발화 구조화
app/services/validate_service.py    필수 발화 필드 검증
app/services/transport_service.py   Kakao 좌표 변환, ODsay 경로 조회/선택
app/services/public_bus_service.py  공공데이터 기반 버스 도착 조회
app/services/response_builder.py    최종 안내 문장 생성
scripts/test_external_apis.py       외부 API 단독 테스트
scripts/test_public_data_key.py     공공데이터 서비스키 인증 단독 테스트
scripts/make_test_audio.py          테스트 음성 생성
scripts/test_process_real.py        /api/process real mode 테스트
scripts/test_route_cases.py         route transcript 회귀 테스트
scripts/test_arrival_cases.py       arrival transcript 테스트
```

## 현재 미구현 기능

- 공공데이터 실시간 버스 도착 API 후보 선택 고도화
- Raspberry Pi 실기기 녹음/버튼/출력 연동
- AWS 배포
