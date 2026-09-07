from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8-sig")


def test_frontend_defaults_to_current_origin_and_keeps_local_override():
    source = read("frontend/app.js")

    assert "window.location.origin" in source
    assert "localhost|127\\.0\\.0\\.1" in source
    assert '"http://127.0.0.1:8000"' not in source


def test_api_image_does_not_copy_environment_file_and_runs_single_worker():
    dockerfile = read("Dockerfile.api")

    assert "COPY . ." not in dockerfile
    assert ".env" not in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert "USER 10001" in dockerfile
    assert "/api/health" in dockerfile
    assert "COPY data/mapping_v1.json ./data/mapping_v1.json" in dockerfile


def test_web_proxy_covers_all_browser_api_prefixes():
    config = read("deploy/nginx.conf")

    for path in ("/api/", "/chat", "/kb/", "/tools/", "/docs", "/openapi.json"):
        assert f"location {path}" in config
    assert "zhishu-mingxi-api:8000" in config
    assert "try_files $uri $uri/ /index.html" in config


def test_kubernetes_resources_are_namespaced_persistent_and_bounded():
    namespace = read("deploy/kubernetes/namespace.yaml")
    api = read("deploy/kubernetes/api.yaml")
    web = read("deploy/kubernetes/web.yaml")
    storage = read("deploy/kubernetes/storage.yaml")

    assert "name: zhishu-mingxi" in namespace
    for manifest in (api, web, storage):
        assert "namespace: zhishu-mingxi" in manifest
    assert "replicas: 1" in api
    assert "persistentVolumeClaim" in api
    assert "startupProbe" in api
    assert "readinessProbe" in api
    assert "livenessProbe" in api
    assert 'memory: "3Gi"' in api
    assert "type: NodePort" in web
    assert "nodePort:" not in web


def test_secret_example_contains_placeholders_only():
    secret = read("deploy/kubernetes/secret.example.yaml")

    assert "REPLACE_WITH_" in secret
    assert "kind: Secret" in secret
    assert "SPARK_API_KEY:" in secret
