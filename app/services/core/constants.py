# LLM 분석 결과를 신뢰할 수 있는 최소 confidence 기준값입니다.
MIN_CONFIDENCE = 0.5

# OpenAI 기본 모델명입니다.
DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_LLM_MODEL = "gpt-4o-mini"
DEFAULT_TTS_MODEL = "tts-1-hd"
DEFAULT_TTS_VOICE = "nova"

# 외부 교통/지도 API 엔드포인트입니다.
ODSAY_ROUTE_URL = "https://api.odsay.com/v1/api/searchPubTransPathT"
KAKAO_KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
SEOUL_BUS_ROUTE_SEARCH_URL = "http://ws.bus.go.kr/api/rest/busRouteInfo/getBusRouteList"
SEOUL_STATION_SEARCH_URL = "http://ws.bus.go.kr/api/rest/stationinfo/getStationByName"
SEOUL_STATION_ARRIVAL_URL = "http://ws.bus.go.kr/api/rest/stationinfo/getStationByUid"
SEOUL_ROUTE_STATION_URL = "http://ws.bus.go.kr/api/rest/busRouteInfo/getStaionByRoute"
SEOUL_BUS_ARRIVAL_URL = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRoute"

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

# ODsay API가 반환하는 지하철 노선 코드 → 한국어 노선명 매핑입니다.
SUBWAY_LINE_NAMES: dict[int, str] = {
    1: "1호선", 2: "2호선", 3: "3호선", 4: "4호선",
    5: "5호선", 6: "6호선", 7: "7호선", 8: "8호선", 9: "9호선",
    21: "인천1호선", 22: "인천2호선",
    31: "대전1호선", 41: "대구1호선", 51: "광주1호선",
    101: "공항철도", 104: "경의중앙선", 107: "수인분당선",
    108: "경춘선", 109: "신분당선", 110: "우이신설선",
    112: "서해선", 113: "경강선",
}

TRANSIT_INTENT_SYSTEM_PROMPT = """
너는 교통 안내 시스템의 발화 분석기다.

중요 규칙:
- 사용자의 질문에 직접 답하지 않는다.
- 반드시 정해진 JSON 구조로만 분석 결과를 반환한다.
- 사용자가 출발지를 말하면 origin_text에 넣는다.
- 사용자가 목적지를 말하면 destination_text에 넣는다.
- 사용자가 특정 버스 도착 정보를 묻고 정류장명이나 기준 위치를 말하면 stop_text에 넣는다.
- 사용자가 요청한 이동 수단을 transport_mode에 넣는다.
  가능한 값은 "bus", "subway", "transit", "unknown"뿐이다.
- "버스"를 요청하면 transport_mode는 "bus"다.
- "지하철"을 요청하면 transport_mode는 "subway"다.
- 특정 수단 없이 대중교통 경로를 묻는 요청이면 transport_mode는 "transit"다.
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
- 실제 교통 정보는 Kakao/ODsay/공공데이터 API가 조회하므로 이 단계에서는 발화 구조화만 한다.
"""
