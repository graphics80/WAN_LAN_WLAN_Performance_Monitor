import os
from pathlib import Path

from monitor_app.config import AppConfig, load_env_from_file


def test_config_defaults():
    cfg = AppConfig.from_env()
    assert "www.google.ch" in cfg.ping_targets
    assert cfg.ping_count == 4
    assert cfg.http_test_interval_minutes == 15
    assert cfg.enable_ping is True
    assert cfg.enable_speedtest is True
    assert cfg.enable_download_tests is True
    assert cfg.enable_http_tests is True


def test_config_from_env_overrides():
    os.environ["PING_COUNT"] = "9"
    os.environ["PING_TARGETS"] = "a.example.com,b.example.com"
    cfg = AppConfig.from_env()
    assert cfg.ping_count == 9
    assert cfg.ping_targets == ["a.example.com", "b.example.com"]


def test_config_toggle_parsing(monkeypatch):
    monkeypatch.setenv("ENABLE_PING", "false")
    monkeypatch.setenv("ENABLE_SPEEDTEST", "0")
    monkeypatch.setenv("ENABLE_DOWNLOAD_TESTS", "off")
    monkeypatch.setenv("ENABLE_HTTP_TESTS", "no")
    cfg = AppConfig.from_env()
    assert cfg.enable_ping is False
    assert cfg.enable_speedtest is False
    assert cfg.enable_download_tests is False
    assert cfg.enable_http_tests is False


def test_load_env_from_file(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nPING_COUNT=7")
    monkeypatch.chdir(tmp_path)
    load_env_from_file(".env")
    assert os.environ["FOO"] == "bar"
    assert os.environ["PING_COUNT"] == "7"
