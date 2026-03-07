"""
codeupipe-postgres: PostgreSQL connector package.

Filters:
- PostgresQuery: Run parameterized SELECT, return rows
- PostgresExecute: Run INSERT/UPDATE/DELETE, return affected count
- PostgresTransaction: Wrap N operations in a transaction
- PostgresBulkInsert: Batch insert rows efficiently
"""

from .query import PostgresQuery
from .execute import PostgresExecute
from .transaction import PostgresTransaction
from .bulk_insert import PostgresBulkInsert


def register(registry, config):
    """Entry point called by codeupipe discover_connectors."""
    conninfo = config.resolve_env("connection_string_env")

    registry.register(
        f"{config.name}_query",
        lambda: PostgresQuery(conninfo=conninfo),
        kind="connector",
        force=True,
    )
    registry.register(
        f"{config.name}_execute",
        lambda: PostgresExecute(conninfo=conninfo),
        kind="connector",
        force=True,
    )
    registry.register(
        f"{config.name}_transaction",
        lambda: PostgresTransaction(conninfo=conninfo),
        kind="connector",
        force=True,
    )
    registry.register(
        f"{config.name}_bulk_insert",
        lambda: PostgresBulkInsert(conninfo=conninfo),
        kind="connector",
        force=True,
    )


__all__ = [
    "register",
    "PostgresQuery",
    "PostgresExecute",
    "PostgresTransaction",
    "PostgresBulkInsert",
]
