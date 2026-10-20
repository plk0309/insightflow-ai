
import uuid

import psycopg
import pytest

from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.schema_discovery import discover_postgres_schema


@pytest.fixture
def postgres_connection():
    """
    Connect only to the isolated insightflow_test database.

    Never use the development database for integration tests.
    """

    config = dotenv_values(".env.test")
    database_url = config.get("DATABASE_URL")

    if not database_url:
        pytest.fail(
            "DATABASE_URL is missing from backend/.env.test"
        )

    # Validate the database name BEFORE connecting.
    parsed_url = make_url(database_url)

    if parsed_url.database != "insightflow_test":
        pytest.fail(
            "Integration tests require insightflow_test"
        )

    # Convert SQLAlchemy's URL format into a psycopg URL.
    psycopg_url = parsed_url.set(
        drivername="postgresql"
    ).render_as_string(hide_password=False)

    # Connect only to the validated test database.
    with psycopg.connect(psycopg_url) as connection:

        # Verify the actual connected database as well.
        if connection.info.dbname != "insightflow_test":
            pytest.fail(
                "Connected to an unexpected database"
            )

        yield connection


def test_discovers_real_postgres_tables_and_relationships(
    postgres_connection,
):
    connection = postgres_connection

    # Generate a unique schema for this test.
    schema_name = "discovery_" + uuid.uuid4().hex[:16]
    schema_identifier = sql.Identifier(schema_name)

    try:
        # ----------------------------------------
        # Create test schema and tables
        # ----------------------------------------
        with connection.cursor() as cursor:

            cursor.execute(
                sql.SQL("CREATE SCHEMA {}").format(
                    schema_identifier
                )
            )

            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE {}.customers (
                        tenant_id UUID NOT NULL,
                        customer_id UUID NOT NULL,
                        email TEXT NOT NULL,
                        PRIMARY KEY (
                            tenant_id,
                            customer_id
                        )
                    )
                    """
                ).format(schema_identifier)
            )

            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE {}.orders (
                        order_id UUID PRIMARY KEY,
                        tenant_id UUID NOT NULL,
                        customer_id UUID NOT NULL,
                        amount NUMERIC(12, 2),
                        FOREIGN KEY (
                            tenant_id,
                            customer_id
                        )
                        REFERENCES {}.customers (
                            tenant_id,
                            customer_id
                        )
                    )
                    """
                ).format(
                    schema_identifier,
                    schema_identifier,
                )
            )

        connection.commit()

        # ----------------------------------------
        # Discover database metadata
        # ----------------------------------------
        result = discover_postgres_schema(connection)

        tables = {
            (table["schema"], table["table"]): table
            for table in result["tables"]
        }

        customers = tables[(schema_name, "customers")]
        orders = tables[(schema_name, "orders")]

        # ----------------------------------------
        # Verify primary keys
        # ----------------------------------------
        assert customers["primary_keys"] == [
            "tenant_id",
            "customer_id",
        ]

        assert orders["primary_keys"] == [
            "order_id",
        ]

        # ----------------------------------------
        # Verify column metadata
        # ----------------------------------------
        columns = {
            column["name"]: column
            for column in orders["columns"]
        }

        assert columns["amount"]["nullable"] is True

        # ----------------------------------------
        # Verify composite foreign keys
        # ----------------------------------------
        foreign_keys = {
            (
                item["column"],
                item["referenced_schema"],
                item["referenced_table"],
                item["referenced_column"],
            )
            for item in orders["foreign_keys"]
        }

        assert (
            "tenant_id",
            schema_name,
            "customers",
            "tenant_id",
        ) in foreign_keys

        assert (
            "customer_id",
            schema_name,
            "customers",
            "customer_id",
        ) in foreign_keys

    finally:
        # Roll back any failed metadata query.
        connection.rollback()

        # Remove only the schema created by this test.
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "DROP SCHEMA IF EXISTS {} CASCADE"
                ).format(schema_identifier)
            )

        connection.commit()
