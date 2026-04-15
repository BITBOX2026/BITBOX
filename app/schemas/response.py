# API 응답 형식을 통일하는 유틸 함수

from fastapi.responses import JSONResponse


def success_response(data: dict):
    return {
        "status": "success",
        "message": data.get("message", ""),
        "data": {
            "destination": data.get("destination", ""),
            "bus_number": data.get("bus", ""),
            "arrival_time": data.get("arrival_time", ""),
            "confidence": data.get("confidence", 0.0)
        }
    }


def error_response(message: str, status_code: int):
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "message": message
        }
    )