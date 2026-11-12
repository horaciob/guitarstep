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
    monkeypatch.setattr(config, "BASE", h)         # HOME, CONFIG_PATH, SONGS_DIR… follow it
    monkeypatch.setattr(config, "CACHE_DIR", cache_dir)
    return h


@pytest.fixture(scope="session")
def demo_dir(tmp_path_factory):
    from guitarr.demo import main

    return main(tmp_path_factory.mktemp("demo"))


# ---------------------------------------------------------------- Postgres (web service tests)
def _pg_bin():
    import shutil
    from pathlib import Path
    for d in [None, "/opt/homebrew/opt/postgresql@18/bin", "/opt/homebrew/opt/postgresql@17/bin",
              "/usr/lib/postgresql/18/bin", "/usr/lib/postgresql/17/bin", "/usr/lib/postgresql/16/bin"]:
        p = shutil.which("initdb", path=d) if d else shutil.which("initdb")
        if p:
            return Path(p).parent
    return None


@pytest.fixture(scope="session")
def pg_server(tmp_path_factory):
    """A Postgres to test against: GUITARR_TEST_DATABASE_URL (an admin URL), or a throwaway
    cluster started from the local binaries. Skips the test when neither is there."""
    import os
    import socket
    import subprocess
    url = os.environ.get("GUITARR_TEST_DATABASE_URL")
    if url:
        yield url
        return
    bin_ = _pg_bin()
    if bin_ is None:
        pytest.skip("no Postgres: set GUITARR_TEST_DATABASE_URL or install postgres")
    data = tmp_path_factory.mktemp("pg")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    subprocess.run([bin_ / "initdb", "-D", data / "db", "-U", "postgres", "-A", "trust", "--no-sync", "-E", "UTF8"],
                   check=True, capture_output=True)
    subprocess.run([bin_ / "pg_ctl", "-D", data / "db", "-l", data / "log", "-w", "-o",
                    f"-p {port} -c unix_socket_directories='' -c listen_addresses=127.0.0.1 -c fsync=off", "start"],
                   check=True, capture_output=True)
    try:
        yield f"postgresql://postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run([bin_ / "pg_ctl", "-D", data / "db", "-m", "immediate", "stop"], capture_output=True)


@pytest.fixture
def pg_url(pg_server):
    """An empty database of its own for each test."""
    import uuid
    import psycopg
    name = f"t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(pg_server, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{name}"')
    base = pg_server.rsplit("/", 1)[0]
    yield f"{base}/{name}"
    from guitarr import db
    db.close()
    with psycopg.connect(pg_server, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
