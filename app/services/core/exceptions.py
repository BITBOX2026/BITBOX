"""
파이프라인 예외 계층

모든 예외는 user_message 클래스 속성을 가집니다.
pipeline.py의 예외 핸들러에서 이 속성을 사용해 기술적 메시지 대신
사용자가 이해할 수 있는 안내 문구를 응답에 담습니다.

예외 상속 구조:
    Exception
    └── PipelineError              (기본 오류)
        ├── STTProcessingError     (음성 인식 실패)
        ├── LLMParsingError        (발화 분석 실패)
        └── TransportAPIError      (교통 정보 조회 실패)
            └── CoordinateResolveError  (장소 좌표 변환 실패)
"""


class PipelineError(Exception):
    user_message = "요청을 처리하지 못했습니다. 다시 말씀해 주세요."


class STTProcessingError(PipelineError):
    user_message = "음성을 인식하지 못했습니다. 다시 한 번 말씀해 주세요."


class LLMParsingError(PipelineError):
    user_message = "요청 내용을 분석하지 못했습니다. 목적지나 버스 번호를 다시 말씀해 주세요."


class TransportAPIError(PipelineError):
    user_message = "교통 정보를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요."

    def __init__(self, message: str = "", *, user_message: str = "") -> None:
        super().__init__(message)
        # user_message 키워드 인자를 통해서만 사용자 표시 문구를 재정의할 수 있음
        # positional message는 내부 로그 전용 — 사용자에게 노출되지 않음
        if user_message:
            self.user_message = user_message


class ExternalServiceError(TransportAPIError):
    """An upstream service failed independently of the user's request.

    ``retryable``    같은 요청을 다시 보내면 성공할 수 있는가 (재시도 판단).
    ``provider_down`` 제공자 자체가 망가졌는가 (회로 즉시 개방 판단).

    두 값은 서로 다릅니다. 잘못된 인증 키나 미설정은 재시도해도 소용없고 제공자
    전체가 사용 불가이므로 회로를 즉시 엽니다. 반면 특정 요청 하나에 대한 400/404는
    재시도해도 소용없지만 제공자는 정상이므로, 회로를 즉시 열어 ``/ready``를
    503으로 만들면 안 됩니다. 후자는 실패 횟수만 누적해 임계값에서 열립니다.
    """

    http_status = 502
    error_kind = "external_service"

    def __init__(
        self,
        message: str = "",
        *,
        user_message: str = "",
        retryable: bool = True,
        provider_down: bool = False,
    ) -> None:
        super().__init__(message, user_message=user_message)
        self.retryable = retryable
        self.provider_down = provider_down


class RouteNotFoundError(TransportAPIError):
    """The provider is healthy but has no usable bus-only route."""

    http_status = 404
    error_kind = "route_not_found"


class ProviderUsageError(TransportAPIError):
    """A local allowance guard stopped an outbound provider request."""

    error_kind = "usage_limit"

    def __init__(self, message: str, *, http_status: int, user_message: str) -> None:
        super().__init__(message, user_message=user_message)
        self.http_status = http_status


class CoordinateResolveError(TransportAPIError):
    # 장소명을 좌표로 변환하지 못한 경우 — 사용자가 더 정확한 이름을 말해야 함
    user_message = "목적지 위치를 찾지 못했습니다. 더 정확한 장소명을 말씀해 주세요."
