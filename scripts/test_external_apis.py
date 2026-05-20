import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.constants import TRANSIT_INTENT_SYSTEM_PROMPT

load_dotenv()


def get_env(name: str, required: bool = True) -> str | None:
    value = os.getenv(name)
    if required and not value:
        print(f"[ERROR] {name} 값이 .env에 없습니다.")
        sys.exit(1)
    return value


def geocode_kakao(query: str):
    kakao_key = get_env("KAKAO_REST_API_KEY")

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {kakao_key}"}
    params = {"query": query, "size": 1}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
    except requests.RequestException as exc:
        print(f"[FAIL] Kakao {query}: {type(exc).__name__}")
        return None

    print(f"[Kakao] {query} HTTP:", response.status_code)

    if response.status_code != 200:
        print("[FAIL] Kakao error:", summarize_error_response(response))
        return None

    data = response.json()
    documents = data.get("documents", [])

    if not documents:
        print(f"[FAIL] Kakao {query}: 검색 결과 없음")
        return None

    place = documents[0]
    name = place.get("place_name")
    x = place.get("x")
    y = place.get("y")

    print(f"[OK] Kakao {query}: {name} x={x} y={y}")

    return x, y


def test_kakao():
    print("\n========== Kakao Local API 테스트 ==========")

    origin = geocode_kakao("서울역")
    destination = geocode_kakao("강남역")

    if origin and destination:
        print("[OK] Kakao API 정상 동작")
    else:
        print("[FAIL] Kakao API 테스트 실패")

    return origin, destination


def test_odsay(origin, destination):
    print("\n========== ODsay API 테스트 ==========")

    odsay_key = get_env("ODSAY_API_KEY")

    if not origin or not destination:
        print("[SKIP] Kakao 좌표 변환 실패로 ODsay 테스트를 건너뜁니다.")
        return

    sx, sy = origin
    ex, ey = destination

    url = "https://api.odsay.com/v1/api/searchPubTransPathT"
    params = {
        "SX": sx,
        "SY": sy,
        "EX": ex,
        "EY": ey,
        "apiKey": odsay_key,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
    except requests.RequestException as exc:
        print(f"[FAIL] ODsay API 요청 실패: {type(exc).__name__}")
        return

    print("[ODsay] HTTP 상태:", response.status_code)

    try:
        data = response.json()
    except Exception:
        print("[FAIL] ODsay JSON 응답 해석 실패")
        return

    if "error" in data:
        print("[FAIL] ODsay error:", data.get("error"))
        return

    result = data.get("result", {})
    paths = result.get("path", [])

    if not paths:
        print("[ODsay] 경로 검색 결과가 없습니다.")
        return

    print("[OK] ODsay API 정상 동작")
    print(f"[ODsay] 서울역 -> 강남역 경로 수: {len(paths)}")


def extract_first_bus_number(sub_paths: list[dict]) -> str | None:
    for sub_path in sub_paths:
        if sub_path.get("trafficType") != 2:
            continue

        for lane in sub_path.get("lane", []):
            bus_number = lane.get("busNo")
            if bus_number:
                return str(bus_number)

    return None


def test_openai():
    print("\n========== OpenAI API 테스트 ==========")

    openai_key = get_env("OPENAI_API_KEY")

    try:
        from openai import OpenAI
    except ImportError:
        print("[ERROR] openai 패키지가 없습니다. python -m pip install openai 실행 필요")
        return

    client = OpenAI(api_key=openai_key)

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_TEST_MODEL", "gpt-4o-mini"),
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": TRANSIT_INTENT_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": "서울역에서 강남역 가는 버스 알려줘",
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "transit_intent_schema",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "intent": {
                                "type": "string",
                                "enum": ["route", "arrival", "unknown"],
                            },
                            "origin_text": {
                                "type": ["string", "null"],
                            },
                            "destination_text": {
                                "type": ["string", "null"],
                            },
                            "transport_mode": {
                                "type": "string",
                                "enum": ["bus", "subway", "transit", "unknown"],
                            },
                            "bus_number": {
                                "type": ["string", "null"],
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                            },
                        },
                        "required": [
                            "intent",
                            "origin_text",
                            "destination_text",
                            "transport_mode",
                            "bus_number",
                            "confidence",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            max_tokens=200,
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)

        print("[OK] OpenAI API 정상 동작")
        print("[OpenAI] JSON 응답:")
        print(json.dumps(parsed, ensure_ascii=False, indent=2))

        forbidden_keys = {
            "total_time_min",
            "arrival_time",
            "payment",
            "route_summary",
            "duration",
        }
        generated_keys = sorted(forbidden_keys.intersection(parsed))

        if generated_keys:
            print(f"[FAIL] OpenAI가 교통 정보 필드를 생성했습니다: {generated_keys}")
            return

        expected_values = {
            "intent": "route",
            "origin_text": "서울역",
            "destination_text": "강남역",
            "transport_mode": "bus",
        }

        mismatches = {
            key: parsed.get(key)
            for key, expected in expected_values.items()
            if parsed.get(key) != expected
        }

        if mismatches:
            print(f"[WARN] 예상 추출값과 다른 필드가 있습니다: {mismatches}")
            return

        print("[OK] OpenAI가 발화 추출 필드만 반환했습니다.")

    except Exception as e:
        print("[FAIL] OpenAI API 테스트 실패")
        print(type(e).__name__, str(e))


def summarize_error_response(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]

    if isinstance(payload, dict):
        for key in ["message", "msg", "error", "error_description"]:
            value = payload.get(key)
            if value:
                return str(value)

    return str(payload)[:200]


def test_public_data():
    print("\n========== 공공데이터 API 테스트 ==========")

    service_key = get_env("PUBLIC_DATA_SERVICE_KEY", required=False)

    if not service_key:
        print("[SKIP] PUBLIC_DATA_SERVICE_KEY가 비어 있습니다.")
        return

    print("[INFO] 공공데이터 키는 입력되어 있습니다.")
    print("[INFO] 다만 실시간 버스 도착 API는 busRouteId, 정류장 ID 같은 테스트 값이 필요합니다.")
    print("[INFO] 현재 단계에서는 키 존재 여부까지만 확인합니다.")


if __name__ == "__main__":
    origin, destination = test_kakao()
    test_odsay(origin, destination)
    test_openai()
