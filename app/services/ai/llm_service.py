import json
import os
import re
from dataclasses import replace

from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.core.logger import get_logger
from app.services.ai.korean_number_normalizer import (
    normalize_bus_number_token,
    normalize_spoken_bus_numbers,
)
from app.services.core.constants import DEFAULT_LLM_MODEL, TRANSIT_INTENT_SYSTEM_PROMPT
from app.services.core.exceptions import LLMParsingError
from app.services.core.openai_client import get_openai_client as _get_openai_client
from app.services.core.service_types import ParsedIntent
from app.services.core.settings_helper import (
    get_bool_setting,
    get_setting,
    is_mock_mode,
)

logger = get_logger(__name__)

_system_prompt_cache: str | None = None
_system_prompt_file_mtime: float | None = None  # 마지막으로 읽은 파일의 수정 시각


def _load_system_prompt() -> str:
    """
    시스템 프롬프트를 반환합니다.

    LLM_SYSTEM_PROMPT_FILE이 설정된 경우 파일을 읽습니다.
    파일이 변경되면(mtime 감지) 자동으로 다시 로드합니다.
    파일이 없거나 비어 있으면 내장 TRANSIT_INTENT_SYSTEM_PROMPT를 사용합니다.
    """
    global _system_prompt_cache, _system_prompt_file_mtime

    prompt_file = get_setting("LLM_SYSTEM_PROMPT_FILE")

    if prompt_file:
        try:
            current_mtime = os.path.getmtime(prompt_file)
            # 캐시가 있고 파일이 변경되지 않았으면 캐시 반환
            if _system_prompt_cache is not None and current_mtime == _system_prompt_file_mtime:
                return _system_prompt_cache

            # 파일 변경 감지 또는 최초 로드
            with open(prompt_file, encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                _system_prompt_cache = content
                _system_prompt_file_mtime = current_mtime
                return _system_prompt_cache

            # 파일이 비워진 경우: 내장 프롬프트로 폴백, mtime 갱신으로 반복 재읽기 방지
            _system_prompt_cache = TRANSIT_INTENT_SYSTEM_PROMPT
            _system_prompt_file_mtime = current_mtime
            return _system_prompt_cache

        except OSError:
            # 파일 삭제·권한 오류 시 캐시 초기화 → 내장 프롬프트 사용
            _system_prompt_cache = None
            _system_prompt_file_mtime = None

    # 파일 미설정 또는 읽기 실패 시 내장 프롬프트 사용 (한 번만 캐싱)
    if _system_prompt_cache is None:
        _system_prompt_cache = TRANSIT_INTENT_SYSTEM_PROMPT
    return _system_prompt_cache


@retry(
    retry=retry_if_exception_type(LLMParsingError),
    stop=stop_after_attempt(2),
    wait=wait_fixed(0.5),
    reraise=True,
)
async def _call_llm(client: AsyncOpenAI, llm_model: str, transcript: str) -> ParsedIntent:
    """LLM을 호출해 ParsedIntent를 반환합니다. JSON 파싱 실패 시 1회 재시도합니다."""

    completion = await client.chat.completions.create(
        model=llm_model,
        temperature=0,
        messages=[
            {"role": "system", "content": _load_system_prompt()},
            {"role": "user", "content": transcript},
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
                        "origin_text": {"type": ["string", "null"]},
                        "destination_text": {"type": ["string", "null"]},
                        "stop_text": {"type": ["string", "null"]},
                        "transport_mode": {
                            "type": "string",
                            "enum": ["bus", "subway", "unknown"],
                        },
                        "bus_number": {"type": ["string", "null"]},
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
                        "stop_text",
                        "transport_mode",
                        "bus_number",
                        "confidence",
                    ],
                    "additionalProperties": False,
                },
            },
        },
    )

    message = completion.choices[0].message

    if getattr(message, "refusal", None):
        raise LLMParsingError("LLM이 요청을 처리할 수 없습니다.")

    content = message.content
    if not content:
        raise LLMParsingError("LLM 응답이 비어 있습니다.")

    parsed_json = _safe_json_loads(content)

    return ParsedIntent(
        intent=parsed_json.get("intent", "unknown"),
        origin_text=parsed_json.get("origin_text"),
        destination_text=parsed_json.get("destination_text"),
        stop_text=parsed_json.get("stop_text"),
        transport_mode=_normalize_transport_mode(parsed_json.get("transport_mode")),
        bus_number=normalize_bus_number_token(parsed_json.get("bus_number")),
        confidence=_safe_confidence(parsed_json.get("confidence")),
    )


