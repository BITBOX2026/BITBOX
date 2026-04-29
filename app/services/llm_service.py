# STT 결과 문장에서 의도, 목적지, 버스 번호를 JSON 형태로 추출하는 LLM 서비스 파일입니다.

import json
import re

from openai import AsyncOpenAI

from app.services.constants import DEFAULT_LLM_MODEL, TRANSIT_INTENT_SYSTEM_PROMPT
from app.services.exceptions import LLMParsingError
from app.services.service_types import ParsedIntent
from app.services.settings_helper import get_setting, is_mock_mode


async def parse_transit_intent(transcript: str) -> ParsedIntent:
    """
    사용자의 자연어 발화를 교통 안내용 JSON 구조로 변환하는 함수입니다.

    기능:
        - STT로 변환된 문장에서 intent, destination_text, bus_number, confidence를 추출합니다.
        - 실제 모드에서는 OpenAI Structured Outputs를 사용합니다.
        - mock 모드에서는 간단한 규칙 기반 분석을 사용합니다.

    입력:
        transcript:
            - STT 결과 텍스트입니다.

    반환:
        ParsedIntent:
            - 분석된 사용자 의도 정보입니다.
    """

    if not transcript or not transcript.strip():
        return ParsedIntent(
            intent="unknown",
            destination_text=None,
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
                            "destination_text": {
                                "type": ["string", "null"],
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
                            "destination_text",
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
                destination_text=None,
                bus_number=None,
                confidence=0.0,
            )

        content = message.content
        if not content:
            raise LLMParsingError("LLM 응답이 비어 있습니다.")

        parsed_json = _safe_json_loads(content)

        return ParsedIntent(
            intent=parsed_json.get("intent", "unknown"),
            destination_text=parsed_json.get("destination_text"),
            bus_number=parsed_json.get("bus_number"),
            confidence=_safe_confidence(parsed_json.get("confidence")),
        )

    except LLMParsingError:
        raise

    except Exception as exc:
        raise LLMParsingError(f"LLM 분석 중 오류가 발생했습니다: {exc}") from exc


def _mock_parse_transit_intent(transcript: str) -> ParsedIntent:
    """
    mock 모드에서 사용자 발화를 간단히 분석하는 함수입니다.

    기능:
        - OpenAI API 없이 로컬에서 파이프라인 흐름을 테스트합니다.
        - 실제 운영용 자연어 분석을 완전히 대체하는 함수는 아닙니다.
    """

    text = transcript.strip()

    bus_number = _extract_bus_number(text)
    destination = _extract_destination(text)

    if bus_number and any(keyword in text for keyword in ["언제", "도착", "몇 분", "몇분"]):
        return ParsedIntent(
            intent="arrival",
            destination_text=None,
            bus_number=bus_number,
            confidence=0.85,
        )

    if destination:
        return ParsedIntent(
            intent="route",
            destination_text=destination,
            bus_number=bus_number,
            confidence=0.85,
        )

    if bus_number:
        return ParsedIntent(
            intent="arrival",
            destination_text=None,
            bus_number=bus_number,
            confidence=0.75,
        )

    return ParsedIntent(
        intent="unknown",
        destination_text=None,
        bus_number=None,
        confidence=0.0,
    )


def _extract_bus_number(text: str) -> str | None:
    """
    문장에서 버스 번호를 추출하는 함수입니다.

    기능:
        - "146번", "740 번" 같은 표현에서 숫자만 추출합니다.
    """

    match = re.search(r"(\d{1,4})\s*번", text)

    if not match:
        return None

    return match.group(1)


def _extract_destination(text: str) -> str | None:
    """
    문장에서 목적지로 보이는 표현을 추출하는 함수입니다.

    기능:
        - "강남역 가는 버스 알려줘"에서 "강남역"을 추출합니다.
        - "서울역까지 가고 싶어"에서 "서울역"을 추출합니다.
    """

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
            destination = match.group(1).strip()
            return _clean_destination(destination)

    return None


def _clean_destination(destination: str) -> str:
    """
    목적지 문자열에서 불필요한 표현을 제거하는 함수입니다.

    기능:
        - "제가 강남역" 같은 표현에서 불필요한 단어를 제거합니다.
        - 너무 과한 정규화는 하지 않고 최소한의 정리만 수행합니다.
    """

    cleaned = destination.strip()

    remove_words = [
        "저",
        "나",
        "제가",
        "나는",
        "혹시",
        "좀",
        "버스",
    ]

    for word in remove_words:
        cleaned = cleaned.replace(word, "").strip()

    return cleaned or destination


def _safe_confidence(value: object) -> float:
    """
    confidence 값을 0.0 ~ 1.0 범위로 안전하게 보정하는 함수입니다.

    기능:
        - LLM이 숫자가 아닌 값을 반환해도 서버가 바로 죽지 않게 합니다.
        - 범위를 벗어나면 0.0 ~ 1.0 사이로 보정합니다.
    """

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1.0, confidence))


def _safe_json_loads(content: str) -> dict:
    """
    LLM 응답 문자열을 안전하게 JSON으로 변환하는 함수입니다.

    기능:
        - Structured Outputs를 쓰면 보통 순수 JSON이 반환됩니다.
        - 예외적으로 ```json 코드블록이 포함되는 상황에 대비합니다.
    """

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