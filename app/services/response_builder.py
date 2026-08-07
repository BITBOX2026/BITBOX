"""
사용자 안내 문장 생성기

교통 API 조회 결과(TransportResult)를 자연스러운 한국어 안내 문장으로 변환합니다.

route intent:  "서울역에서 740번 버스를 타시면 강남역까지 가실 수 있습니다. 약 24분 소요됩니다."
arrival intent: "서울역 정류장 기준 740번 버스는 약 3분 후 도착 예정입니다."
"""

import re

from app.services.core.service_types import ParsedIntent, RouteSegment, TransportResult
from app.services.transit.seoul_bus_parser import is_night_bus_number as _is_night_bus

# 공공데이터 API가 반환하는 특수 도착 상태 문자열과 사용자 친화적 문구 매핑
_SPECIAL_ARRIVAL_TEXTS: dict[str, str] = {
    "출발대기": "출발 대기 중입니다.",
    "곧 도착": "곧 도착 예정입니다.",
    "운행종료": "운행이 종료되었습니다.",
}

# 오늘 더 이상 운행하지 않는 상태 코드 (두 번째 버스 안내 제외에 사용)
_TERMINAL_ARRIVAL_STATES = {"운행종료"}


def build_user_message(
    parsed: ParsedIntent,
    transport_result: TransportResult,
) -> str:
    """검증된 교통 데이터를 사용자 안내 문장으로 변환합니다."""
    if parsed.intent == "route":
        return _build_route_message(transport_result)

    if parsed.intent == "arrival":
        return _build_arrival_message(transport_result)

    return "요청을 이해하지 못했습니다. 다시 말씀해 주세요."


# ---------------------------------------------------------------------------
# 경로 안내 문장 생성
# ---------------------------------------------------------------------------

def _build_route_message(result: TransportResult) -> str:
    if not result.origin:
        return "출발지를 말씀해 주세요."

    if not result.destination:
        return "목적지를 확인하지 못했습니다. 다시 말씀해 주세요."

    if not result.route_segments and not result.bus_number and result.total_time_min is None:
        return f"{result.origin}에서 {result.destination}까지 가는 경로를 찾지 못했습니다."

    parts: list[str] = []

    if result.route_segments:
        parts.extend(_build_segment_guidance(result.route_segments))
    else:
        parts.append(_build_fallback_guidance(result))

    tail = _build_time_payment(result.total_time_min, result.payment)
    if tail:
        parts.append(tail)

    return " ".join(parts)


def _build_segment_guidance(segments: list[RouteSegment]) -> list[str]:
    """탑승 구간 목록으로 자연스러운 안내 문장 목록을 만듭니다."""
    if not segments:
        return []

    guidance: list[str] = []
    for segment in segments:
        if segment.vehicle_type == "도보":
            duration = f"약 {segment.time_min}분 " if segment.time_min else ""
            target = segment.end_name or "다음 탑승 지점"
            guidance.append(f"{target}까지 {duration}걸어가세요.")
            continue

        label = _vehicle_label(segment)
        guidance.append(
            f"{segment.start_name}에서 {label}{_josa_reul(label)} 타고 "
            f"{segment.end_name}에 내리세요."
        )

    return guidance


def _build_fallback_guidance(result: TransportResult) -> str:
    """route_segments가 없을 때 bus_number / transport_mode로 안내 문장을 만듭니다."""
    if result.bus_number:
        night = " 야간버스" if _is_night_bus(result.bus_number) else ""
        label = f"{result.bus_number}번{night}"
        return (
            f"{result.origin}에서 {label}{_josa_reul(label)} 이용하시면 "
            f"{result.destination}까지 가실 수 있습니다."
        )

    return f"{result.origin}에서 {result.destination}까지 가는 경로를 찾지 못했습니다."


def _build_time_payment(total_time_min: int | None, payment: int | None) -> str:
    if total_time_min is not None and payment is not None:
        return f"약 {total_time_min}분 소요되며, 요금은 {payment:,}원입니다."
    if total_time_min is not None:
        return f"약 {total_time_min}분 소요됩니다."
    if payment is not None:
        return f"요금은 {payment:,}원입니다."
    return ""


# ---------------------------------------------------------------------------
# 버스 도착 안내 문장 생성
# ---------------------------------------------------------------------------

def _build_arrival_message(result: TransportResult) -> str:
    if not result.stop_name:
        return "해당 정류장의 버스 도착 정보를 찾지 못했습니다."

    if not result.bus_number:
        return "버스 번호를 확인하지 못했습니다. 다시 말씀해 주세요."

    if not result.arrival_time:
        return "해당 정류장의 버스 도착 정보를 찾지 못했습니다."

    # 출발대기 / 곧 도착 / 운행종료 등 특수 상태 처리
    special = _SPECIAL_ARRIVAL_TEXTS.get(result.arrival_time)
    if special:
        base = f"{result.stop_name} 정류장 기준 {result.bus_number}번 버스는 {special}"
        if result.arrival_time == "운행종료" and result.first_bus_time:
            base += f" 내일 첫차는 {result.first_bus_time}입니다."
        return base

    message = (
        f"{result.stop_name} 정류장 기준 {result.bus_number}번 버스는 "
        f"{_format_arrival_time(result.arrival_time)} 도착 예정입니다."
    )

    if result.arrival_time_2:
        second_special = _SPECIAL_ARRIVAL_TEXTS.get(result.arrival_time_2)
        if second_special:
            message += f" 다음 버스는 {second_special}"
        elif result.arrival_time_2 not in _TERMINAL_ARRIVAL_STATES:
            message += f" 다음 버스는 {_format_arrival_time(result.arrival_time_2)} 도착합니다."

    return message


def _format_arrival_time(arrival_time: str) -> str:
    """공공데이터 API 도착 문구를 안내 문장에 맞게 정리합니다."""
    compact = re.fullmatch(r"(\d+)분(?:(\d+)초)?후(?:\[.+\])?", arrival_time.strip())
    if compact:
        minutes, seconds = compact.group(1), compact.group(2)
        parts = [f"{minutes}분"]
        if seconds:
            parts.append(f"{seconds}초")
        # "[N번째전]" 같은 정류소 수 표기는 TTS에서 어색하므로 제외
        return f"약 {' '.join(parts)} 후"

    if arrival_time.startswith("약 "):
        return arrival_time
    if arrival_time[:1].isdigit():
        return f"약 {arrival_time}" if "후" in arrival_time else f"약 {arrival_time} 후"
    return arrival_time


# ---------------------------------------------------------------------------
# 한국어 조사 / 차량 레이블 헬퍼
# ---------------------------------------------------------------------------

def _vehicle_label(seg: RouteSegment) -> str:
    """구간의 차량 유형과 노선명을 조합한 탑승 수단 표현을 반환합니다."""
    if seg.vehicle_type == "버스":
        if _is_night_bus(seg.line):
            return f"{seg.line} 야간버스"
        return f"{seg.line} 버스"
    return seg.line


def _josa_reul(word: str) -> str:
    """받침 유무에 따라 목적격 조사 '을' 또는 '를'을 반환합니다."""
    return "를" if _last_jongseong(word) == 0 else "을"



def _last_jongseong(word: str) -> int:
    """마지막 한글 글자의 받침 인덱스를 반환합니다. 받침 없음 = 0."""
    if not word:
        return 0
    code = ord(word[-1]) - 0xAC00
    if code < 0 or code > 11171:
        return 0
    return code % 28
