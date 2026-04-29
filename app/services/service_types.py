# 파이프라인 내부에서 공통으로 사용하는 데이터 구조를 정의하는 파일입니다.

from dataclasses import dataclass
from typing import Literal


IntentType = Literal["route", "arrival", "unknown"]


@dataclass
class ParsedIntent:
    """
    LLM이 사용자 발화를 분석한 결과를 담는 데이터 구조입니다.

    기능:
        - 사용자의 말에서 의도, 목적지, 버스 번호, 신뢰도를 분리해서 저장합니다.

    예:
        "강남역 가는 버스 알려줘"
        ->
        intent="route"
        destination_text="강남역"
        bus_number=None
        confidence=0.86
    """

    intent: IntentType = "unknown"
    destination_text: str | None = None
    bus_number: str | None = None
    confidence: float = 0.0


@dataclass
class ValidationResult:
    """
    LLM 분석 결과가 실제 서비스에서 처리 가능한지 검증한 결과입니다.

    기능:
        - 검증 성공 여부와 사용자에게 안내할 메시지를 함께 저장합니다.
    """

    is_valid: bool
    message: str


@dataclass
class TransportResult:
    """
    교통 API 조회 결과를 백엔드 내부에서 통일해서 사용하기 위한 데이터 구조입니다.

    기능:
        - ODsay, 공공데이터, mock 결과를 하나의 형태로 맞춥니다.
        - response_builder.py가 이 구조를 기반으로 최종 문장을 만듭니다.
    """

    destination: str | None = None
    bus_number: str | None = None
    arrival_time: str | None = None
    total_time_min: int | None = None
    transfer_count: int | None = None
    route_summary: str | None = None
    source: str = "none"