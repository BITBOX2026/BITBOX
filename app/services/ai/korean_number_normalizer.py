"""음성 인식 결과에 섞인 숫자·한국어 수사를 버스 번호로 정규화합니다."""

import re

_NATIVE_TENS = {
    "열": 10,
    "스물": 20,
    "스무": 20,
    "서른": 30,
    "마흔": 40,
    "쉰": 50,
    "예순": 60,
    "일흔": 70,
    "여든": 80,
    "아흔": 90,
}
_NATIVE_ONES = {
    "하나": 1, "한": 1,
    "둘": 2, "두": 2,
    "셋": 3, "세": 3,
    "넷": 4, "네": 4,
    "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9,
}
_SINO_DIGITS = {
    "영": "0", "공": "0", "일": "1", "이": "2", "삼": "3",
    "사": "4", "오": "5", "육": "6", "칠": "7", "팔": "8", "구": "9",
}
_SINO_UNITS = {"십": 10, "백": 100, "천": 1000}
_NUMBER_WORDS = sorted(
    {*_NATIVE_TENS, *_NATIVE_ONES, *_SINO_DIGITS, *_SINO_UNITS}, key=len, reverse=True
)
_WORD_PATTERN = "|".join(map(re.escape, _NUMBER_WORDS))
_MIXED_BUS_PATTERN = re.compile(
    rf"(?P<digits>\d{{1,4}})\s*(?P<words>(?:{_WORD_PATTERN}){{1,2}})\s*번"
)
_PURE_BUS_PATTERN = re.compile(
    rf"(?P<words>(?:{_WORD_PATTERN}){{1,8}})\s*번"
)


_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def strip_thousands_separators(text: str) -> str:
    """STT가 붙인 천 단위 쉼표만 제거합니다.

    실제 STT는 "삼천사백십삼번"을 `3,413번`으로 받아쓰는 경우가 있습니다.
    이때 쉼표를 지우지 않으면 버스 번호 추출 정규식이 뒤쪽 `413`만 잡아
    전혀 다른 노선을 조회하게 됩니다.

    쉼표 뒤에 정확히 세 자리 숫자가 이어질 때만 지우므로 "3, 4번"처럼
    나열을 뜻하는 쉼표는 보존됩니다.
    """
    return _THOUSANDS_SEPARATOR.sub("", text)


def parse_korean_number(words: str) -> int | None:
    """고유어 1~99 또는 한자어 숫자 나열을 정수로 변환합니다."""
    compact = re.sub(r"\s+", "", words)
    if not compact:
        return None

    for tens_word, tens_value in sorted(_NATIVE_TENS.items(), key=lambda item: -len(item[0])):
        if not compact.startswith(tens_word):
            continue
        remainder = compact[len(tens_word):]
        if not remainder:
            return tens_value
        one = _NATIVE_ONES.get(remainder)
        return tens_value + one if one is not None else None

    if compact in _NATIVE_ONES:
        return _NATIVE_ONES[compact]

    if all(char in _SINO_DIGITS for char in compact):
        return int("".join(_SINO_DIGITS[char] for char in compact))
    if all(char in _SINO_DIGITS or char in _SINO_UNITS for char in compact):
        total = 0
        pending_digit = 0
        last_unit = 10_000
        for char in compact:
            if char in _SINO_DIGITS:
                pending_digit = int(_SINO_DIGITS[char])
                continue
            unit = _SINO_UNITS[char]
            if unit >= last_unit:
                return None
            total += (pending_digit or 1) * unit
            pending_digit = 0
            last_unit = unit
        return total + pending_digit
    return None


def _merge_digit_prefix(digits: str, suffix: int) -> str | None:
    """STT의 `3400 열두`를 `3412`처럼 안전하게 합칩니다."""
    if suffix < 0 or suffix > 99:
        return None
    if len(digits) == 4 and digits.endswith("00"):
        return str(int(digits) + suffix)
    suffix_text = str(suffix)
    if len(digits) + len(suffix_text) <= 4:
        return f"{digits}{suffix_text}"
    return None


def normalize_bus_number_token(value: str | None) -> str | None:
    """이미 버스 번호로 식별된 토큰만 숫자로 정규화합니다.

    문장 전체를 훑는 :func:`normalize_spoken_bus_numbers` 와 달리, 이 함수는
    LLM 등이 "이 값은 버스 번호"라고 판단한 토큰에만 적용합니다. 따라서
    "이 버스" 같은 일반 발화를 잘못 변환할 위험 없이 `번` 접미사가 빠진
    "삼사이삼" 형태를 3423 으로 복구할 수 있습니다.

    변환할 수 없는 값(`3사리`, `30-5하남`, `N13` 등)은 그대로 돌려줍니다.
    """
    if value is None:
        return None
    token = strip_thousands_separators(value.strip())
    if not token or token.isdigit():
        return token

    # LLM이 "삼사이삼번"처럼 접미사를 붙여 돌려주는 경우를 함께 처리합니다.
    candidate = token[:-1].strip() if token.endswith("번") and len(token) > 1 else token
    if candidate.isdigit():
        return candidate

    parsed = parse_korean_number(candidate)
    if parsed is not None and 0 < parsed <= 9999:
        return str(parsed)

    # "3400 열두"처럼 숫자 뒤에 수사가 붙은 혼합 표기도 복구합니다.
    # 숫자가 섞인 나머지(`30-5하남`)나 수사가 아닌 글자(`3사리`)는 매칭되지 않습니다.
    mixed = re.fullmatch(r"(?P<digits>\d{1,4})\s*(?P<words>\D+)", candidate)
    if mixed:
        suffix = parse_korean_number(mixed.group("words"))
        if suffix is not None:
            merged = _merge_digit_prefix(mixed.group("digits"), suffix)
            if merged:
                return merged
    return token


def normalize_spoken_bus_numbers(text: str) -> str:
    """문장 안의 혼합 표기 버스 번호만 치환하고 나머지 발화는 보존합니다."""
    def replace(match: re.Match[str]) -> str:
        suffix = parse_korean_number(match.group("words"))
        merged = _merge_digit_prefix(match.group("digits"), suffix) if suffix is not None else None
        return f"{merged}번" if merged else match.group(0)

    normalized = _MIXED_BUS_PATTERN.sub(replace, strip_thousands_separators(text))

    def replace_pure(match: re.Match[str]) -> str:
        value = parse_korean_number(match.group("words"))
        return f"{value}번" if value is not None and 0 < value <= 9999 else match.group(0)

    return _PURE_BUS_PATTERN.sub(replace_pure, normalized)
