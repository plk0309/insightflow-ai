
from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
import pytest

from app.core.query_execution import (
    MAX_RESULT_BYTES,
    MAX_RESULT_COLUMNS,
    MAX_RESULT_ROWS,
    QueryExecutionError,
    execute_read_only_query,
    serialize_query_value,
)
from app.core.query_security import UnsafeQueryError


@pytest.fixture
def fake_database():
    """
    Mock PostgreSQL without opening any real connections.
    """
    cursor = MagicMock()

    cursor.description = [
        SimpleNamespace(name="region"),
        SimpleNamespace(name="revenue"),
    ]

    cursor.fetchmany.return_value = [
        ("North", Decimal("12500.50")),
        ("South", Decimal("9800.00")),
    ]

    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    return connection, cursor


def test_query_returns_structured_results(fake_database):
    connection, cursor = fake_database

    result = execute_read_only_query(
        connection,
        "SELECT region, revenue FROM sales",
    )

    assert result == {
        "columns": ["region", "revenue"],
        "rows": [
            ["North", "12500.50"],
            ["South", "9800.00"],
        ],
        "row_count": 2,
        "truncated": False,
    }


def test_transaction_is_set_read_only(fake_database):
    connection, cursor = fake_database

    execute_read_only_query(
        connection,
        "SELECT region FROM sales",
    )

    executed = [
        call.args[0]
        for call in cursor.execute.call_args_list
    ]

    assert executed[0] == "SET TRANSACTION READ ONLY"
    assert executed[1] == "SELECT region FROM sales"

    connection.transaction.assert_called_once()


def test_query_fetches_only_bounded_rows(fake_database):
    connection, cursor = fake_database

    execute_read_only_query(
        connection,
        "SELECT region FROM sales",
    )

    cursor.fetchmany.assert_called_once_with(
        MAX_RESULT_ROWS + 1
    )


def test_large_results_are_truncated(fake_database):
    connection, cursor = fake_database

    cursor.fetchmany.return_value = [
        (f"Region-{index}", Decimal("100.00"))
        for index in range(MAX_RESULT_ROWS + 1)
    ]

    result = execute_read_only_query(
        connection,
        "SELECT region, revenue FROM sales",
    )

    assert result["row_count"] == MAX_RESULT_ROWS
    assert len(result["rows"]) == MAX_RESULT_ROWS
    assert result["truncated"] is True


def test_write_queries_are_rejected_before_execution(fake_database):
    connection, cursor = fake_database

    with pytest.raises(UnsafeQueryError):
        execute_read_only_query(
            connection,
            "DELETE FROM customers",
        )

    connection.transaction.assert_not_called()
    cursor.execute.assert_not_called()


def test_multiple_statements_are_rejected(fake_database):
    connection, cursor = fake_database

    with pytest.raises(UnsafeQueryError):
        execute_read_only_query(
            connection,
            "SELECT 1; DROP TABLE customers",
        )

    cursor.execute.assert_not_called()


def test_queries_without_results_are_rejected(fake_database):
    connection, cursor = fake_database
    cursor.description = None

    with pytest.raises(
        QueryExecutionError,
        match="Query did not return a result set",
    ):
        execute_read_only_query(
            connection,
            "SELECT 1",
        )


def test_excessive_columns_are_rejected(fake_database):
    connection, cursor = fake_database

    cursor.description = [
        SimpleNamespace(name=f"column_{index}")
        for index in range(MAX_RESULT_COLUMNS + 1)
    ]

    with pytest.raises(
        QueryExecutionError,
        match="too many columns",
    ):
        execute_read_only_query(
            connection,
            "SELECT * FROM sales",
        )

    cursor.fetchmany.assert_not_called()


def test_database_errors_are_sanitized(fake_database):
    connection, cursor = fake_database

    cursor.execute.side_effect = psycopg.OperationalError(
        "Sensitive password=VerySecret123"
    )

    with pytest.raises(QueryExecutionError) as exc_info:
        execute_read_only_query(
            connection,
            "SELECT 1",
        )

    assert str(exc_info.value) == (
        "Database query execution failed"
    )

    assert "VerySecret123" not in str(exc_info.value)


def test_binary_results_are_rejected(fake_database):
    connection, cursor = fake_database

    cursor.fetchmany.return_value = [
        ("North", b"binary-data"),
    ]

    with pytest.raises(
        QueryExecutionError,
        match="Binary query results are not supported",
    ):
        execute_read_only_query(
            connection,
            "SELECT region, revenue FROM sales",
        )


def test_common_values_are_serialized():
    identifier = uuid4()

    assert serialize_query_value(None) is None
    assert serialize_query_value(True) is True
    assert serialize_query_value(123) == 123

    assert serialize_query_value(
        Decimal("123.45")
    ) == "123.45"

    assert serialize_query_value(
        date(2026, 10, 20)
    ) == "2026-10-20"

    assert serialize_query_value(
        datetime(2026, 10, 20, 14, 30)
    ) == "2026-10-20T14:30:00"

    assert serialize_query_value(
        time(14, 30)
    ) == "14:30:00"

    assert serialize_query_value(
        identifier
    ) == str(identifier)

    assert serialize_query_value(
        [Decimal("10.50"), None]
    ) == ["10.50", None]

    assert serialize_query_value(
        {"total": Decimal("25.75")}
    ) == {"total": "25.75"}


def test_unsupported_result_types_are_rejected():
    with pytest.raises(
        QueryExecutionError,
        match="Unsupported query result type",
    ):
        serialize_query_value(object())


# --------------------------------------------------
# RESPONSE SIZE SECURITY TESTS
# --------------------------------------------------

def test_oversized_query_result_rejected(fake_database):
    connection, cursor = fake_database

    cursor.fetchmany.return_value = [
        ("North", "X" * (MAX_RESULT_BYTES + 100))
    ]

    with pytest.raises(
        QueryExecutionError,
        match="maximum response size",
    ):
        execute_read_only_query(
            connection,
            "SELECT region, revenue FROM sales",
        )


def test_large_unicode_result_rejected(fake_database):
    connection, cursor = fake_database

    # Emoji characters typically occupy four UTF-8 bytes.
    cursor.fetchmany.return_value = [
        ("North", "😀" * (MAX_RESULT_BYTES // 4 + 100))
    ]

    with pytest.raises(
        QueryExecutionError,
        match="maximum response size",
    ):
        execute_read_only_query(
            connection,
            "SELECT region, revenue FROM sales",
        )
