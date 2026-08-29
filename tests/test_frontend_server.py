from __future__ import annotations

from pathlib import Path

from frontend.server import resolve_textbook_directory, textbook_fallback_path


def test_textbook_uses_configured_external_directory(tmp_path, monkeypatch):
    textbook = tmp_path / 'textbook'
    textbook.mkdir()
    (textbook / 'index.html').write_text('<h1>??</h1>', encoding='utf-8')
    monkeypatch.setenv('TEXTBOOK_DIR', str(textbook))

    assert resolve_textbook_directory() == textbook.resolve()


def test_textbook_has_a_non_blank_fallback_when_external_resource_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv('TEXTBOOK_DIR', str(tmp_path / 'missing-textbook'))

    fallback = textbook_fallback_path()

    assert resolve_textbook_directory() is None
    assert fallback.name == 'textbook-unavailable.html'
    assert fallback.is_file()


def test_textbook_uses_frontend_junction_when_no_environment_path_is_set(tmp_path, monkeypatch):
    textbook = tmp_path / 'textbook'
    textbook.mkdir()
    (textbook / 'index.html').write_text('<h1>??</h1>', encoding='utf-8')
    monkeypatch.delenv('TEXTBOOK_DIR', raising=False)
    monkeypatch.setattr('frontend.server.FRONTEND_DIR', tmp_path)

    assert resolve_textbook_directory() == textbook.resolve()
