import socket

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Fail fast if an automated test attempts a real network connection."""

    def denied(*args, **kwargs):
        raise AssertionError("Network access is disabled in automated tests.")

    monkeypatch.setattr(socket.socket, "connect", denied)
