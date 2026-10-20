
from unittest.mock import MagicMock

import pytest

from app.core.schema_discovery import (
    SchemaDiscoveryError,
    discover_postgres_schema,
)


def make_connection(column_rows, primary_keys=None, foreign_keys=None):
    cursor = MagicMock()
    cursor.fetchall.side_effect = [
        column_rows,
        primary_keys or [],
        foreign_keys or [],
    ]

    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    return connection, cursor


def test_empty_database_returns_no_tables():
    connection, cursor = make_connection([])

    result = discover_postgres_schema(connection)

    assert result == {
        "table_count": 0,
        "tables": [],
    }
    assert cursor.execute.call_count == 3


def test_discovers_table_columns():
    connection, _ = make_connection(
        [
            ("public", "customers", "id", "uuid", "NO", 1),
            ("public", "customers", "email", "text", "NO", 2),
            ("public", "customers", "nickname", "text", "YES", 3),
        ]
    )

    result = discover_postgres_schema(connection)

    assert result["table_count"] == 1

    table = result["tables"][0]

    assert table["schema"] == "public"
    assert table["table"] == "customers"
    assert table["columns"] == [
        {"name": "id", "data_type": "uuid", "nullable": False},
        {"name": "email", "data_type": "text", "nullable": False},
        {"name": "nickname", "data_type": "text", "nullable": True},
    ]


def test_discovers_multiple_tables():
    connection, _ = make_connection(
        [
            ("public", "customers", "id", "uuid", "NO", 1),
            ("public", "orders", "id", "uuid", "NO", 1),
            ("analytics", "events", "id", "bigint", "NO", 1),
        ]
    )

    result = discover_postgres_schema(connection)

    assert result["table_count"] == 3

    discovered = {
        (table["schema"], table["table"])
        for table in result["tables"]
    }

    assert discovered == {
        ("public", "customers"),
        ("public", "orders"),
        ("analytics", "events"),
    }


def test_discovers_primary_keys():
    connection, _ = make_connection(
        [
            ("public", "customers", "id", "uuid", "NO", 1),
            ("public", "customers", "tenant_id", "uuid", "NO", 2),
        ],
        primary_keys=[
            ("public", "customers", "id"),
            ("public", "customers", "tenant_id"),
        ],
    )

    result = discover_postgres_schema(connection)

    assert result["tables"][0]["primary_keys"] == [
        "id",
        "tenant_id",
    ]


def test_discovers_foreign_keys():
    connection, _ = make_connection(
        [
            ("public", "orders", "id", "uuid", "NO", 1),
            ("public", "orders", "customer_id", "uuid", "NO", 2),
        ],
        foreign_keys=[
            (
                "public",
                "orders",
                "customer_id",
                "public",
                "customers",
                "id",
            )
        ],
    )

    result = discover_postgres_schema(connection)

    assert result["tables"][0]["foreign_keys"] == [
        {
            "column": "customer_id",
            "referenced_schema": "public",
            "referenced_table": "customers",
            "referenced_column": "id",
        }
    ]


def test_primary_keys_for_unknown_tables_are_ignored():
    connection, _ = make_connection(
        [],
        primary_keys=[
            ("public", "hidden_table", "id")
        ],
    )

    result = discover_postgres_schema(connection)

    assert result["table_count"] == 0


def test_foreign_keys_for_unknown_tables_are_ignored():
    connection, _ = make_connection(
        [],
        foreign_keys=[
            (
                "public",
                "hidden_table",
                "customer_id",
                "public",
                "customers",
                "id",
            )
        ],
    )

    result = discover_postgres_schema(connection)

    assert result["table_count"] == 0


def test_database_error_is_sanitized():
    connection = MagicMock()
    connection.cursor.side_effect = RuntimeError(
        "Sensitive database connection details"
    )

    with pytest.raises(
        SchemaDiscoveryError,
        match="Unable to discover PostgreSQL schema",
    ) as exc_info:
        discover_postgres_schema(connection)

    assert "Sensitive database connection details" not in str(
        exc_info.value
    )


def test_only_metadata_queries_are_executed():
    connection, cursor = make_connection([])

    discover_postgres_schema(connection)

    assert cursor.execute.call_count == 3

    for call in cursor.execute.call_args_list:
        query = call.args[0].strip().upper()

        assert query.startswith("SELECT")
        assert "INFORMATION_SCHEMA" in query
        assert "INSERT INTO" not in query
        assert "UPDATE " not in query
        assert "DELETE FROM" not in query
        assert "DROP TABLE" not in query
