# 요청 처리 및 pipeline 호출 + fallback(mock) 포함

from fastapi import APIRouter, UploadFile, File, HTTPException
from app.api.response import success_response, error_response
from app.core.logger import logger
from services.pipeline import run_pipeline

router = APIRouter()


@router.post("/process")
async def process_audio(file: UploadFile = File(...)):
    try:
        # 1. 파일 검증
        if not file.content_type or not file.content_type.startswith("audio"):
            raise HTTPException(status_code=400, detail="audio 파일만 업로드 가능합니다")

        # 2. 파일 읽기
        audio_bytes = await file.read()
        await file.close()

        # 3. pipeline 실행
        try:
            result = await run_pipeline(audio_bytes)
            logger.info("pipeline 성공")

        except Exception as pipeline_error:
            logger.error(f"pipeline 실패: {pipeline_error}")

            # 🔥 fallback (mock)
            result = {
                "message": "임시 응답입니다",
                "destination": "강남역",
                "bus": "테스트",
                "arrival_time": "정보 없음",
                "confidence": 0.0
            }

        return success_response(result)

    except HTTPException as e:
        return error_response(e.detail, e.status_code)

    except Exception as e:
        logger.error(str(e))
        return error_response("서버 내부 오류", 500)