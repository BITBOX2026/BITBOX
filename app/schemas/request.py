# 요청 데이터 구조 정의 (현재는 파일 업로드 방식이라 실제 사용은 없음)
# 삭제 예정 

from pydantic import BaseModel


class VoiceRequest(BaseModel):
    filename: str