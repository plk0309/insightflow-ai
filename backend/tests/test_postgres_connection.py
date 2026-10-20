
from unittest.mock import MagicMock

import psycopg
import pytest

from app.core.postgres_connection import (
    PostgreSQLConnectionError,
    secure_postgres_connection,
)


@pytest.fixture
def mock_postgres(monkeypatch):
    """Replace DNS resolution and PostgreSQL connections."""
    connection = MagicMock()

    def fake_resolve(host):
        assert host == "db.example.com"
        return ("8.8.8.8",)

    connect = MagicMock(return_value=connection)

    monkeypatch.setattr(
        "app.core.postgres_connection.resolve_public_database_addresses",
        fake_resolve,
    )
    monkeypatch.setattr(
        "app.core.postgres_connection.psycopg.connect",
        connect,
    )

    return connection, connect


def connection_settings():
    return {
        "host": "db.example.com",
        "port": 5432,
        "database_name": "analytics",
        "username": "readonly_user",
        "password": "TestPassword123!",
    }


def test_connection_uses_pinned_ip(mock_postgres):
    _, connect = mock_postgres

    with secure_postgres_connection(**connection_settings()):
        pass

    kwargs = connect.call_args.kwargs

    assert kwargs["host"] == "db.example.com"
    assert kwargs["hostaddr"] == "8.8.8.8"


def test_connection_requires_verified_tls(mock_postgres):
    _, connect = mock_postgres

    with secure_postgres_connection(**connection_settings()):
        pass

    assert connect.call_args.kwargs["sslmode"] == "verify-full"


def test_connection_timeout_is_configured(mock_postgres):
    _, connect = mock_postgres

    with secure_postgres_connection(**connection_settings()):
        pass

    assert connect.call_args.kwargs["connect_timeout"] == 5


def test_connection_requests_read_only_transactions(mock_postgres):
    _, connect = mock_postgres

    with secure_postgres_connection(**connection_settings()):
        pass

    assert (
        "default_transaction_read_only=on"
        in connect.call_args.kwargs["options"]
    )


def test_connection_closes_after_success(mock_postgres):
    connection, _ = mock_postgres

    with secure_postgres_connection(**connection_settings()):
        pass

    connection.close.assert_called_once()


def test_connection_closes_after_application_error(mock_postgres):
    connection, _ = mock_postgres

    with pytest.raises(RuntimeError, match="Application error"):
        with secure_postgres_connection(**connection_settings()):
            raise RuntimeError("Application error")

    connection.close.assert_called_once()


def test_unsafe_host_rejected_before_connect(monkeypatch):
    connect = MagicMock()

    def reject_host(host):
        raise ValueError("Restricted destination")

    monkeypatch.setattr(
        "app.core.postgres_connection.resolve_public_database_addresses",
        reject_host,
    )
    monkeypatch.setattr(
        "app.core.postgres_connection.psycopg.connect",
        connect,
    )

    with pytest.raises(
        PostgreSQLConnectionError,
        match="not permitted",
    ):
        with secure_postgres_connection(**connection_settings()):
            pass

    connect.assert_not_called()


@pytest.mark.parametrize("port", [0, -1, 65536, "5432", True])
def test_invalid_port_rejected(port, monkeypatch):
    connect = MagicMock()

    monkeypatch.setattr(
        "app.core.postgres_connection.psycopg.connect",
        connect,
    )

    settings = connection_settings()
    settings["port"] = port

    with pytest.raises(
        PostgreSQLConnectionError,
        match="Invalid database port",
    ):
        with secure_postgres_connection(**settings):
            pass

    connect.assert_not_called()


def test_driver_errors_are_sanitized(mock_postgres):
    _, connect = mock_postgres

    connect.side_effect = psycopg.OperationalError(
        "Connection failed for password=SuperSecret123!"
    )

    with pytest.raises(PostgreSQLConnectionError) as exc_info:
        with secure_postgres_connection(**connection_settings()):
            pass

    assert str(exc_info.value) == "Secure PostgreSQL connection failed"
    assert "SuperSecret123!" not in str(exc_info.value)


def test_connection_uses_first_validated_address(monkeypatch):
    connection = MagicMock()
    connect = MagicMock(return_value=connection)

    monkeypatch.setattr(
        "app.core.postgres_connection.resolve_public_database_addresses",
        lambda host: ("8.8.8.8", "1.1.1.1"),
    )
    monkeypatch.setattr(
        "app.core.postgres_connection.psycopg.connect",
        connect,
    )

    with secure_postgres_connection(**connection_settings()):
        pass

    assert connect.call_args.kwargs["hostaddr"] == "8.8.8.8"


def test_statement_timeout_is_configured(mock_postgres):
    _, connect = mock_postgres

    with secure_postgres_connection(**connection_settings()):
        pass

    options = connect.call_args.kwargs["options"]

    assert "statement_timeout=10000" in options


def test_idle_transaction_timeout_is_configured(mock_postgres):
    _, connect = mock_postgres

    with secure_postgres_connection(**connection_settings()):
        pass

    options = connect.call_args.kwargs["options"]

    assert "idle_in_transaction_session_timeout=15000" in options
