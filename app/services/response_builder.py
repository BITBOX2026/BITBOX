# 검증된 교통 정보를 라즈베리파이에 전달할 정형 문장으로 변환하는 파일입니다.

from app.services.service_types import ParsedIntent, TransportResult


def build_user_message(
    parsed: ParsedIntent,
    transport_result: TransportResult,
) -> str:
    """
    최종 사용자 안내 문장을 생성하는 함수입니다.

    기능:
        - LLM이 만든 자유 문장을 그대로 사용하지 않습니다.
        - 검증된 교통 데이터만 이용해 정형 문장을 만듭니다.
        - 없는 정보는 억지로 만들어내지 않습니다.

    입력:
        parsed:
            - LLM 분석 결과입니다.

        transport_result:
            - 교통 API 조회 결과입니다.

    반환:
        str:
            - 라즈베리파이 화면 또는 TTS로 사용할 최종 안내 문장입니다.
    """

    if parsed.intent == "route":
        return _build_route_message(transport_result)

    if parsed.intent == "arrival":
        return _build_arrival_message(transport_result)

    return "요청을 이해하지 못했습니다. 다시 말씀해 주세요."


def _build_route_message(result: TransportResult) -> str:
    """
    목적지 경로 안내 문장을 생성하는 함수입니다.

    기능:
        - 목적지, 버스 번호, 도착 예정 시간, 총 소요 시간, 환승 횟수를 조합합니다.
        - 값이 없는 항목은 문장에 포함하지 않습니다.

    입력:
        result:
            - 교통 API 조회 결과입니다.

    반환:
        str:
            - 경로 안내 문장입니다.
    """

    if not result.destination:
        return "목적지를 확인하지 못했습니다. 다시 말씀해 주세요."

    if not result.bus_number and result.total_time_min is None:
        return f"{result.destination}까지 가는 경로를 찾지 못했습니다."

    parts = [f"{result.destination}까지 가는 경로를 찾았습니다."]

    if result.bus_number:
        parts.append(f"{result.bus_number}번 버스를 이용할 수 있습니다.")

    if result.arrival_time:
        parts.append(f"버스 도착 예정 시간은 약 {result.arrival_time}입니다.")

    if result.total_time_min is not None:
        parts.append(f"예상 소요 시간은 약 {result.total_time_min}분입니다.")

    if result.transfer_count is not None:
        parts.append(f"버스 환승 횟수는 {result.transfer_count}회입니다.")

    return " ".join(parts)


def _build_arrival_message(result: TransportResult) -> str:
    """
    특정 버스 도착 정보 안내 문장을 생성하는 함수입니다.

    기능:
        - 버스 번호와 도착 예정 시간을 이용해 정형 문장을 만듭니다.
        - 도착 시간이 없으면 조회 실패 문장을 반환합니다.

    입력:
        result:
            - 교통 API 조회 결과입니다.

    반환:
        str:
            - 버스 도착 안내 문장입니다.
    """

    if not result.bus_number:
        return "버스 번호를 확인하지 못했습니다. 다시 말씀해 주세요."

    if not result.arrival_time:
        return f"{result.bus_number}번 버스의 실시간 도착 정보를 찾지 못했습니다."

    return f"{result.bus_number}번 버스는 약 {result.arrival_time}에 도착할 예정입니다."