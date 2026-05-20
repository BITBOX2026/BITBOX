from app.services.service_types import ParsedIntent, TransportResult


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
    """출발지와 목적지를 포함한 경로 안내 문장을 생성합니다."""

    if not result.origin:
        return "출발지를 말씀해 주세요."

    if not result.destination:
        return "목적지를 확인하지 못했습니다. 다시 말씀해 주세요."

    if not result.bus_number and result.total_time_min is None:
        return f"{result.origin}에서 {result.destination}까지 가는 경로를 찾지 못했습니다."

    parts = [f"{result.origin}에서 {result.destination}까지 가는 경로를 찾았습니다."]

    if result.bus_number:
        parts.append(f"{result.bus_number}번 버스를 이용할 수 있습니다.")

    if result.arrival_time:
        parts.append(f"버스 도착 예정 시간은 약 {result.arrival_time}입니다.")

    if result.total_time_min is not None:
        parts.append(f"예상 소요 시간은 약 {result.total_time_min}분입니다.")

    if result.payment is not None:
        parts.append(f"요금은 {result.payment}원입니다.")

    if result.bus_transit_count is not None:
        parts.append(f"버스 이용 구간은 {result.bus_transit_count}개입니다.")

    if result.subway_transit_count is not None:
        parts.append(f"지하철 이용 구간은 {result.subway_transit_count}개입니다.")

    return " ".join(parts)


def _build_arrival_message(result: TransportResult) -> str:
    """특정 버스 도착 안내 문장을 생성합니다."""

    if not result.bus_number:
        return "버스 번호를 확인하지 못했습니다. 다시 말씀해 주세요."

    if not result.arrival_time:
        return f"{result.bus_number}번 버스의 실시간 도착 정보를 찾지 못했습니다."

    return f"{result.bus_number}번 버스는 약 {result.arrival_time}에 도착할 예정입니다."
