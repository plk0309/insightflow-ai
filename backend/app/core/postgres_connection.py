
from contextlib import contextmanager

import psycopg

from app.core.connection_security import (
    resolve_public_database_addresses,
)


class PostgreSQLConnectionError(RuntimeError):
    """A database connection could not be established safely."""


@contextmanager
def secure_postgres_connection(
    *,
    host: str,
    port: int,
    database_name: str,
    username: str,
    password: str,
):
    """
    Connect to a validated public IP while verifying TLS
    against the original database hostname.

    Plaintext connections are not permitted.
    """

    # Validate database port.
    if not isinstance(port, int) or isinstance(port, bool):
        raise PostgreSQLConnectionError(
            "Invalid database port"
        )

    if not 1 <= port <= 65535:
        raise PostgreSQLConnectionError(
            "Invalid database port"
        )

    # Resolve and validate the destination before connecting.
    # The original hostname must not be resolved again by libpq.
    try:
        addresses = resolve_public_database_addresses(host)
    except ValueError as exc:
        raise PostgreSQLConnectionError(
            "Database destination is not permitted"
        ) from exc

    # Connect to the validated IP address.
    # Keep the original hostname for TLS certificate verification.
    selected_ip = addresses[0]

    connection = None

    try:
        connection = psycopg.connect(
            host=host,
            hostaddr=selected_ip,
            port=port,
            dbname=database_name,
            user=username,
            password=password,
            sslmode="verify-full",
            connect_timeout=5,
            application_name="insightflow_ai",
            options=(
                "-c default_transaction_read_only=on "
                "-c statement_timeout=10000 "
                "-c idle_in_transaction_session_timeout=15000"
            ),
        )

        yield connection

    except psycopg.Error as exc:
        # Avoid exposing driver error details, which may
        # contain connection parameters or server information.
        raise PostgreSQLConnectionError(
            "Secure PostgreSQL connection failed"
        ) from exc

    finally:
        if connection is not None:
            connection.close()
