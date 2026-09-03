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

# `여기서`, `이곳에서` 처럼 지시어 뒤에 바로 붙는 조사입니다. 장소 이름이 아니라
# 지시어일 때만 떼므로 `구로`·`종로` 같은 지명은 건드리지 않습니다.
_DEICTIC_PARTICLE = re.compile(r"^(?P<word>여기|이곳|현재|지금|우리)(?:서|에서|에)$")


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
})

# `정류장`·`정류소` 를 떼고 나면 앞에 남는 지시어들입니다. 보통명사가 실제로 붙어
# 있었을 때만 이 집합으로 판단하므로, `올림픽공원 정류장` 의 `올림픽공원` 이나
# `구로` 같은 지명이 여기 걸릴 일은 없습니다.
_CURRENT_STOP_DETERMINERS = frozenset({
    "이", "그", "여기", "이곳", "현재", "지금", "우리",
})

# 이용자는 "올림픽공원 정류소에서"처럼 보통명사를 붙여 말합니다. 서울 정류소
# 이름에는 이 낱말이 들어가지 않으므로(노선 네 개 406개 확인) 이름 매칭에
# 실패했을 때만 떼어 다시 맞춰 봅니다.
_TRAILING_STOP_NOUN = re.compile(r"\s*(?:버스)?\s*(?:정류장|정류소)$")


def is_current_stop_reference(value: str | None) -> bool:
    """`여기`, `이 정류장에서`처럼 기기가 선 정류장을 가리키는 말인지 봅니다.

    LLM 이 돌려주는 형태가 한 가지가 아닙니다. `여기`, `여기 정류장`,
    `이 정류장에서`, `현재 정류소` 가 모두 나올 수 있어, 낱말 목록만 두면 그중
    하나만 어긋나도 이름으로 검색하다 실패합니다. 위치 조사와 `정류장`·`정류소`
    보통명사를 먼저 떼고 나서 맞춰 봅니다.
    """
    if not value:
        return False
    stripped = " ".join(value.strip().split())
    if stripped in _CURRENT_STOP_WORDS:
        return True

    # `여기서` 처럼 지시어에 조사가 바로 붙은 형태를 먼저 되돌립니다.
    reduced = normalize_station_reference(stripped)
    deictic = _DEICTIC_PARTICLE.fullmatch(reduced)
    if deictic:
        reduced = deictic.group("word")
    if reduced in _CURRENT_STOP_WORDS:
        return True

    # `이 정류장에서` → `이 정류장` → `이`. 보통명사가 실제로 붙어 있었을 때만
    # 지시어로 판단합니다. 그래야 `올림픽공원 정류장` 이 지시어로 오인되지 않습니다.
    without_noun = strip_stop_noun(reduced)
    if without_noun == reduced:
        return False
    return without_noun in _CURRENT_STOP_DETERMINERS


def strip_stop_noun(value: str) -> str:
    """이름 뒤에 붙은 `정류장`·`정류소` 보통명사만 떼어 냅니다."""
    stripped = " ".join(value.strip().split())
    without_noun = _TRAILING_STOP_NOUN.sub("", stripped).strip()
    # 낱말만 말한 경우("정류장")까지 빈 문자열로 만들지 않습니다.
    return without_noun or stripped
