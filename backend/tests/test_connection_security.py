
import socket

import pytest

from app.core.connection_security import (
    UnsafeDatabaseHostError,
    validate_database_host,
)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.10",
        "172.16.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_restricted_ip_addresses_rejected(host):
    with pytest.raises(UnsafeDatabaseHostError):
        validate_database_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "",
        " ",
        "https://example.com",
        "user@host.example.com",
        "host.example.com/path",
        "host.example.com?query=1",
        "fe80::1%eth0",
    ],
)
def test_invalid_hosts_rejected(host):
    with pytest.raises(UnsafeDatabaseHostError):
        validate_database_host(host)


def test_public_ipv4_accepted():
    assert validate_database_host("8.8.8.8") == "8.8.8.8"


def test_public_ipv6_accepted():
    assert (
        validate_database_host("2606:4700:4700::1111")
        == "2606:4700:4700::1111"
    )


def test_hostname_resolving_to_private_ip_rejected(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("192.168.1.50", 0),
            )
        ]

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        fake_getaddrinfo,
    )

    with pytest.raises(UnsafeDatabaseHostError):
        validate_database_host("database.example.com")


def test_hostname_resolving_to_public_ip_accepted(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("8.8.8.8", 0),
            )
        ]

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        fake_getaddrinfo,
    )

    assert (
        validate_database_host("database.example.com")
        == "database.example.com"
    )


def test_hostname_with_mixed_public_private_ips_rejected(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [
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
        ]

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        fake_getaddrinfo,
    )

    with pytest.raises(UnsafeDatabaseHostError):
        validate_database_host("mixed.example.com")


def test_unresolvable_hostname_rejected(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        raise socket.gaierror("Name not found")

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        fake_getaddrinfo,
    )

    with pytest.raises(UnsafeDatabaseHostError):
        validate_database_host("missing.example.com")
