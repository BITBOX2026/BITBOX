import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.core.constants import SEOUL_BUS_ROUTE_SEARCH_URL  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PUBLIC_DATA_SERVICE_KEY를 노출하지 않고 서울시 버스 노선 조회 인증만 확인합니다."
    )
    parser.add_argument(
        "--bus-number",
        default="402",
        help="인증 확인에 사용할 서울 버스 번호입니다. 기본값: 402",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    raw_key = os.getenv("PUBLIC_DATA_SERVICE_KEY")
    if not raw_key:
        print("[SKIP] PUBLIC_DATA_SERVICE_KEY가 비어 있습니다.")
        return

    service_key = unquote(raw_key.strip())
    key_format = "encoded" if raw_key.strip() != service_key else "decoded"

    print("[INFO] PUBLIC_DATA_SERVICE_KEY가 설정되어 있습니다.")
    print("[INFO] key_format:", key_format)
    print("[INFO] endpoint: getBusRouteList")

    try:
        response = requests.get(
            SEOUL_BUS_ROUTE_SEARCH_URL,
            params={
                "ServiceKey": service_key,
                "strSrch": args.bus_number,
                "resultType": "json",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        print("[FAIL] request_error:", type(exc).__name__)
        return

    print("[INFO] http_status:", response.status_code)

    payload = _parse_response(response.text)
    if payload is None:
        print("[FAIL] response_parse_error")
        return

    header_code = _find_first_value(payload, ["headerCd", "resultCode", "returnReasonCode"])
    header_message = _find_first_value(
        payload,
        ["headerMsg", "resultMsg", "returnAuthMsg", "errMsg"],
    )
    item_count = _find_first_value(payload, ["itemCount"])
    first_route_id = _find_first_value(payload, ["busRouteId"])
    first_route_name = _find_first_value(payload, ["busRouteNm"])

    print("[INFO] resultCode:", header_code)
    print("[INFO] resultMsg:", header_message)
    print("[INFO] itemCount:", item_count)

    if header_code == "0":
        print("[OK] route_lookup_authenticated: true")
        print("[INFO] first_busRouteId:", first_route_id)
        print("[INFO] first_busRouteNm:", first_route_name)
        return

    print("[FAIL] route_lookup_authenticated: false")
    print("[HINT] resultCode=7이면 키 승인 범위, 발급 직후 반영 지연, 또는 서비스키 형식을 확인하세요.")


def _parse_response(text: str) -> dict | ElementTree.Element | None:
    try:
        return json.loads(text)
    except ValueError:
        pass

    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return None


def _find_first_value(payload: dict | ElementTree.Element, names: list[str]) -> str | None:
    if isinstance(payload, ElementTree.Element):
        return _find_first_text(payload, names)

    return _find_nested_value(payload, names)


def _find_first_text(
    root: ElementTree.Element,
    tag_names: list[str],
) -> str | None:
    for tag_name in tag_names:
        value = _find_text(root, tag_name)
        if value:
            return value

    return None


def _find_text(root: ElementTree.Element, tag_name: str) -> str | None:
    for element in root.iter(tag_name):
        return element.text

    return None


def _find_nested_value(value: object, names: list[str]) -> str | None:
    normalized_names = {name.lower() for name in names}

    if isinstance(value, dict):
        for key, nested_value in value.items():
            if str(key).lower() in normalized_names and nested_value is not None:
                return str(nested_value)

        for nested_value in value.values():
            found = _find_nested_value(nested_value, names)
            if found:
                return found

    elif isinstance(value, list):
        for nested_value in value:
            found = _find_nested_value(nested_value, names)
            if found:
                return found

    return None


if __name__ == "__main__":
    main()
