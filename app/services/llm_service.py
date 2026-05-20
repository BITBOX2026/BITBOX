import json
import re

from openai import AsyncOpenAI

from app.services.constants import DEFAULT_LLM_MODEL, TRANSIT_INTENT_SYSTEM_PROMPT
from app.services.exceptions import LLMParsingError
from app.services.service_types import ParsedIntent
from app.services.settings_helper import get_setting, is_mock_mode


async def parse_transit_intent(transcript: str) -> ParsedIntent:
    """STT 문장을 교통 안내용 intent JSON 구조로 변환합니다."""

    if not transcript or not transcript.strip():
        return ParsedIntent(
            intent="unknown",
            origin_text=None,
            destination_text=None,
            transport_mode="unknown",
            bus_number=None,
            confidence=0.0,
        )

    if is_mock_mode():
        return _mock_parse_transit_intent(transcript)

    api_key = get_setting("OPENAI_API_KEY")
    if not api_key:
        raise LLMParsingError("OPENAI_API_KEY가 설정되지 않았습니다.")

    llm_model = get_setting("LLM_MODEL", DEFAULT_LLM_MODEL)

    try:
        client = AsyncOpenAI(api_key=api_key)

        completion = await client.chat.completions.create(
            model=llm_model,
            temperature=0,
            messages=[
                {"role": "system", "content": TRANSIT_INTENT_SYSTEM_PROMPT},
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
        )

        message = completion.choices[0].message

        if getattr(message, "refusal", None):
            return ParsedIntent(
                intent="unknown",
                origin_text=None,
                destination_text=None,
                transport_mode="unknown",
                bus_number=None,
                confidence=0.0,
            )

        content = message.content
        if not content:
            raise LLMParsingError("LLM 응답이 비어 있습니다.")

        parsed_json = _safe_json_loads(content)

        return ParsedIntent(
            intent=parsed_json.get("intent", "unknown"),
            origin_text=parsed_json.get("origin_text"),
            destination_text=parsed_json.get("destination_text"),
            transport_mode=_normalize_transport_mode(
                parsed_json.get("transport_mode")
            ),
            bus_number=parsed_json.get("bus_number"),
            confidence=_safe_confidence(parsed_json.get("confidence")),
        )

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
            transport_mode="bus",
            bus_number=bus_number,
            confidence=0.85,
        )

    origin, destination = _extract_route_places(text)
    if destination is None:
        destination = _extract_destination(text)

    if destination:
        return ParsedIntent(
            intent="route",
            origin_text=origin,
            destination_text=destination,
            transport_mode=transport_mode,
            bus_number=bus_number,
            confidence=0.85,
        )

    if bus_number:
        return ParsedIntent(
            intent="arrival",
            origin_text=None,
            destination_text=None,
            transport_mode="bus",
            bus_number=bus_number,
            confidence=0.75,
        )

    return ParsedIntent(
        intent="unknown",
        origin_text=None,
        destination_text=None,
        transport_mode="unknown",
        bus_number=None,
        confidence=0.0,
    )


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

    patterns = [
        r"(.+?)\s*에서\s*(.+?)\s*(?:까지|가는|가고|으로|로)",
        r"(.+?)\s*부터\s*(.+?)\s*(?:까지|가는|가고|으로|로)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            origin = _clean_place_text(match.group(1))
            destination = _clean_place_text(match.group(2))
            return origin, destination

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

    remove_words = [
        "저",
        "나",
        "제가",
        "저는",
        "혹시",
        "좀",
        "버스",
    ]

    for word in remove_words:
        cleaned = cleaned.replace(word, "").strip()

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
