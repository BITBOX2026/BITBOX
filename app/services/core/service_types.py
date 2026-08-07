"""
파이프라인 전 구간에서 사용하는 공유 데이터 타입

STT → LLM → 검증 → 교통 API → 응답 빌더 순서로 전달되며,
각 단계는 이 타입들을 통해 데이터를 주고받습니다.
"""

from dataclasses import dataclass
from typing import Literal


# 허용된 intent 값 — LLM이 분류하는 사용자 요청 유형
IntentType = Literal["route", "arrival", "unknown"]

# 버스 전용 서비스이지만 명시적인 비지원 요청을 판별하기 위해 subway를 유지합니다.
TransportMode = Literal["bus", "subway", "unknown"]


@dataclass
class ParsedIntent:
    """LLM(또는 mock 파서)이 STT 결과를 구조화한 사용자 요청 정보입니다."""

    intent: IntentType = "unknown"
    origin_text: str | None = None        # 사용자가 말한 출발지 (없으면 기기 기본 출발지 사용)
    destination_text: str | None = None   # 사용자가 말한 목적지
    destination_x: float | None = None    # 자동완성에서 확정한 목적지 경도
    destination_y: float | None = None    # 자동완성에서 확정한 목적지 위도
    stop_text: str | None = None          # 버스 도착 조회 시 기준 정류장
    transport_mode: TransportMode = "unknown"
    bus_number: str | None = None         # 사용자가 말한 버스 번호
    confidence: float = 0.0               # LLM 분석 신뢰도 (0.0 ~ 1.0)


@dataclass
class ValidationResult:
    """파이프라인을 계속 진행할 수 있는지 판단한 결과입니다."""

    is_valid: bool
    message: str  # 실패 시 사용자에게 보여줄 안내 문구


@dataclass
class RouteSegment:
    """버스 경로의 한 탑승 구간을 나타냅니다."""

    vehicle_type: str       # "버스"
    line: str               # 예: "740번"
    start_name: str         # 탑승 정류장 이름
    end_name: str           # 하차 정류장 이름
    time_min: int | None = None  # ODsay subPath.time — 해당 구간 소요 시간(분)
    start_x: float | None = None  # 탑승 정류장 경도 (Kakao 지도용)
    start_y: float | None = None  # 탑승 정류장 위도
    end_x: float | None = None    # 하차 정류장 경도
    end_y: float | None = None    # 하차 정류장 위도
    path_points: list[dict[str, float]] | None = None  # 경유 정류장 좌표


@dataclass
class TransportResult:
    """교통 API 또는 mock 조회 결과를 파이프라인 공통 구조로 정규화한 값입니다."""

    origin: str | None = None
    destination: str | None = None
    origin_x: float | None = None         # 출발지 경도 (Kakao 지도용)
    origin_y: float | None = None         # 출발지 위도
    destination_x: float | None = None    # 목적지 경도
    destination_y: float | None = None    # 목적지 위도
    stop_name: str | None = None          # 버스 도착 조회 시 확인된 정류장명
    transport_mode: TransportMode = "unknown"
    bus_number: str | None = None
    arrival_time: str | None = None       # 첫 번째 버스 실시간 도착 시간 (예: "3분 후")
    arrival_time_2: str | None = None     # 두 번째 버스 실시간 도착 시간
    first_bus_time: str | None = None     # 운행종료 시 내일 첫차 시간 (예: "05:30")
    total_time_min: int | None = None     # 예상 소요 시간 (분)
    payment: int | None = None            # 예상 요금 (원)
    bus_transit_count: int | None = None
    transfer_count: int | None = None     # 환승 횟수
    path_type: int | None = None          # ODsay pathType (버스 경로는 2)
    route_summary: str | None = None      # 요약 안내 문구 (내부용)
    route_segments: list[RouteSegment] | None = None  # 구간별 탑승 정보
    source: str = "none"                  # 데이터 출처 ("odsay"|"public_data"|"mock"|"none")
