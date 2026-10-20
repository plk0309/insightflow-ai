
import sqlglot
from sqlglot import exp


class UnsafeQueryError(ValueError):
    """The SQL statement is not permitted."""


ALLOWED_QUERY_TYPES = (
    exp.Select,
    exp.Union,
    exp.Intersect,
    exp.Except,
)

FORBIDDEN_QUERY_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Merge,
    exp.TruncateTable,
    exp.Into,
)

# A conservative initial allowlist for BI analytics.
# Add new functions only after reviewing their behavior.
ALLOWED_FUNCTIONS = frozenset(
    {
        "ABS",
        "AVG",
        "CEIL",
        "CEILING",
        "COALESCE",
        "CONCAT",
        "COUNT",
        "DATE_TRUNC",
        "EXTRACT",
        "FLOOR",
        "GREATEST",
        "LEAST",
        "LENGTH",
        "LOWER",
        "MAX",
        "MIN",
        "NULLIF",
        "ROUND",
        "SUM",
        "TRIM",
        "UPPER",
    }
)


def validate_read_only_query(sql: str) -> str:
    """
    Validate a single read-only PostgreSQL analytics query.

    SQL parsing is only one security layer. The database
    connection must also use least-privilege permissions,
    read-only transactions, and execution limits.
    """
    if not isinstance(sql, str):
        raise UnsafeQueryError("SQL must be a string")

    sql = sql.strip()

    if not sql:
        raise UnsafeQueryError("SQL cannot be empty")

    if len(sql) > 20_000:
        raise UnsafeQueryError(
            "SQL exceeds the maximum length"
        )

    try:
        statements = sqlglot.parse(
            sql,
            read="postgres",
            error_level=sqlglot.ErrorLevel.RAISE,
        )
    except (sqlglot.errors.ParseError, ValueError) as exc:
        raise UnsafeQueryError(
            "Invalid SQL statement"
        ) from exc

    if len(statements) != 1 or statements[0] is None:
        raise UnsafeQueryError(
            "Exactly one SQL statement is required"
        )

    statement = statements[0]

    if not isinstance(statement, ALLOWED_QUERY_TYPES):
        raise UnsafeQueryError(
            "Only SELECT queries are permitted"
        )

    for node in statement.walk():
        if isinstance(node, FORBIDDEN_QUERY_TYPES):
            raise UnsafeQueryError(
                "Query contains a prohibited operation"
            )

        if isinstance(node, exp.Lock):
            raise UnsafeQueryError(
                "Locking queries are not permitted"
            )

        if isinstance(node, exp.Func):
            function_name = node.sql_name().upper()

            # Anonymous functions use their actual SQL name.
            if isinstance(node, exp.Anonymous):
                function_name = node.name.upper()

            if function_name not in ALLOWED_FUNCTIONS:
                raise UnsafeQueryError(
                    "SQL function is not permitted"
                )

    return sql
