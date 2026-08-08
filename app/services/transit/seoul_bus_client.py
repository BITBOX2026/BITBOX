"""
서울시 버스 공공데이터 API HTTP 클라이언트

공공데이터포털(data.go.kr)의 서울시 버스 API를 호출하는 저수준 HTTP 레이어입니다.
응답이 JSON 또는 XML로 올 수 있어 두 형식을 모두 처리합니다.

인증 키 처리:
- 공공데이터포털에서 발급받은 키는 URL 인코딩된 형태로 제공됩니다.
- httpx params에 이미 인코딩된 키를 그대로 전달하면 '%'가 이중 인코딩되어 인증 실패가 납니다.
- 따라서 _normalize_service_key()로 디코딩한 후 전달합니다.
"""

from typing import Any
from urllib.parse import unquote

import httpx

from app.core.logger import get_logger
from app.services.core.exceptions import TransportAPIError
from app.services.core.http_client import get_http_client
from app.services.core.http_utils import http_retry as _http_retry
from app.services.core.settings_helper import get_setting
from app.services.transit.xml_utils import (
    XML_ELEMENT_TYPE,
    XML_PARSE_ERRORS,
    parse_untrusted_xml,
)

logger = get_logger(__name__)

# 서울시 버스 API가 성공으로 반환하는 결과 코드 목록
SUCCESS_CODES = {"0", "00", "NORMAL_CODE", "INFO-000", "SUCCESS"}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@_http_retry
async def _seoul_bus_get(url: str, params: dict[str, str]) -> httpx.Response:
    """서울버스 API GET 요청. 재시도 가능한 오류는 자동 재시도합니다."""
    response = await get_http_client().get(url, params=params)
    response.raise_for_status()
    return response


async def request_seoul_bus_payload(
    url: str,
    params: dict[str, str],
    stage: str,
    service_key_param_names: tuple[str, ...] = ("ServiceKey", "serviceKey"),
    service_key_setting_names: tuple[str, ...] = (
        "SEOUL_BUS_API_KEY",
        "PUBLIC_DATA_SERVICE_KEY",
    ),
) -> Any:
    """
    서울시 버스 API를 호출하고 파싱된 응답(JSON dict 또는 XML Element)을 반환합니다.

    service_key_param_names: 인증키 파라미터명 후보 목록 (API마다 다를 수 있음)
    두 번째 파라미터명으로 재시도할 때 첫 번째가 인증 오류인 경우에만 시도합니다.
    """
    service_key = _get_first_service_key(service_key_setting_names)
    if not service_key:
        raise TransportAPIError(
            f"{' or '.join(service_key_setting_names)} is not configured"
        )

    last_auth_error: tuple[str, str] | None = None

    try:
        for index, key_param_name in enumerate(service_key_param_names):
            safe_params = {
                key_param_name: service_key,
                **params,
                "resultType": "json",
            }

            response = await _seoul_bus_get(url, safe_params)
            payload = _parse_response_payload(response, stage)

            code, message = extract_result_code_message(payload)
            if code is None:
                logger.debug("공공데이터 API 응답에 resultCode 없음 (%s) — 성공으로 간주", stage)
            if code and not is_success_code(code):
                message = message or "공공데이터 API 오류"

                # 인증 오류일 때만 다음 파라미터명으로 재시도
                if index + 1 < len(service_key_param_names) and is_service_key_error(code, message):
                    last_auth_error = (code, message)
                    continue

                raise TransportAPIError(
                    f"공공데이터 API 오류({stage}): resultCode={code}, resultMsg={message}"
                )

            return payload

    except httpx.HTTPStatusError as exc:
        raise TransportAPIError(
            f"공공데이터 API HTTP 오류({stage}): status={exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise TransportAPIError(f"공공데이터 API 요청 오류({stage})") from exc

    if last_auth_error:
        code, message = last_auth_error
        raise TransportAPIError(
            f"공공데이터 API 인증 오류({stage}): resultCode={code}, resultMsg={message}"
        )

    raise TransportAPIError(f"공공데이터 API 오류({stage})")


def _get_first_service_key(setting_names: tuple[str, ...]) -> str:
    for setting_name in setting_names:
        service_key = _normalize_service_key(get_setting(setting_name))
        if service_key:
            return service_key
    return ""


def _parse_response_payload(response: httpx.Response, stage: str) -> Any:
    """응답을 JSON 우선으로 파싱합니다. JSON 실패 시 XML을 시도합니다."""
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise TransportAPIError(f"공공데이터 API 응답 크기 초과({stage})")

    try:
        return response.json()
    except ValueError:
        pass

    try:
        return parse_untrusted_xml(response.text)
    except XML_PARSE_ERRORS as exc:
        raise TransportAPIError(f"공공데이터 API 응답 해석 오류({stage})") from exc


def _normalize_service_key(service_key: object) -> str:
    """
    인코딩/디코딩 키를 모두 허용합니다.
    httpx params에 넣기 전에 URL 디코딩하여 이중 인코딩을 방지합니다.
    """
    if service_key is None:
        return ""
    return unquote(str(service_key).strip())


def extract_result_code_message(payload: Any) -> tuple[str | None, str | None]:
    """응답(JSON dict 또는 XML Element)에서 결과 코드와 메시지를 추출합니다."""
    if isinstance(payload, XML_ELEMENT_TYPE):
        return (
            _find_first_xml_text(payload, ["headerCd", "resultCode", "returnReasonCode"]),
            _find_first_xml_text(payload, ["headerMsg", "resultMsg", "returnAuthMsg", "errMsg"]),
        )

    if isinstance(payload, dict):
        return (
            _find_nested_value(payload, ["headerCd", "resultCode", "returnReasonCode"]),
            _find_nested_value(payload, ["headerMsg", "resultMsg", "returnAuthMsg", "errMsg"]),
        )

    return None, None


def _find_nested_value(value: Any, names: list[str]) -> str | None:
    """중첩된 JSON 구조에서 재귀적으로 키를 탐색합니다. 대소문자 무시."""
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


def _find_first_xml_text(root: Any, tag_names: list[str]) -> str | None:
    """XML 트리에서 주어진 태그 이름 목록 순서대로 첫 번째 텍스트 값을 찾습니다."""
    for tag_name in tag_names:
        for element in root.iter(tag_name):
            if element.text:
                return element.text
    return None


def is_success_code(code: str) -> bool:
    return code.strip().upper() in SUCCESS_CODES


def is_service_key_error(code: str, message: str) -> bool:
    """인증 키 관련 오류인지 판별합니다 (파라미터명 재시도 여부 결정에 사용)."""
    normalized_message = message.upper()
    return (
        code.strip() in {"7", "30"}
        or "SERVICE KEY" in normalized_message
        or "KEY인증실패" in message
    )
