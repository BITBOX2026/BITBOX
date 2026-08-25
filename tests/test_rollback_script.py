"""배포 롤백 스크립트가 실제로 동작하는지 실행해서 확인합니다.

롤백은 배포 실패 시에만 도는 경로라 검증하지 않으면 정작 필요한 순간에 처음
실행됩니다. deploy/rollback_test.sh 가 systemctl·curl·pip 를 대체하고 임시
저장소를 만들어 스크립트를 실제로 실행하므로, 여기서는 그 하네스를 호출하고
결과만 확인합니다.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "deploy" / "rollback_test.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to run the rollback harness")
@pytest.mark.skipif(shutil.which("git") is None, reason="git is required to run the rollback harness")
def test_rollback_script_restores_the_previous_release() -> None:
    # check=False: 종료코드는 아래에서 출력과 함께 직접 판정합니다.
    result = subprocess.run(
        [shutil.which("bash"), str(HARNESS)],
        capture_output=True,
        timeout=300,
        cwd=str(REPO_ROOT),
        check=False,
    )
    # 하네스는 한국어로 결과를 출력합니다. Windows 기본 코드페이지(cp949)로 디코딩하면
    # 실패하므로 UTF-8 을 명시합니다.
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert "실패 0" in output, output
    assert result.returncode == 0, output
