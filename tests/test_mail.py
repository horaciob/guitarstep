"""The sign-in email, sent to a tiny SMTP server on this machine (no database needed)."""
import socket
import threading

import pytest

from guitarr import accounts
from guitarr.errors import CodedError


def smtp_server():
    """A one-message SMTP server on a free port: (port, the received messages)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    got = []

    def serve():
        conn, _ = srv.accept()
        f = conn.makefile("rwb")
        say = lambda line: (f.write(line.encode() + b"\r\n"), f.flush())
        say("220 test")
        data = None
        for raw in f:
            line = raw.decode().rstrip("\r\n")
            if data is not None:
                if line == ".":
                    got.append("\n".join(data))
                    data = None
                    say("250 ok")
                else:
                    data.append(line)
            elif line.upper().startswith("EHLO"):
                say("250 test")
            elif line.upper() == "DATA":
                data = []
                say("354 go")
            elif line.upper() == "QUIT":
                say("221 bye")
                break
            else:
                say("250 ok")
        conn.close()
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1], got


def test_the_link_is_emailed(monkeypatch):
    port, got = smtp_server()
    monkeypatch.setenv("GUITARR_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("GUITARR_SMTP_PORT", str(port))
    monkeypatch.setenv("GUITARR_SMTP_TLS", "off")
    monkeypatch.setenv("GUITARR_MAIL_FROM", "guitarr <no-reply@example.com>")
    accounts.send_link("ana@example.com", "https://guitarr.example/auth/verify?token=abc")
    assert len(got) == 1
    assert "To: ana@example.com" in got[0] and "token=abc" in got[0]


def test_a_mail_server_that_fails_is_a_coded_error(monkeypatch):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                   # nothing listens there
    monkeypatch.setenv("GUITARR_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("GUITARR_SMTP_PORT", str(port))
    with pytest.raises(CodedError) as e:
        accounts.send_link("ana@example.com", "https://guitarr.example/auth/verify?token=abc")
    assert e.value.code == "mail_failed"
