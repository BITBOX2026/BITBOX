"""테스트가 실제 외부 API를 호출하지 못하게 막습니다.

왜 필요한가
-----------
이 저장소의 테스트는 각자 경계에서 개별적으로 mock 합니다. 그래서 새 테스트가
파이프라인 전체를 호출하는 순간, 개발 PC 의 ``.env`` (실제 키 + ``USE_MOCK_EXTERNALS=false``)
가 그대로 적용되어 **유료 API 가 실제로 호출됩니다.**

이 실수는 CI 에서는 절대 드러나지 않습니다. GitHub 러너에는 키가 없어 각 서비스가
조용히 ``None`` 을 반환하거나 설정 오류를 던지기 때문입니다. 즉 "CI 녹색"이
"외부 호출 없음"을 보장하지 않습니다. ODsay 는 하루 30회뿐이라 이런 사고 한 번이
그날의 시연 예산을 깎습니다.

무엇을 하는가
-------------
세션 전체에서 제공자 키를 비워, 로컬 실행을 CI 러너와 동일한 상태로 맞춥니다.
키가 없으면 각 서비스는 HTTP 를 시작하기 전에 되돌아갑니다.

- ``generate_tts_audio``  → ``None`` 반환 (네트워크 없음)
- ``transcribe_audio``    → ``STTProcessingError``
- ``parse_transit_intent``→ ``LLMParsingError``
- Kakao / ODsay / 공공데이터 → 설정 오류로 조기 종료

개별 테스트가 ``monkeypatch.setattr(settings, ...)`` 로 키를 다시 넣는 것은 그대로
동작합니다(함수 종료 시 자동 복원). 진짜로 살아 있는 API 를 쓰고 싶다면
``BITBOX_ALLOW_LIVE_API_TESTS=1`` 을 명시적으로 설정해야 합니다.
"""

import os

import pytest

from app.core import config

# 값이 있으면 실제 외부 호출로 이어질 수 있는 설정들입니다.
_PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "KAKAO_REST_API_KEY",
    "ODSAY_API_KEY",
    "PUBLIC_DATA_SERVICE_KEY",
    "SEOUL_BUS_API_KEY",
)

_LIVE_OPT_IN = "BITBOX_ALLOW_LIVE_API_TESTS"


@pytest.fixture(scope="session", autouse=True)
def keep_the_test_suite_offline() -> None:
    """제공자 키를 세션 내내 비워 둡니다 (명시적 opt-in 이 없는 한)."""
    if os.getenv(_LIVE_OPT_IN, "").strip().lower() in {"1", "true", "yes", "on"}:
        # 실제 호출을 의도한 경우에만 통과시킵니다. 사고로 켜지지 않도록
        # 환경변수 이름을 길게 두고, 켜졌다는 사실을 반드시 출력합니다.
        print(f"\n[conftest] {_LIVE_OPT_IN} 가 설정되어 실제 외부 API 호출이 허용됩니다.")
        yield
        return

    with pytest.MonkeyPatch.context() as patch:
        for name in _PROVIDER_KEYS:
            # os.environ 이 pydantic settings 보다 우선하므로 둘 다 비웁니다.
            patch.delenv(name, raising=False)
            patch.setattr(config.settings, name, None, raising=False)
        yield
