
import socket

import pytest

from app.core.connection_security import (
    UnsafeDatabaseHostError,
    resolve_public_database_addresses,
)


def test_public_ipv4_literal_resolves():
    assert resolve_public_database_addresses(
        "8.8.8.8"
    ) == ("8.8.8.8",)


def test_public_ipv6_literal_resolves():
    assert resolve_public_database_addresses(
        "2606:4700:4700::1111"
    ) == ("2606:4700:4700::1111",)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.1.10",
        "169.254.169.254",
        "::1",
        "fc00::1",
    ],
)
def test_private_addresses_rejected(host):
    with pytest.raises(UnsafeDatabaseHostError):
        resolve_public_database_addresses(host)


def test_hostname_resolves_to_public_ip(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("8.8.8.8", 0),
            )
        ],
    )

    assert resolve_public_database_addresses(
        "db.example.com"
    ) == ("8.8.8.8",)


def test_mixed_public_private_dns_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("8.8.8.8", 0),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("10.0.0.5", 0),
            ),
        ],
    )

    with pytest.raises(UnsafeDatabaseHostError):
        resolve_public_database_addresses("db.example.com")


def test_duplicate_addresses_removed(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("8.8.8.8", 0),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("8.8.8.8", 0),
            ),
        ],
    )

    assert resolve_public_database_addresses(
        "db.example.com"
    ) == ("8.8.8.8",)


def test_unresolvable_host_rejected(monkeypatch):
    def fail_resolution(*args, **kwargs):
        raise socket.gaierror("Host not found")

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        fail_resolution,
    )

    with pytest.raises(UnsafeDatabaseHostError):
        resolve_public_database_addresses("missing.example.com")
