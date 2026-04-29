# 서비스 계층에서 발생하는 예외를 기능별로 구분하기 위한 파일입니다.


class PipelineError(Exception):
    """
    파이프라인 처리 중 발생하는 기본 예외입니다.

    기능:
        - 모든 서비스 예외의 부모 클래스 역할을 합니다.
        - pipeline.py에서 공통적으로 잡아서 사용자 메시지를 만들 수 있습니다.
    """

    user_message = "요청을 처리하지 못했습니다. 다시 말씀해 주세요."


class STTProcessingError(PipelineError):
    """
    음성 파일을 텍스트로 변환하는 과정에서 발생하는 예외입니다.

    발생 예:
        - 음성 파일이 비어 있음
        - OpenAI STT API 호출 실패
        - STT 결과 텍스트가 비어 있음
    """

    user_message = "음성을 인식하지 못했습니다. 다시 한 번 말씀해 주세요."


class LLMParsingError(PipelineError):
    """
    사용자 발화를 JSON 구조로 분석하는 과정에서 발생하는 예외입니다.

    발생 예:
        - OpenAI LLM API 호출 실패
        - JSON 파싱 실패
        - LLM 응답이 비어 있음
    """

    user_message = "요청 내용을 분석하지 못했습니다. 목적지나 버스 번호를 다시 말씀해 주세요."


class ValidationFailedError(PipelineError):
    """
    LLM 분석 결과가 서비스에서 처리하기 어려운 형태일 때 발생하는 예외입니다.

    발생 예:
        - 목적지가 없음
        - 버스 번호가 없음
        - confidence가 너무 낮음
    """

    user_message = "요청 내용이 불명확합니다. 다시 말씀해 주세요."


class TransportAPIError(PipelineError):
    """
    ODsay, Kakao, 공공데이터 API 조회 과정에서 발생하는 예외입니다.

    발생 예:
        - API 키 없음
        - 외부 API 응답 오류
        - 네트워크 오류
        - 교통 경로 조회 실패
    """

    user_message = "교통 정보를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요."


class CoordinateResolveError(TransportAPIError):
    """
    목적지명을 좌표로 변환하지 못했을 때 발생하는 예외입니다.

    발생 예:
        - Kakao Local API 검색 결과 없음
        - 지원하지 않는 목적지명 입력
        - 좌표가 대한민국 서비스 범위를 벗어남
    """

    user_message = "목적지 위치를 찾지 못했습니다. 더 정확한 장소명을 말씀해 주세요."