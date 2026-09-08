from pathlib import Path


def test_chat_proxy_does_not_capture_chat_static_assets() -> None:
    config = (Path(__file__).resolve().parents[1] / "deploy" / "nginx.conf").read_text(encoding="utf-8")

    assert "location = /chat {" in config
    assert "location /chat {" not in config
