"""
PostgresQuery: Run parameterized SELECT queries.

Reads 'sql' and 'params' from payload, returns 'rows' and 'columns'.
"""

from codeupipe import Payload


class PostgresQuery:
    """Run a parameterized SELECT and return rows."""

    def __init__(self, conninfo: str):
        self._conninfo = conninfo

    async def call(self, payload: Payload) -> Payload:
        import psycopg

        sql = payload.get("sql", "")
        params = payload.get("params", None)

        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                columns = [desc.name for desc in cur.description] if cur.description else []
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        return payload.insert("rows", rows).insert("columns", columns)
