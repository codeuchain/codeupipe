"""
Unit tests for codeupipe-postgres connector.

All tests mock psycopg via sys.modules — no pip install needed.
"""

import asyncio
import sys
from types import SimpleNamespace, ModuleType
from unittest.mock import MagicMock

import pytest

from codeupipe import Payload


# ── Module-level mocks for psycopg ──────────────────────────────────

_mock_psycopg = MagicMock()
_mock_psycopg.__name__ = "psycopg"
_mock_psycopg.__spec__ = None

_mock_psycopg_sql = MagicMock()
_mock_psycopg.sql = _mock_psycopg_sql


@pytest.fixture(autouse=True)
def mock_psycopg_module():
    """Inject mock psycopg into sys.modules for all tests."""
    originals = {}
    for mod in ("psycopg", "psycopg.sql"):
        originals[mod] = sys.modules.get(mod)

    sys.modules["psycopg"] = _mock_psycopg
    sys.modules["psycopg.sql"] = _mock_psycopg_sql
    _mock_psycopg.reset_mock()
    _mock_psycopg_sql.reset_mock()
    _mock_psycopg.sql = _mock_psycopg_sql
    yield

    for mod, orig in originals.items():
        if orig is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = orig
    for key in list(sys.modules):
        if key.startswith("codeupipe_postgres"):
            del sys.modules[key]


def make_mock_cursor(rows=None, columns=None, rowcount=0):
    cur = MagicMock()
    if columns:
        cur.description = [SimpleNamespace(name=c) for c in columns]
    else:
        cur.description = None
    cur.fetchall.return_value = rows or []
    cur.rowcount = rowcount
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    return cur


def make_mock_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    tx = MagicMock()
    tx.__enter__ = MagicMock(return_value=tx)
    tx.__exit__ = MagicMock(return_value=False)
    conn.transaction.return_value = tx
    return conn


# ── PostgresQuery ───────────────────────────────────────────────────


class TestPostgresQuery:
    def test_select_returns_rows(self):
        from codeupipe_postgres.query import PostgresQuery

        cur = make_mock_cursor(rows=[(1, "Alice"), (2, "Bob")], columns=["id", "name"])
        conn = make_mock_conn(cur)
        _mock_psycopg.connect.return_value = conn

        f = PostgresQuery(conninfo="postgresql://test")
        payload = Payload({"sql": "SELECT id, name FROM users", "params": None})
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))

        rows = result.get("rows")
        assert len(rows) == 2
        assert rows[0] == {"id": 1, "name": "Alice"}
        assert result.get("columns") == ["id", "name"]

    def test_parameterized_query(self):
        from codeupipe_postgres.query import PostgresQuery

        cur = make_mock_cursor(rows=[(5,)], columns=["count"])
        conn = make_mock_conn(cur)
        _mock_psycopg.connect.return_value = conn

        f = PostgresQuery(conninfo="postgresql://test")
        payload = Payload({"sql": "SELECT count(*) FROM users WHERE active = %s", "params": (True,)})
        asyncio.get_event_loop().run_until_complete(f.call(payload))
        cur.execute.assert_called_once_with(
            "SELECT count(*) FROM users WHERE active = %s", (True,)
        )


# ── PostgresExecute ─────────────────────────────────────────────────


class TestPostgresExecute:
    def test_insert_returns_affected(self):
        from codeupipe_postgres.execute import PostgresExecute

        cur = make_mock_cursor(rowcount=1)
        conn = make_mock_conn(cur)
        _mock_psycopg.connect.return_value = conn

        f = PostgresExecute(conninfo="postgresql://test")
        payload = Payload({"sql": "INSERT INTO users (name) VALUES (%s)", "params": ("Alice",)})
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))

        assert result.get("affected_rows") == 1
        conn.commit.assert_called_once()


# ── PostgresTransaction ─────────────────────────────────────────────


class TestPostgresTransaction:
    def test_multiple_statements(self):
        from codeupipe_postgres.transaction import PostgresTransaction

        cur = make_mock_cursor(rowcount=1)
        conn = make_mock_conn(cur)
        _mock_psycopg.connect.return_value = conn

        f = PostgresTransaction(conninfo="postgresql://test")
        payload = Payload({
            "statements": [
                {"sql": "INSERT INTO a (x) VALUES (%s)", "params": (1,)},
                {"sql": "UPDATE b SET y = %s", "params": (2,)},
            ],
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))

        assert result.get("results") == [1, 1]
        assert cur.execute.call_count == 2


# ── PostgresBulkInsert ──────────────────────────────────────────────


class TestPostgresBulkInsert:
    def test_bulk_insert(self):
        from codeupipe_postgres.bulk_insert import PostgresBulkInsert

        cur = make_mock_cursor()
        conn = make_mock_conn(cur)
        _mock_psycopg.connect.return_value = conn

        # Setup SQL composable mocks
        _mock_psycopg_sql.Identifier.side_effect = lambda x: x
        _mock_psycopg_sql.Placeholder.return_value = "%s"
        mock_joined = MagicMock()
        _mock_psycopg_sql.SQL.return_value.join.return_value = mock_joined
        _mock_psycopg_sql.SQL.return_value.format.return_value = "INSERT mocked"

        f = PostgresBulkInsert(conninfo="postgresql://test")
        payload = Payload({
            "table": "users",
            "columns": ["name", "email"],
            "rows": [("Alice", "a@x.com"), ("Bob", "b@x.com")],
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))

        assert result.get("inserted_count") == 2
        conn.commit.assert_called_once()
