from sqlalchemy import inspect, text

from app.db.session import engine


def test_database_connection():
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

    assert result == "insightflow"


def test_database_tables_exist():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    expected_tables = {
        "organizations",
        "users",
        "organization_memberships",
        "alembic_version",
    }

    assert expected_tables.issubset(tables)