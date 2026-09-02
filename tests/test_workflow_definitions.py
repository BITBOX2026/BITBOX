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


def test_quality_gate_e2e_excludes_the_submission_only_spec() -> None:
    """`npm run e2e` 가 제출용 데모 녹화 스펙을 실행하지 않는지 고정합니다.

    live-submission-demo.spec.ts 는 실제 백엔드·가짜 마이크·240초 타임아웃이 있는
    playwright.submission.config.ts 전용입니다. 기본 설정(기본 30초 타임아웃)이
    이 스펙을 함께 잡으면 CI 와 배포의 프론트 단계가 항상 실패합니다.
    """
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    default_config = (frontend / "playwright.config.ts").read_text(encoding="utf-8")
    submission_config = (frontend / "playwright.submission.config.ts").read_text(encoding="utf-8")

    assert (frontend / "e2e" / "live-submission-demo.spec.ts").exists()
    assert 'testIgnore: "live-submission-demo.spec.ts"' in default_config
    assert 'testMatch: "live-submission-demo.spec.ts"' in submission_config


def test_deployment_only_triggers_on_main() -> None:
    """배포가 다른 브랜치 푸시로 일어나지 않는지 고정합니다."""
    document = yaml.safe_load((WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8"))
    # PyYAML 은 언쿼트된 `on:` 을 불리언 True 로 읽습니다.
    triggers = document.get("on") or document.get(True)
    assert triggers["push"]["branches"] == ["main"]


def test_pull_requests_run_the_full_quality_gate() -> None:
    document = yaml.safe_load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"))
    triggers = document.get("on") or document.get(True)
    assert "pull_request" in triggers
    assert triggers["push"]["branches"] == ["main"]
    commands = "\n".join(
        str(step.get("run") or "")
        for job in document["jobs"].values()
        for step in job.get("steps", [])
    )
    for required in ("pytest", "ruff", "bandit", "pip_audit", "typecheck", "npm test", "npm run build", "npm run e2e"):
        assert required in commands


def test_codeql_runs_for_main_pushes() -> None:
    document = yaml.safe_load((WORKFLOW_DIR / "codeql.yml").read_text(encoding="utf-8"))
    triggers = document.get("on") or document.get(True)
    assert triggers["push"]["branches"] == ["main"]


def test_deployment_serializes_so_two_pushes_cannot_interleave() -> None:
    """배포가 겹쳐 돌지 못하게 하고, 진행 중인 배포를 취소하지도 않게 고정합니다."""
    document = yaml.safe_load((WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8"))
    concurrency = document.get("concurrency")
    assert concurrency, "deploy.yml must serialize deployments"
    assert concurrency.get("group"), "deploy concurrency needs a fixed group"
    # 배포를 중간에 취소하면 systemd 재시작·심볼릭 링크 교체가 끊겨
    # 반쯤 적용된 상태가 남습니다. 취소가 아니라 대기여야 합니다.
    assert concurrency.get("cancel-in-progress") is False


def test_ec2_checks_out_the_triggering_commit_not_the_branch_head() -> None:
    """EC2가 트리거 커밋 대신 최신 main 을 받아 프론트·백엔드가 갈라지는 것을 막습니다."""
    workflow = (WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8")
    assert 'git checkout --quiet --force --detach "$RELEASE_SHA"' in workflow
    assert 'git cat-file -e "${RELEASE_SHA}^{commit}"' in workflow
    # 배포가 도는 동안 push 된 커밋을 끌어오는 형태가 되살아나지 않게 막습니다.
    assert "git checkout main" not in workflow
    assert "git pull --ff-only origin main" not in workflow


def test_deployment_reports_how_much_odsay_quota_it_consumed() -> None:
    """하루 30회뿐인 예산이라, 배포가 몇 회를 썼는지 로그에 남아야 합니다."""
    document = yaml.safe_load((WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8"))
    steps = [
        step
        for job in document["jobs"].values()
        for step in job.get("steps", [])
    ]
    usage_step = next(
        (step for step in steps if step.get("name") == "Report today's ODsay call usage"),
        None,
    )
    assert usage_step, "deploy.yml must report ODsay usage after verification"
    # 검증이 실패해 롤백된 배포도 쿼터는 이미 썼으므로 항상 기록해야 합니다.
    assert usage_step.get("if") == "always()"
    # 이 조회가 배포를 실패시켜서는 안 됩니다.
    assert usage_step.get("continue-on-error") is True
    script = str(usage_step.get("with", {}).get("script", ""))
    assert "127.0.0.1:8001/internal/status" in script


def _run_commands(workflow_name: str) -> str:
    document = yaml.safe_load((WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8"))
    return "\n".join(
        str(step.get("run") or "")
        for job in document["jobs"].values()
        for step in job.get("steps", [])
    )


def test_deployment_gate_is_a_superset_of_the_pull_request_gate() -> None:
    """배포가 PR 품질 게이트보다 느슨해지지 않게 고정합니다.

    ci.yml 과 deploy.yml 은 같은 main push 에서 나란히 시작하고 서로를 기다리지
    않습니다. 그래서 deploy.yml 의 검증이 ci.yml 의 부분집합이면, ci 가 빨간불인
    코드가 배포될 수 있습니다. 실제로 ruff 와 compileall 이 배포 쪽에만 빠져
    있었습니다.
    """
    deploy_commands = _run_commands("deploy.yml")
    missing = [
        check
        for check in (
            "git diff --check",
            "python -m pip check",
            "python -m compileall -q app scripts tests",
            "python -m ruff check app scripts tests",
            "python -m pip_audit",
            "python -m bandit",
            "python -m pytest",
            "npm run typecheck",
            "npm run test",
            "npm run build",
            "npm run e2e",
        )
        if check not in deploy_commands
    ]
    assert not missing, (
        "deploy.yml must run every check that ci.yml runs, otherwise a commit that "
        f"fails the PR gate can still deploy. Missing: {missing}"
    )


def test_deployment_verifies_the_live_route_api_unless_explicitly_skipped() -> None:
    """운영 경로 API 검증이 기본값으로 남아 있는지 고정합니다.

    이 검증은 ODsay 를 1회 소비하므로 끄고 싶은 유혹이 있지만, 끄면 키·쿼터가 죽은
    채 배포돼도 배포 시점에 알 수 없습니다. 기본은 켬이고, 끄는 것은 수동 배포에서
    명시적으로 선택할 때뿐이어야 합니다.
    """
    document = yaml.safe_load((WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8"))
    triggers = document.get("on") or document.get(True)
    skip_input = (triggers["workflow_dispatch"] or {})["inputs"]["skip_transit_check"]
    assert skip_input["default"] is False, "ODsay 검증 생략은 기본값이 되면 안 됩니다."

    workflow = (WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8")
    assert "transit_flag=--check-transit" in workflow
    # push 로 도는 자동 배포에는 inputs 가 없으므로 항상 검증 쪽으로 떨어져야 합니다.
    assert '"${SKIP_TRANSIT_CHECK:-false}" == "true"' in workflow


def test_public_verification_failure_has_a_guarded_rollback() -> None:
    workflow = (WORKFLOW_DIR / "deploy.yml").read_text(encoding="utf-8")
    assert "/etc/bitbox/deployment_in_progress" in workflow
    assert "Roll back a release that failed public verification" in workflow
    assert "Send deployment success alert" in workflow
    assert "/usr/local/sbin/bitbox-healthcheck" in workflow
    assert "--test-alert" in workflow
    assert '[[ "$marker" == "$RELEASE_SHA" ]] || exit 0' in workflow
    assert "previous_release_dir" in workflow
