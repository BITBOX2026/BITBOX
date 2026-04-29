# 서비스 계층에서 공통으로 사용하는 상수값을 관리하는 파일입니다.

# LLM 분석 결과를 신뢰할 수 있는 최소 confidence 기준값입니다.
MIN_CONFIDENCE = 0.5

# OpenAI 기본 모델명입니다.
DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_LLM_MODEL = "gpt-4o-mini"

# ODsay 대중교통 길찾기 API 엔드포인트입니다.
ODSAY_ROUTE_URL = "https://api.odsay.com/v1/api/searchPubTransPathT"

# Kakao Local 키워드 검색 API 엔드포인트입니다.
KAKAO_KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

# 대한민국 서비스 범위 기준 좌표 검증값입니다.
# ODsay 기준 X는 경도, Y는 위도입니다.
KOREA_LONGITUDE_MIN = 124.0
KOREA_LONGITUDE_MAX = 132.0
KOREA_LATITUDE_MIN = 33.0
KOREA_LATITUDE_MAX = 39.5

# 개발 테스트용 목적지 좌표입니다.
# 실제 서비스에서는 Kakao Local API 검색 결과를 우선 활용할 수 있습니다.
KNOWN_DESTINATION_COORDS = {
    "강남역": (127.027610, 37.497942),
    "서울역": (126.970626, 37.554678),
    "시청역": (126.977088, 37.565703),
    "잠실역": (127.100159, 37.513261),
    "홍대입구역": (126.923708, 37.557192),
}

# LLM에게 전달할 시스템 프롬프트입니다.
TRANSIT_INTENT_SYSTEM_PROMPT = """
너는 교통 안내 시스템의 발화 분석기다.

중요 규칙:
- 너는 사용자에게 직접 답변하지 않는다.
- 반드시 정해진 JSON 구조로만 분석 결과를 반환한다.
- 사용자가 목적지를 말하면 destination_text에 넣는다.
- 사용자가 버스 번호를 말하면 bus_number에 넣는다.
- 목적지까지 가는 방법을 묻는 요청이면 intent는 "route"다.
- 특정 버스가 언제 오는지 묻는 요청이면 intent는 "arrival"이다.
- 의미를 알 수 없으면 intent는 "unknown"이다.
- confidence는 0.0 이상 1.0 이하 숫자다.
"""