"""
PostgresTransaction: Wrap multiple SQL operations in a single transaction.

Reads 'statements' (list of {sql, params}) from payload.
Returns 'results' (list of affected_rows per statement).
Rolls back all on any failure.
"""

from codeupipe import Payload


class PostgresTransaction:
    """Execute multiple statements in a single transaction."""

    def __init__(self, conninfo: str):
        self._conninfo = conninfo

    async def call(self, payload: Payload) -> Payload:
        import psycopg

        statements = payload.get("statements", [])
        results = []

        with psycopg.connect(self._conninfo) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    for stmt in statements:
                        sql = stmt.get("sql", "")
                        params = stmt.get("params", None)
                        cur.execute(sql, params)
                        results.append(cur.rowcount)

        return payload.insert("results", results)
