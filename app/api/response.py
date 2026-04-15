# 응답 데이터 구조 정의 (문서화 및 타입 명시용)

from pydantic import BaseModel
from typing import Optional


class ResponseData(BaseModel):
    destination: Optional[str]
    bus_number: Optional[str]
    arrival_time: Optional[str]
    confidence: Optional[float]


class VoiceResponse(BaseModel):
    status: str
    message: str
    data: Optional[ResponseData]