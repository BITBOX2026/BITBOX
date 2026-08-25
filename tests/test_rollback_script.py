"""배포 롤백 스크립트가 실제로 동작하는지 실행해서 확인합니다.

롤백은 배포 실패 시에만 도는 경로라 검증하지 않으면 정작 필요한 순간에 처음
실행됩니다. deploy/rollback_test.sh 가 systemctl·curl·pip 를 대체하고 임시
저장소를 만들어 스크립트를 실제로 실행하므로, 여기서는 그 하네스를 호출하고
결과만 확인합니다.
"""

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "deploy" / "rollback_test.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to run the rollback harness")
@pytest.mark.skipif(shutil.which("git") is None, reason="git is required to run the rollback harness")
def test_rollback_script_restores_the_previous_release() -> None:
    bash = str(shutil.which("bash"))
    harness = HARNESS
    command = [bash, str(harness)]

    # Windows의 System32/bash.exe는 WSL 실행기입니다. Windows 경로를 직접 넘기면
    # `C:Users...`로 해석하고, core.autocrlf 작업 트리의 CRLF도 Bash 구문을 깨뜨립니다.
    # 임시 복사본만 LF로 정규화하고 WSL 마운트 경로로 변환해 같은 하네스를 실행합니다.
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if os.name == "nt" and "windows\\system32\\bash.exe" in bash.lower():
        temporary = tempfile.TemporaryDirectory(prefix="bitbox-rollback-")
        temp_dir = Path(temporary.name)
        for source in (HARNESS, REPO_ROOT / "deploy" / "rollback.sh"):
            destination = temp_dir / source.name
            destination.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))

        drive = temp_dir.drive.rstrip(":").lower()
        wsl_dir = f"/mnt/{drive}/{temp_dir.as_posix().split(':', 1)[1].lstrip('/')}"
        command = [bash, "-lc", f"bash {shlex.quote(wsl_dir + '/rollback_test.sh')}"]

    # check=False: 종료코드는 아래에서 출력과 함께 직접 판정합니다.
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=300,
            cwd=str(REPO_ROOT),
            check=False,
        )
    finally:
        if temporary is not None:
            temporary.cleanup()
    # 하네스는 한국어로 결과를 출력합니다. Windows 기본 코드페이지(cp949)로 디코딩하면
    # 실패하므로 UTF-8 을 명시합니다.
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert "실패 0" in output, output
    assert result.returncode == 0, output
