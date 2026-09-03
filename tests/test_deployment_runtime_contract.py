from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_docker_runtime_keeps_one_uvicorn_worker_for_process_local_queue():
    dockerfile = (_repo_root() / "Dockerfile").read_text(encoding="utf-8")

    assert "uvicorn backend.main_api:app" in dockerfile
    assert "--workers" not in dockerfile


def test_compose_keeps_built_frontend_and_requires_admin_runtime_config():
    compose = (_repo_root() / "docker-compose.yml").read_text(encoding="utf-8")

    assert "uvicorn backend.main_api:app" in compose
    assert "--workers" not in compose
    assert "ADMIN_PASSWORD:" in compose
    assert "ADMIN_SESSION_SECRET:" in compose
    assert "HEAVY_JOB_QUEUE_SIZE:" in compose

    # The Dockerfile already copies frontend/dist into /app. Mounting the whole
    # repository here would hide that built artifact when the host has no dist.
    assert "- ./:/app" not in compose
    assert "- .:/app" not in compose


def test_render_uses_the_same_docker_single_process_entrypoint():
    render = (_repo_root() / "render.yaml").read_text(encoding="utf-8")

    assert "runtime: docker" in render
    assert "dockerfilePath: ./Dockerfile" in render
    assert "healthCheckPath: /api/health" in render
