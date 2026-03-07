"""
PostgresBulkInsert: Batch insert rows efficiently.

Reads 'table', 'columns', and 'rows' from payload.
Returns 'inserted_count'.
"""

from codeupipe import Payload


class PostgresBulkInsert:
    """Batch insert rows into a table."""

    def __init__(self, conninfo: str):
        self._conninfo = conninfo

    async def call(self, payload: Payload) -> Payload:
        import psycopg
        from psycopg import sql as psycopg_sql

        table = payload.get("table", "")
        columns = payload.get("columns", [])
        rows = payload.get("rows", [])

        col_ids = [psycopg_sql.Identifier(c) for c in columns]
        placeholders = psycopg_sql.SQL(", ").join(
            [psycopg_sql.Placeholder()] * len(columns)
        )
        query = psycopg_sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            psycopg_sql.Identifier(table),
            psycopg_sql.SQL(", ").join(col_ids),
            placeholders,
        )

        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cur:
                cur.executemany(query, rows)
                count = len(rows)
            conn.commit()

        return payload.insert("inserted_count", count)
