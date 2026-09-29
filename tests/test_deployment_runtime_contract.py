from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_docker_runtime_keeps_one_uvicorn_worker_for_process_local_queue():
    dockerfile = (_repo_root() / "Dockerfile").read_text(encoding="utf-8")

    assert "uvicorn backend.main_api:app" in dockerfile
    assert "backend.main_api_core:app" not in dockerfile
    assert "--workers" not in dockerfile


def test_compose_keeps_built_frontend_and_requires_admin_runtime_config():
    compose = (_repo_root() / "docker-compose.yml").read_text(encoding="utf-8")

    assert "uvicorn backend.main_api:app" in compose
    assert "backend.main_api_core:app" not in compose
    assert "--workers" not in compose
    assert "ADMIN_PASSWORD:" in compose
    assert "ADMIN_SESSION_SECRET:" in compose
    assert "HEAVY_JOB_QUEUE_SIZE:" in compose

    # The Dockerfile already copies frontend/dist into /app. Mounting the whole
    # repository here would hide that built artifact when the host has no dist.
    assert "- ./:/app" not in compose
    assert "- .:/app" not in compose


def test_cloud_run_deploy_waits_for_ci_and_preserves_process_local_runtime_contract():
    workflow_path = _repo_root() / ".github" / "workflows" / "deploy-cloud-run.yml"
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "workflows: [\"CI\"]" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert "google-github-actions/auth@v3" in workflow
    assert "google-github-actions/deploy-cloudrun@v3" in workflow
    assert "source: ." in workflow
    assert "--min-instances=1" in workflow
    assert "--max-instances=1" in workflow
    assert "--no-cpu-throttling" in workflow
    assert "HEAVY_JOB_QUEUE_SIZE=1" in workflow
    assert "/api/health" in workflow
    assert "contracts_ok" in workflow
    assert "backend.main_api_core:app" not in workflow


def test_render_blueprint_is_removed_after_cloud_run_migration():
    assert not (_repo_root() / "render.yaml").exists()
