import json
import re

from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.services.core.constants import DEFAULT_LLM_MODEL, TRANSIT_INTENT_SYSTEM_PROMPT
from app.services.core.exceptions import LLMParsingError
from app.services.core.service_types import ParsedIntent
from app.services.core.settings_helper import get_setting, is_mock_mode


_system_prompt_cache: str | None = None
_system_prompt_file_mtime: float | None = None  # 마지막으로 읽은 파일의 수정 시각


def _load_system_prompt() -> str:
    """
    시스템 프롬프트를 반환합니다.

    LLM_SYSTEM_PROMPT_FILE이 설정된 경우 파일을 읽습니다.
    파일이 변경되면(mtime 감지) 자동으로 다시 로드합니다.
    파일이 없거나 비어 있으면 내장 TRANSIT_INTENT_SYSTEM_PROMPT를 사용합니다.
    """
    import os
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

        except OSError:
            pass

    # 파일 미설정 또는 읽기 실패 시 내장 프롬프트 사용 (한 번만 캐싱)
    if _system_prompt_cache is None:
        _system_prompt_cache = TRANSIT_INTENT_SYSTEM_PROMPT
    return _system_prompt_cache

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=get_setting("OPENAI_API_KEY"))
    return _openai_client


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
                            "enum": ["bus", "subway", "transit", "unknown"],
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
        return ParsedIntent()

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
        bus_number=parsed_json.get("bus_number"),
        confidence=_safe_confidence(parsed_json.get("confidence")),
    )


async def parse_transit_intent(transcript: str) -> ParsedIntent:
    """STT 문장을 교통 안내용 intent JSON 구조로 변환합니다."""

    if not transcript or not transcript.strip():
        return ParsedIntent()

    if is_mock_mode():
        return _mock_parse_transit_intent(transcript)

    if not get_setting("OPENAI_API_KEY"):
        raise LLMParsingError("OPENAI_API_KEY가 설정되지 않았습니다.")

    llm_model = get_setting("LLM_MODEL", DEFAULT_LLM_MODEL)

    try:
        return await _call_llm(_get_openai_client(), llm_model, transcript)

    except LLMParsingError:
        raise

    except Exception as exc:
        raise LLMParsingError(f"LLM 분석 중 오류가 발생했습니다: {exc}") from exc


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
        return "transit"

    return "transit"


def _extract_bus_number(text: str) -> str | None:
    """문장에서 146번, 740 번 같은 버스 번호를 추출합니다."""

    match = re.search(r"(\d{1,4})\s*번", text)

    if not match:
        return None

    return match.group(1)


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

    return cleaned or place_text


def _safe_confidence(value: object) -> float:
    """confidence 값을 0.0 ~ 1.0 범위로 보정합니다."""

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1.0, confidence))


def _normalize_transport_mode(value: object) -> str:
    """LLM 응답의 transport_mode를 허용된 값으로 보정합니다."""

    if value in {"bus", "subway", "transit", "unknown"}:
        return str(value)

    return "unknown"


def _safe_json_loads(content: str) -> dict:
    """LLM 응답 문자열을 JSON dict로 변환합니다."""

    cleaned = content.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMParsingError("LLM 응답을 JSON으로 해석하지 못했습니다.") from exc