async def parse_transit_intent(transcript: str, request_id: str = "") -> ParsedIntent:
    """STT 문장을 교통 안내용 intent JSON 구조로 변환합니다."""

    if not transcript or not transcript.strip():
        return ParsedIntent()

    logger.info("[%s] LLM 분석 시작: transcript_length=%d", request_id, len(transcript))

    normalized_transcript = normalize_spoken_bus_numbers(transcript)
    if _has_ambiguous_bus_number_expression(normalized_transcript):
        logger.info("[%s] 복수 또는 비정상 버스 번호 발화 감지: 재확인 필요", request_id)
        return ParsedIntent()

    deterministic = _mock_parse_transit_intent(normalized_transcript)
    if get_bool_setting("INTENT_FAST_PATH_ENABLED", True) and _is_unambiguous(deterministic):
        logger.info(
            "[%s] 규칙 기반 의도 분석 사용: intent=%s",
            request_id,
            deterministic.intent,
        )
        return deterministic

    if is_mock_mode():
        return deterministic

    if not get_setting("OPENAI_API_KEY"):
        raise LLMParsingError("OPENAI_API_KEY가 설정되지 않았습니다.")

    llm_model = get_setting("LLM_MODEL", DEFAULT_LLM_MODEL)

    try:
        parsed = await _call_llm(_get_openai_client(), llm_model, normalized_transcript)
        return _preserve_explicit_named_bus_number(normalized_transcript, parsed)

    except LLMParsingError:
        raise

    except Exception as exc:
        raise LLMParsingError(f"LLM 분석 중 오류가 발생했습니다: {exc}") from exc


def _is_unambiguous(parsed: ParsedIntent) -> bool:
    if parsed.intent == "route":
        return bool(parsed.destination_text and parsed.confidence >= 0.8)
    if parsed.intent == "arrival":
        return bool(parsed.bus_number and parsed.confidence >= 0.8)
    return False


def _has_ambiguous_bus_number_expression(text: str) -> bool:
    """Reject lists and overlong values instead of selecting a plausible suffix."""

    # A five-or-more digit value is not a supported Seoul route number.  In
    # particular, `12345번` must never be truncated to the suffix `2345번`.
    if re.search(r"(?<!\d)\d{5,}\s*번", text):
        return True

    explicit_numbers = re.findall(
        r"(?<![0-9A-Za-z])(\d{1,4})(?!\d)\s*번",
        text,
    )
    if len(explicit_numbers) > 1:
        return True

    named_numbers = set(_extract_explicit_named_bus_numbers(text))
    if len(named_numbers) > 1 or (named_numbers and explicit_numbers):
        return True

    # STT often writes a choice such as "3, 4번 중에" with `번` only after
    # the last item.  This is a choice request, not a confident request for 4.
    return bool(
        re.search(
            r"(?<!\d)\d{1,4}\s*[,/·]\s*\d{1,4}\s*번(?:\s*중(?:에|에서)?)?",
            text,
        )
    )


def _extract_explicit_named_bus_numbers(text: str) -> list[str]:
    """Return route names whose prefix or hyphen is semantically significant."""
    matches = re.findall(
        r"(?<![0-9A-Za-z])([A-Za-z]{1,3}\d{1,4}|\d{1,4}-\d{1,4}[가-힣]*?)"
        r"(?=\s*번(?:\s|$|[,.!?])|\s|$|[,.!?])",
        text,
    )
    return [value.upper() if value[0].isalpha() else value for value in matches]


def _preserve_explicit_named_bus_number(text: str, parsed: ParsedIntent) -> ParsedIntent:
    """Prevent the LLM from stripping M/N prefixes or route-name hyphens."""
    candidates = list(dict.fromkeys(_extract_explicit_named_bus_numbers(text)))
    if not candidates:
        return parsed
    if len(candidates) != 1:
        return ParsedIntent()

    candidate = candidates[0]
    parsed_number = (parsed.bus_number or "").strip()
    if parsed_number.upper() == candidate.upper():
        return replace(parsed, bus_number=candidate)

    if candidate[0].isalpha() and parsed_number == re.sub(r"^[A-Za-z]+", "", candidate):
        logger.warning("LLM stripped a route prefix; restoring the explicit transcript value")
        return replace(parsed, bus_number=candidate)

    # A conflict is safety-sensitive: ask again instead of querying another route.
    logger.warning("LLM bus number conflicts with the explicit named route; requesting confirmation")
    return ParsedIntent()


