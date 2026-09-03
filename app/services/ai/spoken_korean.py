"""화면 문구를 한국어 교통 안내에 맞는 TTS 입력으로 바꿉니다.

프론트의 브라우저 음성뿐 아니라 음성 업로드 파이프라인이 미리 생성하는 서버
오디오에도 같은 규칙이 적용되어야 합니다. 이 모듈은 TTS 경계에서 마지막으로 한 번
더 정규화하며, 이미 변환된 한글 문장은 그대로 두므로 중복 적용해도 안전합니다.
"""

from __future__ import annotations

import re

_HANGUL_DIGITS = ("공", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")
_HANGUL_LETTERS = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔",
    "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유",
    "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "지",
}
_BUS_NUMBER = re.compile(r"(^|[^0-9A-Za-z가-힣])([A-Za-z]?\d[0-9A-Za-z-]*[가-힣]{0,6})번")
_PART = re.compile(r"[A-Za-z]+|\d+|-|[가-힣]+")
_NON_BUS_CONTEXT = re.compile(r"^(?:출구|승강장|게이트|좌석|플랫폼|문항|항목)")
# `타/이용` 을 함께 봅니다. 안내 문구에는 "…에서 5번을 이용하시면" 형태가 있는데
# `타` 만 보면 한두 자리 노선이 문맥을 잃어 자릿수로 읽히지 않았습니다. `출구`·`승강장`
# 같은 시설 번호는 _NON_BUS_CONTEXT 가 먼저 걸러내므로 안전합니다.
_SHORT_BUS_CONTEXT = re.compile(
    r"^(?:버스|노선|마을버스|탑승|승차|하차|(?:을|를)?\s*(?:타|이용)|"
    r"(?:에서|으로)\s*.*갈아타|(?:이|가|은|는)?\s*(?:곧|도착|출발|운행))"
)


def spell_digits(digits: str) -> str:
    """숫자를 자릿수 그대로 읽습니다. ``3412`` -> ``삼사일이``."""
    return "".join(_HANGUL_DIGITS[int(digit)] if digit.isdigit() else digit for digit in digits)


def spell_bus_number(bus_number: str) -> str:
    """영문 접두·가지번호·지역 접미가 섞인 노선 식별자를 읽습니다."""
    spoken: list[str] = []
    for part in _PART.findall(bus_number):
        if part.isdigit():
            spoken.append(spell_digits(part))
        elif part == "-":
            # 서울시가 버스정보안내단말기 음성안내에서 `-` 발음을 "다시"에서
            # "대시"로 바로잡았습니다. 정류장 방송과 이 서비스가 다르게 읽으면
            # 이용자는 같은 노선을 다른 번호로 듣습니다.
            # 근거: 서울시 「버스정보 안내 단말기 개선」
            #       news.seoul.go.kr/traffic/archives/514398
            spoken.append("대시")
        elif part.isascii() and part.isalpha():
            spoken.append(" ".join(_HANGUL_LETTERS.get(letter, letter) for letter in part.upper()))
        else:
            spoken.append(part)
    return " ".join(spoken)


def _is_likely_bus_number(identifier: str, following_text: str) -> bool:
    context = following_text.lstrip()
    if _NON_BUS_CONTEXT.match(context):
        return False
    digits = re.sub(r"\D", "", identifier)
    has_route_marker = bool(re.search(r"[A-Za-z가-힣-]", identifier)) or len(digits) >= 3
    return has_route_marker or bool(_SHORT_BUS_CONTEXT.match(context))


def to_spoken_korean(text: str) -> str:
    """노선번호만 자릿수 읽기로 바꾸고 출구·요금·시간 숫자는 보존합니다."""

    def replace(match: re.Match[str]) -> str:
        prefix, route_number = match.group(1), match.group(2)
        if not _is_likely_bus_number(route_number, text[match.end():]):
            return match.group(0)
        return f"{prefix}{spell_bus_number(route_number)} 번"

    return _BUS_NUMBER.sub(replace, text)
