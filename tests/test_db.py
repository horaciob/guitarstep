"""Schema migrations (against a real Postgres; skipped without one)."""
import pytest

from guitarr.db import migrate
from guitarr.errors import CodedError


def test_migrations_apply_in_order_once(pg_url, tmp_path):
    (tmp_path / "0001_first.sql").write_text("CREATE TABLE a (x int);")
    (tmp_path / "0002_second.sql").write_text("INSERT INTO a VALUES (1); INSERT INTO a VALUES (2);")
    assert [m.version for m in migrate.pending(pg_url, tmp_path)] == [1, 2]
    assert [m.name for m in migrate.migrate(pg_url, tmp_path, log=lambda m: None)] == ["first", "second"]
    assert migrate.migrate(pg_url, tmp_path, log=lambda m: None) == []          # nothing runs twice
    assert all(s["applied_at"] for s in migrate.status(pg_url, tmp_path))
    p = migrate.new("Add the B table!", tmp_path)
    assert p.name == "0003_add_the_b_table.sql"
    assert [m.version for m in migrate.pending(pg_url, tmp_path)] == [3]


def test_a_failing_migration_leaves_nothing_behind(pg_url, tmp_path):
    import psycopg
    (tmp_path / "0001_ok.sql").write_text("CREATE TABLE a (x int);")
    (tmp_path / "0002_bad.sql").write_text("CREATE TABLE b (x int); SELECT nope;")
    with pytest.raises(psycopg.Error):
        migrate.migrate(pg_url, tmp_path, log=lambda m: None)
    st = {s["version"]: s["applied_at"] for s in migrate.status(pg_url, tmp_path)}
    assert st[1] and st[2] is None
    with psycopg.connect(pg_url) as c:
        assert c.execute("SELECT to_regclass('b')").fetchone()[0] is None       # rolled back with its record


def test_an_applied_migration_cannot_change(pg_url, tmp_path):
    f = tmp_path / "0001_first.sql"
    f.write_text("CREATE TABLE a (x int);")
    migrate.migrate(pg_url, tmp_path, log=lambda m: None)
    f.write_text("CREATE TABLE a (x int, y int);")
    with pytest.raises(CodedError) as e:
        migrate.migrate(pg_url, tmp_path, log=lambda m: None)
    assert e.value.code == "edited_migration"
    f.unlink()
    with pytest.raises(CodedError) as e:
        migrate.status(pg_url, tmp_path)
    assert e.value.code == "missing_migration"


def test_bad_names_and_duplicates_are_refused(tmp_path):
    (tmp_path / "1_x.sql").write_text("")
    with pytest.raises(CodedError):
        migrate.discover(tmp_path)
    (tmp_path / "1_x.sql").unlink()
    (tmp_path / "0001_a.sql").write_text("")
    (tmp_path / "0001_b.sql").write_text("")
    with pytest.raises(CodedError):
        migrate.discover(tmp_path)


def test_two_processes_migrating_at_once_apply_each_file_once(pg_url, tmp_path):
    import threading
    (tmp_path / "0001_slow.sql").write_text("CREATE TABLE a (x int); SELECT pg_sleep(0.3);")
    errors = []

    def go():
        try:
            migrate.migrate(pg_url, tmp_path, log=lambda m: None)
        except Exception as e:
            errors.append(e)
    ths = [threading.Thread(target=go) for _ in range(3)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert not errors


def test_the_real_migrations_apply(pg_url):
    assert migrate.migrate(pg_url, log=lambda m: None)
    assert not migrate.pending(pg_url)
