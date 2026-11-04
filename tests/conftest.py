import pytest

from guitarr import config


@pytest.fixture(scope="session")
def cache_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("cache")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch, cache_dir):
    """Every test gets its own ~/.guitarr (config, history, takes). The transcription
    cache is shared across the session so basic-pitch doesn't run more than needed."""
    h = tmp_path / "home"
    monkeypatch.setattr(config, "HOME", h)
    monkeypatch.setattr(config, "CONFIG_PATH", h / "config.toml")
    monkeypatch.setattr(config, "SONGS_DIR", h / "songs")
    monkeypatch.setattr(config, "TAKES_DIR", h / "takes")
    monkeypatch.setattr(config, "HISTORY_DIR", h / "history")
    monkeypatch.setattr(config, "CACHE_DIR", cache_dir)
    return h


@pytest.fixture(scope="session")
def demo_dir(tmp_path_factory):
    from guitarr.demo import main

    return main(tmp_path_factory.mktemp("demo"))
