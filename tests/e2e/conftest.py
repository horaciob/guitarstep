"""Browser tests: the real web UI in headless Chromium, against a server running in a thread.

Each test still gets its own ~/.guitarr (the `home` fixture in tests/conftest.py patches
`config`, which the server reads on every request). No audio device is needed: the tests
never start listening on a microphone, and headless Chromium has no audio output.
"""
import socket
import threading
import time

import pytest

pytest.importorskip("playwright")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server_url():
    import uvicorn

    from guitarr.gui.server import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    th.join(5)


@pytest.fixture
def app_page(page, server_url):
    """A page that fails the test on any uncaught error or console error."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.base = server_url
    yield page
    assert not errors, errors


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    # let the tone rig's AudioContext start without a click (headless has no audio output anyway)
    return {**browser_type_launch_args, "args": ["--autoplay-policy=no-user-gesture-required"]}
