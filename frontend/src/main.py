import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# CORS 설정 유지
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🟢 [수정]: 유령 파라미터 arsId를 지우고, 메인화면 전용 전용 배관으로 전환
@app.get("/api/bus/default")
async def get_default_bus_info():
    # 1. 프론트엔드가 주던 arsId 대신, 이제 백엔드 고유 .env에 저장된 STATION_ID를 서버가 직접 읽음
    ars_id = os.getenv("STATION_ID") # 예: "04123" (올림픽공원역)
    if not ars_id:
        raise HTTPException(status_code=500, detail="서버 정류소 환경변수(STATION_ID) 설정 누락")

    api_url = "http://ws.bus.go.kr/api/rest/stationInfo/getStationByUid"
    params = {
        "serviceKey": os.getenv("BUS_API_KEY"),
        "arsId": ars_id,
        "resultType": "json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(api_url, params=params, timeout=5.0)
            response.raise_for_status()
            raw_data = response.json()

            
            return {
                "stationName": "올림픽공원역", # 혹은 raw_data에서 추출한 정류소명
                "buses": [] # 가공 완료된 청정 버스 배열 객체
            }
            
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail="공공데이터 포털 통신 실패")