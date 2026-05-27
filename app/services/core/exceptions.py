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


class CoordinateResolveError(TransportAPIError):
    # 장소명을 좌표로 변환하지 못한 경우 — 사용자가 더 정확한 이름을 말해야 함
    user_message = "목적지 위치를 찾지 못했습니다. 더 정확한 장소명을 말씀해 주세요."
