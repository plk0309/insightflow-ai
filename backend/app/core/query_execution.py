
import json

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

import psycopg

from app.core.query_security import validate_read_only_query


MAX_RESULT_ROWS = 500
MAX_RESULT_COLUMNS = 100
MAX_RESULT_BYTES = 1_000_000


class QueryExecutionError(RuntimeError):
    """A database query could not be executed safely."""


def serialize_query_value(value):
    """
    Convert common PostgreSQL values to JSON-safe values.
    """
    if value is None:
        return None

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, bytes):
        raise QueryExecutionError(
            "Binary query results are not supported"
        )

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (list, tuple)):
        return [
            serialize_query_value(item)
            for item in value
        ]

    if isinstance(value, dict):
        return {
            str(key): serialize_query_value(item)
            for key, item in value.items()
        }

    raise QueryExecutionError(
        "Unsupported query result type"
    )


def execute_read_only_query(
    connection: psycopg.Connection,
    sql: str,
) -> dict:
    """
    Execute a validated SELECT using an existing
    secure PostgreSQL connection.

    The connection must use a least-privilege database
    account and enforce read-only transactions and
    statement timeouts.
    """
    # Reject unsafe SQL before starting a transaction.
    validated_sql = validate_read_only_query(sql)

    try:
        # Enforce read-only mode in the current transaction.
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET TRANSACTION READ ONLY"
                )

                cursor.execute(validated_sql)

                if cursor.description is None:
                    raise QueryExecutionError(
                        "Query did not return a result set"
                    )

                columns = [
                    column.name
                    for column in cursor.description
                ]

                if len(columns) > MAX_RESULT_COLUMNS:
                    raise QueryExecutionError(
                        "Query returns too many columns"
                    )

                # Fetch one extra row to detect truncation.
                records = cursor.fetchmany(
                    MAX_RESULT_ROWS + 1
                )

                truncated = (
                    len(records) > MAX_RESULT_ROWS
                )

                records = records[:MAX_RESULT_ROWS]

                rows = [
                    [
                        serialize_query_value(value)
                        for value in record
                    ]
                    for record in records
                ]

        result = {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }

        # Enforce the maximum serialized JSON response size.
        # UTF-8 byte counting handles multibyte Unicode text.
        try:
            serialized = json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError) as exc:
            raise QueryExecutionError(
                "Query result cannot be serialized safely"
            ) from exc

        if len(serialized) > MAX_RESULT_BYTES:
            raise QueryExecutionError(
                "Query result exceeds maximum response size"
            )

        return result

    except psycopg.Error as exc:
        # Do not expose SQL driver details, which may contain
        # credentials or other sensitive information.
        raise QueryExecutionError(
            "Database query execution failed"
        ) from exc
