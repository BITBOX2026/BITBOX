"""보수적인 한국어 장소·정류장 입력 정규화 도우미."""

import re

# `구로`, `종로`, `대학로` 같은 실제 지명을 훼손하지 않도록 장소 본문이 명확히
# `역`(선명 포함)으로 끝날 때만 이동 조사·명령을 제거합니다.
_TYPED_STATION_DESTINATION = re.compile(
    r"^(?P<place>.+?역(?:\s+[0-9A-Za-z가-힣]+선)?)"
    r"(?:\s*(?:에|으로|로|까지)(?:\s*(?:가자|가줘|가주세요))?"
    r"|\s+(?:가자|가줘|가주세요))$"
)

# 도착 안내에서 LLM이 조사를 남기는 경우만 보정합니다. 일반 지명의 마지막 음절을
# 조사로 추측해 자르지 않고, 명확한 정류장 표지어 뒤의 `에/에서`만 제거합니다.
_STATION_REFERENCE = re.compile(
    r"^(?P<place>.+?(?:역|정류장|정류소))(?:에|에서)$"
)


def normalize_typed_destination(value: str) -> str:
    """직접 입력한 역 목적지 뒤의 명확한 이동 표현만 제거합니다."""
    stripped = " ".join(value.strip().split())
    match = _TYPED_STATION_DESTINATION.fullmatch(stripped)
    return match.group("place") if match else stripped


def normalize_station_reference(value: str) -> str:
    """도착 요청의 역·정류장 이름 뒤에 남은 위치 조사만 제거합니다."""
    stripped = " ".join(value.strip().split())
    match = _STATION_REFERENCE.fullmatch(stripped)
    return match.group("place") if match else stripped
