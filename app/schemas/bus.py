"""Schemas for bus arrival APIs."""

from pydantic import BaseModel, Field


class DefaultBusArrivalItem(BaseModel):
    bus_number: str
    direction: str
    first_arrival_min: int | None = None
    second_arrival_min: int | None = None
    message: str


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
