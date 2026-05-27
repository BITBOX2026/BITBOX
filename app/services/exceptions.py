class PipelineError(Exception):
    user_message = "요청을 처리하지 못했습니다. 다시 말씀해 주세요."


class STTProcessingError(PipelineError):
    user_message = "음성을 인식하지 못했습니다. 다시 한 번 말씀해 주세요."


class LLMParsingError(PipelineError):
    user_message = "요청 내용을 분석하지 못했습니다. 목적지나 버스 번호를 다시 말씀해 주세요."


class TransportAPIError(PipelineError):
    user_message = "교통 정보를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요."


class CoordinateResolveError(TransportAPIError):
    user_message = "목적지 위치를 찾지 못했습니다. 더 정확한 장소명을 말씀해 주세요."