def _mock_parse_transit_intent(transcript: str) -> ParsedIntent:
    """OpenAI API 없이 로컬에서 기본 발화 패턴을 분석합니다."""

    text = transcript.strip()
    bus_number = _extract_bus_number(text)
    transport_mode = _extract_transport_mode(text, bus_number)

    if bus_number and any(keyword in text for keyword in ["언제", "도착", "몇 분", "몇분"]):
        return ParsedIntent(
            intent="arrival",
            origin_text=None,
            destination_text=None,
            stop_text=_extract_stop_text(text, bus_number),
            transport_mode="bus",
            bus_number=bus_number,
            confidence=0.85,
        )

    origin, destination = _extract_route_places(text)
    if origin is None and destination is None:
        destination = _extract_destination(text)

    if origin and destination is None:
        return ParsedIntent(
            intent="route",
            origin_text=origin,
            destination_text=None,
            stop_text=None,
            transport_mode=transport_mode,
            bus_number=bus_number,
            confidence=0.85,
        )

    if destination:
        return ParsedIntent(
            intent="route",
            origin_text=origin,
            destination_text=destination,
            stop_text=None,
            transport_mode=transport_mode,
            bus_number=bus_number,
            confidence=0.85,
        )

    if bus_number:
        return ParsedIntent(
            intent="arrival",
            transport_mode="bus",
            bus_number=bus_number,
            confidence=0.75,
        )

    return ParsedIntent()


def _extract_stop_text(text: str, bus_number: str) -> str | None:
    """도착 정보 발화에서 정류장명 또는 기준 위치를 추출합니다."""

    escaped_bus = re.escape(bus_number)
    patterns = [
        rf"(.+?)\s*에서\s*{escaped_bus}\s*번",
        rf"(.+?)\s*정류장에\s*{escaped_bus}\s*번",
        rf"(.+?)\s*정류장에서\s*{escaped_bus}\s*번",
        rf"(.+?)\s*에\s*{escaped_bus}\s*번",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return _clean_place_text(match.group(1))

    return None


def _extract_transport_mode(text: str, bus_number: str | None) -> str:
    """발화에서 사용자가 요청한 교통수단만 추출합니다."""

    if "버스" in text or bus_number:
        return "bus"

    if "지하철" in text or "전철" in text:
        return "subway"

    if "대중교통" in text:
        return "bus"

    return "bus"


def _extract_bus_number(text: str) -> str | None:
    """문장에서 146번, 740 번 같은 버스 번호를 추출합니다."""

    if _has_ambiguous_bus_number_expression(text):
        return None

    matches = list(
        re.finditer(r"(?<![0-9A-Za-z])(\d{1,4})(?!\d)\s*번", text)
    )

    if len(matches) != 1:
        return None

    return matches[0].group(1)


def _extract_route_places(text: str) -> tuple[str | None, str | None]:
    """출발지와 목적지가 함께 있는 route 문장에서 장소 두 개를 추출합니다."""

    # 두 장소 패턴을 먼저 시도 — 목적지가 있으면 우선 캡처
    two_place_patterns = [
        r"(.+?)\s*에서\s*(.+?)\s*(?:까지|가는|가고|으로|로)",
        r"(.+?)\s*부터\s*(.+?)\s*(?:까지|가는|가고|으로|로)",
    ]

    for pattern in two_place_patterns:
        match = re.search(pattern, text)
        if match:
            origin = _clean_place_text(match.group(1))
            destination = _clean_place_text(match.group(2))
            if origin and destination:
                return origin, destination

    # 두 장소 패턴 실패 시 출발지만 있는 패턴 시도
    origin_only_patterns = [
        r"(.+?)\s*에서\s*(?:까지|가는|가고|으로|로)",
        r"(.+?)\s*부터\s*(?:까지|가는|가고|으로|로)",
    ]

    for pattern in origin_only_patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_place_text(match.group(1)), None

    return None, None


def _extract_destination(text: str) -> str | None:
    """출발지 없이 목적지만 말한 route 문장에서 목적지를 추출합니다."""

    patterns = [
        r"(.+?)\s*가는",
        r"(.+?)\s*까지",
        r"(.+?)\s*가고",
        r"(.+?)\s*으로",
        r"(.+?)\s*로",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return _clean_place_text(match.group(1))

    return None


def _clean_place_text(place_text: str) -> str:
    """장소명 앞뒤에 붙은 불필요한 말을 최소한으로 제거합니다."""

    cleaned = place_text.strip()

    # 단독 출현 단어만 제거 (공백/문자열 경계 기준) — 장소명 부분문자열 보호
    # 예: "버스 서울역"의 "버스"는 제거, "버스터미널"의 "버스"는 유지
    standalone_words = ["저는", "제가", "혹시", "저", "나", "좀", "버스"]
    for word in standalone_words:
        cleaned = re.sub(rf"(?<!\S){re.escape(word)}(?!\S)", "", cleaned).strip()

    return cleaned


def _safe_confidence(value: object) -> float:
    """confidence 값을 0.0 ~ 1.0 범위로 보정합니다."""

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1.0, confidence))


def _normalize_transport_mode(value: object) -> str:
    """LLM 응답의 transport_mode를 허용된 값으로 보정합니다."""

    if value in {"bus", "subway", "unknown"}:
        return str(value)

    return "unknown"


def _safe_json_loads(content: str) -> dict:
    """LLM 응답 문자열을 JSON dict로 변환합니다."""
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise LLMParsingError("LLM 응답을 JSON으로 해석하지 못했습니다.") from exc
