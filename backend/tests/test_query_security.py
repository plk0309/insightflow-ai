
import pytest

from app.core.query_security import (
    UnsafeQueryError,
    validate_read_only_query,
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM customers",
        "SELECT id, name FROM customers WHERE id = 1",
        "SELECT COUNT(*) FROM orders",
        "SELECT * FROM customers LIMIT 10",
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
        "SELECT id FROM customers UNION SELECT id FROM suppliers",
        "SELECT id FROM customers INTERSECT SELECT id FROM suppliers",
        "SELECT id FROM customers EXCEPT SELECT id FROM suppliers",
    ],
)
def test_read_only_queries_allowed(sql):
    assert validate_read_only_query(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO customers (id) VALUES (1)",
        "UPDATE customers SET name = 'Changed'",
        "DELETE FROM customers",
        "DROP TABLE customers",
        "CREATE TABLE unsafe_table (id INT)",
        "ALTER TABLE customers ADD COLUMN secret TEXT",
        "TRUNCATE TABLE customers",
        "SELECT * INTO new_customers FROM customers",
    ],
)
def test_write_queries_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_query(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DELETE FROM customers",
        "SELECT 1; DROP TABLE customers",
        "SELECT 1; SELECT 2",
    ],
)
def test_multiple_statements_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_query(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "WITH changed AS (DELETE FROM customers RETURNING id) SELECT * FROM changed",
        "WITH changed AS (UPDATE customers SET name = 'x' RETURNING id) SELECT * FROM changed",
    ],
)
def test_writes_inside_ctes_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_query(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM customers FOR UPDATE",
        "SELECT * FROM customers FOR SHARE",
    ],
)
def test_locking_queries_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_query(sql)


def test_empty_query_rejected():
    with pytest.raises(UnsafeQueryError):
        validate_read_only_query("   ")


def test_non_string_query_rejected():
    with pytest.raises(UnsafeQueryError):
        validate_read_only_query(None)


def test_oversized_query_rejected():
    with pytest.raises(UnsafeQueryError):
        validate_read_only_query(
            "SELECT " + "1" * 20_001
        )


def test_invalid_sql_rejected():
    with pytest.raises(UnsafeQueryError):
        validate_read_only_query(
            "SELECT FROM WHERE"
        )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sleep(10)",
        "SELECT pg_advisory_lock(123)",
        "SELECT pg_try_advisory_lock(123)",
        "SELECT pg_terminate_backend(123)",
        "SELECT pg_cancel_backend(123)",
        "SELECT set_config('search_path', 'public', false)",
        "SELECT nextval('orders_id_seq')",
        "SELECT setval('orders_id_seq', 100)",
        "SELECT lo_import('/etc/passwd')",
        "SELECT dblink_exec('connection', 'DELETE FROM users')",
    ],
)
def test_dangerous_postgres_functions_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_query(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM orders",
        "SELECT SUM(amount) FROM orders",
        "SELECT AVG(amount) FROM orders",
        "SELECT LOWER(name) FROM customers",
        "SELECT COALESCE(name, 'Unknown') FROM customers",
    ],
)
def test_common_analytics_functions_allowed(sql):
    assert validate_read_only_query(sql) == sql


def test_dangerous_function_inside_cte_rejected():
    sql = (
        "WITH delayed AS (SELECT pg_sleep(10)) "
        "SELECT * FROM delayed"
    )

    with pytest.raises(UnsafeQueryError):
        validate_read_only_query(sql)
