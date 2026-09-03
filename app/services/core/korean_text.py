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


# 키오스크 앞 이용자가 자기가 선 정류장을 가리키는 말입니다. 이 말들은 정류장
# "이름"이 아니라 "여기"라는 뜻이므로, 이름으로 검색하면 반드시 실패합니다.
# 기기는 자기 정류장(DEFAULT_BUS_STATION_ID)을 알고 있으므로 그쪽으로 보냅니다.
_CURRENT_STOP_WORDS = frozenset({
    "여기", "여기요", "여기서", "여기예요", "이곳", "이 곳",
    "이정류장", "이 정류장", "이정류소", "이 정류소",
    "현재정류장", "현재 정류장", "지금정류장", "지금 정류장",
    "우리정류장", "우리 정류장",
})

# 이용자는 "올림픽공원 정류소에서"처럼 보통명사를 붙여 말합니다. 서울 정류소
# 이름에는 이 낱말이 들어가지 않으므로(노선 네 개 406개 확인) 이름 매칭에
# 실패했을 때만 떼어 다시 맞춰 봅니다.
_TRAILING_STOP_NOUN = re.compile(r"\s*(?:버스)?\s*(?:정류장|정류소)$")


def is_current_stop_reference(value: str | None) -> bool:
    """`여기`, `이 정류장`처럼 기기가 선 정류장을 가리키는 말인지 봅니다."""
    if not value:
        return False
    stripped = " ".join(value.strip().split())
    return stripped in _CURRENT_STOP_WORDS


def strip_stop_noun(value: str) -> str:
    """이름 뒤에 붙은 `정류장`·`정류소` 보통명사만 떼어 냅니다."""
    stripped = " ".join(value.strip().split())
    without_noun = _TRAILING_STOP_NOUN.sub("", stripped).strip()
    # 낱말만 말한 경우("정류장")까지 빈 문자열로 만들지 않습니다.
    return without_noun or stripped
