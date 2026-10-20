
from typing import Any

from psycopg import sql


class SchemaDiscoveryError(RuntimeError):
    """Database schema discovery failed."""


def discover_postgres_schema(connection) -> dict[str, Any]:
    """
    Discover PostgreSQL table metadata.

    This function:
    - Does not read application table rows.
    - Does not modify database data.
    - Excludes PostgreSQL system schemas.
    - Uses parameterized metadata queries.
    """

    try:
        with connection.cursor() as cursor:

            # ------------------------------------
            # Discover tables and columns
            # ------------------------------------
            cursor.execute(
                """
                SELECT
                    c.table_schema,
                    c.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.ordinal_position
                FROM information_schema.columns AS c
                JOIN information_schema.tables AS t
                    ON t.table_schema = c.table_schema
                   AND t.table_name = c.table_name
                WHERE
                    t.table_type = 'BASE TABLE'
                    AND c.table_schema NOT IN (
                        'pg_catalog',
                        'information_schema'
                    )
                    AND c.table_schema NOT LIKE 'pg_toast%%'
                    AND c.table_schema NOT LIKE 'pg_temp_%%'
                ORDER BY
                    c.table_schema,
                    c.table_name,
                    c.ordinal_position
                """
            )

            column_rows = cursor.fetchall()

            # ------------------------------------
            # Discover primary keys
            # ------------------------------------
            cursor.execute(
                """
                SELECT
                    kcu.table_schema,
                    kcu.table_name,
                    kcu.column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_catalog = kcu.constraint_catalog
                   AND tc.constraint_schema = kcu.constraint_schema
                   AND tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                   AND tc.table_name = kcu.table_name
                WHERE
                    tc.constraint_type = 'PRIMARY KEY'
                ORDER BY
                    kcu.table_schema,
                    kcu.table_name,
                    kcu.ordinal_position
                """
            )

            primary_key_rows = cursor.fetchall()

            # ------------------------------------
            # Discover foreign keys
            # ------------------------------------
            cursor.execute(
                """
                SELECT
                    fk.table_schema,
                    fk.table_name,
                    fk.column_name,
                    pk.table_schema AS referenced_schema,
                    pk.table_name AS referenced_table,
                    pk.column_name AS referenced_column
                FROM information_schema.referential_constraints AS rc
                JOIN information_schema.key_column_usage AS fk
                    ON fk.constraint_catalog = rc.constraint_catalog
                   AND fk.constraint_schema = rc.constraint_schema
                   AND fk.constraint_name = rc.constraint_name
                JOIN information_schema.key_column_usage AS pk
                    ON pk.constraint_catalog = rc.unique_constraint_catalog
                   AND pk.constraint_schema = rc.unique_constraint_schema
                   AND pk.constraint_name = rc.unique_constraint_name
                   AND pk.ordinal_position = fk.position_in_unique_constraint
                ORDER BY
                    fk.table_schema,
                    fk.table_name,
                    fk.ordinal_position
                """
            )

            foreign_key_rows = cursor.fetchall()

    except Exception as exc:
        raise SchemaDiscoveryError(
            "Unable to discover PostgreSQL schema"
        ) from exc

    # ------------------------------------
    # Build structured schema metadata
    # ------------------------------------
    tables: dict[tuple[str, str], dict[str, Any]] = {}

    for (
        schema_name,
        table_name,
        column_name,
        data_type,
        is_nullable,
        ordinal_position,
    ) in column_rows:

        table_key = (schema_name, table_name)

        if table_key not in tables:
            tables[table_key] = {
                "schema": schema_name,
                "table": table_name,
                "columns": [],
                "primary_keys": [],
                "foreign_keys": [],
            }

        tables[table_key]["columns"].append(
            {
                "name": column_name,
                "data_type": data_type,
                "nullable": is_nullable == "YES",
            }
        )

    for schema_name, table_name, column_name in primary_key_rows:
        table_key = (schema_name, table_name)

        if table_key in tables:
            tables[table_key]["primary_keys"].append(
                column_name
            )

    for (
        schema_name,
        table_name,
        column_name,
        referenced_schema,
        referenced_table,
        referenced_column,
    ) in foreign_key_rows:

        table_key = (schema_name, table_name)

        if table_key in tables:
            tables[table_key]["foreign_keys"].append(
                {
                    "column": column_name,
                    "referenced_schema": referenced_schema,
                    "referenced_table": referenced_table,
                    "referenced_column": referenced_column,
                }
            )

    return {
        "table_count": len(tables),
        "tables": list(tables.values()),
    }
