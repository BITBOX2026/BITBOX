from typing import Any
from urllib.parse import unquote
from xml.etree import ElementTree

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.services.constants import (
    SEOUL_BUS_ARRIVAL_URL,
    SEOUL_BUS_ROUTE_SEARCH_URL,
    SEOUL_ROUTE_STATION_URL,
    SEOUL_STATION_SEARCH_URL,
)
from app.services.exceptions import TransportAPIError
from app.services.settings_helper import get_setting


SUCCESS_CODES = {"0", "00", "NORMAL_CODE", "INFO-000", "SUCCESS"}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


_http_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)


@_http_retry
async def _seoul_bus_get(url: str, params: dict[str, str]) -> httpx.Response:
    """서울버스 API GET 요청. 재시도 가능한 오류는 자동 재시도합니다."""

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response


async def request_seoul_bus_payload(
    url: str,
    params: dict[str, str],
    stage: str,
    service_key_param_names: tuple[str, ...] = ("ServiceKey", "serviceKey"),
) -> Any:
    """서울시 버스 API를 호출하고 JSON 우선으로 응답을 반환합니다."""

    service_key = _normalize_service_key(get_setting("PUBLIC_DATA_SERVICE_KEY"))
    if not service_key:
        raise TransportAPIError("PUBLIC_DATA_SERVICE_KEY가 설정되지 않았습니다.")

    last_auth_error: tuple[str, str] | None = None

    try:
        for index, service_key_param_name in enumerate(service_key_param_names):
            safe_params = {
                service_key_param_name: service_key,
                **params,
                "resultType": "json",
            }

            response = await _seoul_bus_get(url, safe_params)
            payload = _parse_response_payload(response, stage)

            code, message = extract_result_code_message(payload)
            if code and not is_success_code(code):
                message = message or "공공데이터 API 오류"
                if (
                    index + 1 < len(service_key_param_names)
                    and is_service_key_error(code, message)
                ):
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
            f"공공데이터 API 오류({stage}): resultCode={code}, resultMsg={message}"
        )

    raise TransportAPIError(f"공공데이터 API 오류({stage})")


def _parse_response_payload(response: httpx.Response, stage: str) -> Any:
    try:
        return response.json()

    except ValueError:
        pass

    try:
        return ElementTree.fromstring(response.text)

    except ElementTree.ParseError as exc:
        raise TransportAPIError(f"공공데이터 API 응답 해석 오류({stage})") from exc


def _normalize_service_key(service_key: object) -> str:
    """
    공공데이터포털의 Encoding/Decoding 키 입력을 모두 허용합니다.

    httpx params에 이미 percent-encoded 된 키를 그대로 넣으면 '%'가 다시
    인코딩되어 인증 실패가 날 수 있으므로, params에는 decoded 형태로 넣습니다.
    """

    if service_key is None:
        return ""

    return unquote(str(service_key).strip())


def extract_result_code_message(payload: Any) -> tuple[str | None, str | None]:
    if isinstance(payload, ElementTree.Element):
        return (
            _find_first_xml_text(payload, ["headerCd", "resultCode", "returnReasonCode"]),
            _find_first_xml_text(
                payload,
                ["headerMsg", "resultMsg", "returnAuthMsg", "errMsg"],
            ),
        )

    if isinstance(payload, dict):
        return (
            _find_nested_value(payload, ["headerCd", "resultCode", "returnReasonCode"]),
            _find_nested_value(payload, ["headerMsg", "resultMsg", "returnAuthMsg", "errMsg"]),
        )

    return None, None


def _find_nested_value(value: Any, names: list[str]) -> str | None:
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


def _find_first_xml_text(root: ElementTree.Element, tag_names: list[str]) -> str | None:
    for tag_name in tag_names:
        for element in root.iter(tag_name):
            if element.text:
                return element.text

    return None


def is_success_code(code: str) -> bool:
    return code.strip().upper() in SUCCESS_CODES


def is_service_key_error(code: str, message: str) -> bool:
    normalized_message = message.upper()
    return code.strip() in {"7", "30"} or "SERVICE KEY" in normalized_message or "KEY인증실패" in message
