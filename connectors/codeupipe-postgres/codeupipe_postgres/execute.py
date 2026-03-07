"""
PostgresExecute: Run INSERT/UPDATE/DELETE with parameterized queries.

Reads 'sql' and 'params' from payload, returns 'affected_rows'.
"""

from codeupipe import Payload


class PostgresExecute:
    """Run a parameterized INSERT/UPDATE/DELETE and return affected count."""

    def __init__(self, conninfo: str):
        self._conninfo = conninfo

    async def call(self, payload: Payload) -> Payload:
        import psycopg

        sql = payload.get("sql", "")
        params = payload.get("params", None)

        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                affected = cur.rowcount
            conn.commit()

        return payload.insert("affected_rows", affected)
