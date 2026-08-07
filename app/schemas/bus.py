"""Schemas for bus arrival APIs."""

from pydantic import BaseModel, Field


class DefaultBusArrivalItem(BaseModel):
    bus_number: str
    direction: str
    first_arrival_min: int | None = None
    second_arrival_min: int | None = None
    message: str
    # Seoul Open API 원본 값 — 변환 과정에서 손실되지 않도록 보존
    raw_arrmsg1: str | None = None       # 도착 메시지 "[N번째전]" 포함
    raw_arrmsg2: str | None = None
    raw_congestion1: str | None = None   # 혼잡도 (3=여유, 4=보통, 5=혼잡)
    raw_congestion2: str | None = None
    raw_is_last1: str | None = None      # 막차여부 (1=막차)
    raw_is_last2: str | None = None
    raw_bus_type1: str | None = None     # 버스 종류 (0=일반, 1=저상, 3=간선급행 등)
    raw_bus_type2: str | None = None
    raw_is_full_flag1: str | None = None # 만원여부 (1=만원)
    raw_is_full_flag2: str | None = None
    raw_station_nm1: str | None = None   # 현재 버스 위치 정류소명
    raw_station_nm2: str | None = None
    raw_veh_id1: str | None = None       # 차량 고유 ID
    raw_veh_id2: str | None = None


class DefaultBusArrivalResponse(BaseModel):
    success: bool
    station_name: str | None = None
    station_id: str | None = None
    items: list[DefaultBusArrivalItem] = Field(default_factory=list)
    message: str


class SeoulStationArrivalItem(BaseModel):
    busRouteId: str
    rtNm: str
    vehId1: str = "1"
    traTime1: str = "0"
    busType1: str = "0"
    isLast1: str = "0"
    isFullFlag1: str = "0"
    congestion1: str = "3"
    arrmsg1: str
    stationNm1: str
    vehId2: str = "2"
    traTime2: str = "0"
    busType2: str = "0"
    isLast2: str = "0"
    isFullFlag2: str = "0"
    congestion2: str = "3"
    arrmsg2: str
    stationNm2: str


class SeoulStationMsgHeader(BaseModel):
    headerCd: str
    headerMsg: str


class SeoulStationMsgBody(BaseModel):
    itemList: list[SeoulStationArrivalItem] = Field(default_factory=list)


class SeoulStationArrivalResponse(BaseModel):
    comMsgHeader: dict[str, object] = Field(default_factory=dict)
    msgHeader: SeoulStationMsgHeader
    msgBody: SeoulStationMsgBody = Field(default_factory=SeoulStationMsgBody)
