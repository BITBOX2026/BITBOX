# LLM 분석 결과를 신뢰할 수 있는 최소 confidence 기준값입니다.
MIN_CONFIDENCE = 0.5

# OpenAI 기본 모델명입니다.
DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_LLM_MODEL = "gpt-4o-mini"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "sage"
DEFAULT_TTS_INSTRUCTIONS = (
    "정류장 안내 방송처럼 말하세요. 어르신이 편하게 알아들을 수 있도록 또박또박, 천천히, 따뜻하고 차분한 목소리로 읽습니다. 기계적으로 끊지 말고 자연스러운 문장 억양을 유지하고, 숫자와 노선 번호는 특히 분명하게 발음하세요."
)

# 외부 교통/지도 API 엔드포인트입니다.
ODSAY_ROUTE_URL = "https://api.odsay.com/v1/api/searchPubTransPathT"
KAKAO_KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
# ws.bus.go.kr은 현재 HTTPS 연결을 제공하지 않아 443 포트에서 타임아웃됩니다.
# 서울시 버스 Open API가 실제로 제공하는 HTTP 엔드포인트를 사용합니다.
SEOUL_BUS_API_BASE_URL = "http://ws.bus.go.kr/api/rest"
SEOUL_BUS_ROUTE_SEARCH_URL = f"{SEOUL_BUS_API_BASE_URL}/busRouteInfo/getBusRouteList"
SEOUL_STATION_SEARCH_URL = f"{SEOUL_BUS_API_BASE_URL}/stationinfo/getStationByName"
SEOUL_STATION_ARRIVAL_URL = f"{SEOUL_BUS_API_BASE_URL}/stationinfo/getStationByUid"
SEOUL_ROUTE_STATION_URL = f"{SEOUL_BUS_API_BASE_URL}/busRouteInfo/getStaionByRoute"
SEOUL_BUS_ARRIVAL_URL = f"{SEOUL_BUS_API_BASE_URL}/arrive/getArrInfoByRoute"

# 대한민국 서비스 범위 기준 좌표 검증값입니다.
# ODsay 기준 X는 경도, Y는 위도입니다.
KOREA_LONGITUDE_MIN = 124.0
KOREA_LONGITUDE_MAX = 132.0
KOREA_LATITUDE_MIN = 33.0
KOREA_LATITUDE_MAX = 39.5

# Kakao Local 조회 실패 시 개발/테스트 보조로 사용할 알려진 장소 좌표입니다.
KNOWN_PLACE_COORDS = {
    "강남역": (127.027610, 37.497942),
    "서울역": (126.970626, 37.554678),
    "시청역": (126.977088, 37.565703),
    "잠실역": (127.100159, 37.513261),
    "홍대입구역": (126.923708, 37.557192),
}

TRANSIT_INTENT_SYSTEM_PROMPT = """
너는 버스 안내 시스템의 발화 분석기다.

중요 규칙:
- 사용자의 질문에 직접 답하지 않는다.
- 반드시 정해진 JSON 구조로만 분석 결과를 반환한다.
- 사용자가 출발지를 말하면 origin_text에 넣는다.
- 사용자가 목적지를 말하면 destination_text에 넣는다.
- 사용자가 특정 버스 도착 정보를 묻고 정류장명이나 기준 위치를 말하면 stop_text에 넣는다.
- 사용자가 요청한 이동 수단을 transport_mode에 넣는다.
  가능한 값은 "bus", "subway", "unknown"뿐이다.
- "버스"를 요청하면 transport_mode는 "bus"다.
- "지하철"을 명시적으로 요청하면 비지원 요청 판별을 위해 transport_mode는 "subway"다.
- 이동 수단을 말하지 않은 경로 요청은 버스 전용 기기이므로 transport_mode는 "bus"다.
- 사용자가 버스 번호를 말하면 bus_number에 넣는다.
- "서울역에서 강남역 가는 버스 알려줘"처럼 출발지와 목적지가 함께 있으면
  origin_text는 "서울역", destination_text는 "강남역", transport_mode는 "bus"다.
- route 요청에서 출발지가 없으면 origin_text는 null로 둔다.
- route 요청에서 목적지가 없으면 destination_text는 null로 둔다.
- 목적지까지 가는 방법을 묻는 요청이면 intent는 "route"다.
- 특정 버스가 언제 오는지 묻는 요청이면 intent는 "arrival"이다.
- "402번 언제 와?"처럼 정류장명이 없으면 stop_text는 null이다.
- "서울역에서 402번 언제 와?"이면 stop_text는 "서울역", bus_number는 "402"다.
- "강남역 정류장에 146번 언제 도착해?"이면 stop_text는 "강남역", bus_number는 "146"이다.
- 의미를 알 수 없으면 intent는 "unknown"이다.
- confidence는 0.0 이상 1.0 이하 숫자다.
- 실제 버스 번호, 운행 시간, 도착 시간, 소요 시간, 요금, 경로 상세는 절대 생성하지 않는다.
- bus_number는 사용자가 직접 말한 번호만 넣고, 추정한 번호는 넣지 않는다.
- M5333, N13 같은 영문 접두와 30-5하남 같은 하이픈·문자 접미는 노선명의 일부다. 접두·하이픈·접미를 삭제하거나 숫자만 반환하지 말고 발화 그대로 보존한다.
- 실제 버스 정보는 Kakao/ODsay/공공데이터 API가 조회하므로 이 단계에서는 발화 구조화만 한다.
"""
