# 요청 처리 + pipeline 호출 + timeout + fallback

from fastapi import APIRouter, UploadFile, File, HTTPException
from app.api.response import success_response, error_response
from app.core.logger import logger
from services.pipeline import run_pipeline

import asyncio
import time

router = APIRouter()


@router.post("/process")
async def process_audio(file: UploadFile = File(...)):
    try:
        # 1. 파일 타입 검증
        if not file.content_type or not file.content_type.startswith("audio"):
            raise HTTPException(status_code=400, detail="audio 파일만 업로드 가능합니다")

        # 2. 파일 → bytes 변환
        audio_bytes = await file.read()
        await file.close()

        # 3. pipeline 실행
        try:
            start = time.time()

            result = await asyncio.wait_for(
                run_pipeline(audio_bytes),
                timeout=10.0
            )

            elapsed = time.time() - start
            logger.info(f"pipeline 성공 | {elapsed:.2f}s")

        except asyncio.TimeoutError:
            logger.error("pipeline 타임아웃")

            result = {
                "message": "응답 시간이 초과되었습니다",
                "destination": "",
                "bus": "",
                "arrival_time": "",
                "confidence": 0.0
            }

        except Exception as e:
            logger.error(f"pipeline 실패: {e}")

            # fallback (디버깅용)
            result = {
                "message": "pipeline 처리 실패",
                "destination": None,
                "bus": None,
                "arrival_time": None,
                "confidence": 0.0
            }

        return success_response(result)

    except HTTPException as e:
        return error_response(e.detail, e.status_code)

    except Exception as e:
        logger.error(str(e))
        return error_response("서버 내부 오류", 500)