from app.services.service_types import ParsedIntent, RouteSegment, TransportResult

_SPECIAL_ARRIVAL_TEXTS: dict[str, str] = {
    "출발대기": "출발 대기 중입니다.",
    "곧 도착": "곧 도착 예정입니다.",
    "운행종료": "운행이 종료되었습니다.",
}


def build_user_message(
    parsed: ParsedIntent,
    transport_result: TransportResult,
) -> str:
    """검증된 교통 데이터만 사용해 최종 안내 문장을 생성합니다."""

    if parsed.intent == "route":
        return _build_route_message(transport_result)

    if parsed.intent == "arrival":
        return _build_arrival_message(transport_result)

    return "요청을 이해하지 못했습니다. 다시 말씀해 주세요."


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

    if len(segments) == 1:
        seg = segments[0]
        label = _vehicle_label(seg)
        return [
            f"{seg.start_name}에서 {label}{_josa_reul(label)} 타시면 "
            f"{seg.end_name}까지 가실 수 있습니다."
        ]

    parts: list[str] = []

    first = segments[0]
    label = _vehicle_label(first)
    parts.append(f"{first.start_name}에서 {label}{_josa_reul(label)} 타세요.")

    for i in range(1, len(segments) - 1):
        prev = segments[i - 1]
        cur = segments[i]
        label = _vehicle_label(cur)
        parts.append(f"{prev.end_name}에서 내려 {label}{_josa_ro(label)} 환승하세요.")

    prev = segments[-2]
    last = segments[-1]
    label = _vehicle_label(last)
    parts.append(
        f"{prev.end_name}에서 내려 {label}{_josa_ro(label)} 환승하시면 "
        f"{last.end_name}에 도착합니다."
    )

    return parts


def _build_fallback_guidance(result: TransportResult) -> str:
    """route_segments 없을 때 기존 필드로 안내 문장을 만듭니다."""

    if result.bus_number:
        night = " 야간버스" if _is_night_bus(result.bus_number) else ""
        label = f"{result.bus_number}번{night}"
        return (
            f"{result.origin}에서 {label}{_josa_reul(label)} 이용하시면 "
            f"{result.destination}까지 가실 수 있습니다."
        )

    if result.transport_mode == "subway":
        return f"{result.origin}에서 {result.destination} 방향 지하철을 이용하시면 됩니다."

    return f"{result.origin}에서 {result.destination}까지 버스와 지하철을 이용하시면 됩니다."


def _build_time_payment(total_time_min: int | None, payment: int | None) -> str:
    if total_time_min is not None and payment is not None:
        return f"약 {total_time_min}분 소요되며, 요금은 {payment:,}원입니다."
    if total_time_min is not None:
        return f"약 {total_time_min}분 소요됩니다."
    if payment is not None:
        return f"요금은 {payment:,}원입니다."
    return ""


def _vehicle_label(seg: RouteSegment) -> str:
    """구간 유형과 노선에 따른 탑승 수단 표현을 반환합니다."""

    if seg.vehicle_type == "버스":
        if _is_night_bus(seg.line):
            return f"{seg.line} 야간버스"
        return f"{seg.line} 버스"
    return seg.line


def _is_night_bus(bus_no: str) -> bool:
    return bus_no.strip().upper().startswith("N")


def _josa_reul(word: str) -> str:
    """단어 뒤에 붙는 목적격 조사 '을'/'를'을 반환합니다."""
    return "를" if _last_jongseong(word) == 0 else "을"


def _josa_ro(word: str) -> str:
    """단어 뒤에 붙는 방향격 조사 '로'/'으로'를 반환합니다."""
    j = _last_jongseong(word)
    return "로" if j == 0 or j == 8 else "으로"  # 8=ㄹ받침은 "로"


def _last_jongseong(word: str) -> int:
    """마지막 한글 글자의 받침 인덱스를 반환합니다. 받침 없으면 0."""
    if not word:
        return 0
    code = ord(word[-1]) - 0xAC00
    if code < 0 or code > 11171:
        return 0
    return code % 28


def _build_arrival_message(result: TransportResult) -> str:
    """특정 버스 도착 안내 문장을 생성합니다."""

    if not result.stop_name:
        return "해당 정류장의 버스 도착 정보를 찾지 못했습니다."

    if not result.bus_number:
        return "버스 번호를 확인하지 못했습니다. 다시 말씀해 주세요."

    if not result.arrival_time:
        return "해당 정류장의 버스 도착 정보를 찾지 못했습니다."

    special = _SPECIAL_ARRIVAL_TEXTS.get(result.arrival_time)
    if special:
        return f"{result.stop_name} 정류장 기준 {result.bus_number}번 버스는 {special}"

    return (
        f"{result.stop_name} 정류장 기준 {result.bus_number}번 버스는 "
        f"{_format_arrival_time(result.arrival_time)} 도착 예정입니다."
    )


def _format_arrival_time(arrival_time: str) -> str:
    """공공데이터 API가 준 도착 문구를 안내 문장에 맞게 정리합니다."""

    if arrival_time.startswith("약 "):
        return arrival_time

    if arrival_time[:1].isdigit():
        return f"약 {arrival_time}" if "후" in arrival_time else f"약 {arrival_time} 후"

    return arrival_time
