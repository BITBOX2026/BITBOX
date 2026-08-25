"""GitHub Actions 워크플로 정의가 실행 가능한 형태인지 확인합니다.

워크플로는 푸시해 봐야 유효성을 알 수 있고, 잘못되면 잡(job) 하나 없이
startup failure 로 죽습니다. 배포 워크플로가 이렇게 죽으면 "테스트는 다 녹색인데
배포만 안 되는" 상태가 되므로, 사람이 알아채기 전에 여기서 막습니다.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML is required to validate workflow files")

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
WORKFLOW_FILES = sorted(WORKFLOW_DIR.glob("*.yml"))

# `secrets` 컨텍스트를 쓸 수 있는 곳은 env / with / jobs.<id>.secrets 뿐입니다.
# `if:` 에서 참조하면 표현식 평가가 실패해 워크플로 전체가 기동하지 못합니다.
CONTEXTS_FORBIDDEN_IN_IF = ("secrets.",)


def _iter_conditions(document: dict):
    for job_name, job in (document.get("jobs") or {}).items():
        if "if" in job:
            yield f"job[{job_name}]", str(job["if"])
        for index, step in enumerate(job.get("steps") or []):
            if "if" in step:
                label = step.get("name") or f"step #{index}"
                yield f"job[{job_name}].{label}", str(step["if"])


def test_workflow_directory_is_not_empty() -> None:
    assert WORKFLOW_FILES, "no workflow files found"


@pytest.mark.parametrize("workflow", WORKFLOW_FILES, ids=lambda path: path.name)
def test_workflow_is_parseable(workflow: Path) -> None:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{workflow.name} is not a mapping"
    assert document.get("jobs"), f"{workflow.name} defines no jobs"


@pytest.mark.parametrize("workflow", WORKFLOW_FILES, ids=lambda path: path.name)
def test_conditions_do_not_use_unavailable_contexts(workflow: Path) -> None:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    offenders = [
        f"{location}: {condition}"
        for location, condition in _iter_conditions(document)
        for forbidden in CONTEXTS_FORBIDDEN_IN_IF
        if forbidden in condition
    ]
    assert not offenders, (
        f"{workflow.name}: `secrets` is not available in an `if:` condition and makes the "
        f"whole workflow fail to start. Read it through `env:` instead. Offenders: {offenders}"
    )


def test_deployment_only_triggers_on_the_deployment_branch() -> None:
    """배포가 다른 브랜치 푸시로 일어나지 않는지 고정합니다."""
    document = yaml.safe_load((WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8"))
    # PyYAML 은 언쿼트된 `on:` 을 불리언 True 로 읽습니다.
    triggers = document.get("on") or document.get(True)
    assert triggers["push"]["branches"] == ["merge-frontend-backend"]


def test_pull_requests_run_the_full_quality_gate() -> None:
    document = yaml.safe_load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"))
    triggers = document.get("on") or document.get(True)
    assert "pull_request" in triggers
    commands = "\n".join(
        str(step.get("run") or "")
        for job in document["jobs"].values()
        for step in job.get("steps", [])
    )
    for required in ("pytest", "ruff", "bandit", "pip_audit", "typecheck", "npm test", "npm run build", "npm run e2e"):
        assert required in commands


def test_public_verification_failure_has_a_guarded_rollback() -> None:
    workflow = (WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8")
    assert "/etc/bitbox/deployment_in_progress" in workflow
    assert "Roll back a release that failed public verification" in workflow
    assert "Send deployment success alert" in workflow
    assert "/usr/local/sbin/bitbox-healthcheck" in workflow
    assert "--test-alert" in workflow
    assert '[[ "$marker" == "$RELEASE_SHA" ]] || exit 0' in workflow
    assert "previous_release_dir" in workflow
