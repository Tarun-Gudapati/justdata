"""Database layer. Works with either SQLite (demo) or SQL Server (real).

Which one is chosen by .env:
    DB_KIND=sqlite   (default)  -> uses the local demo.db
    DB_KIND=mssql               -> uses MSSQL_CONN_STR (a read-only user!)
"""
import os
import re
from collections import OrderedDict

import sqlite3

from dotenv import load_dotenv

load_dotenv()

DB_KIND = os.getenv("DB_KIND", "sqlite").lower()
DB_FILE = os.getenv("SQLITE_FILE", "demo.db")
MSSQL_CONN_STR = os.getenv("MSSQL_CONN_STR", "")

# Guardrails for pointing at a live database: a broad question must not be able
# to drag a whole table into memory or sit on the server for minutes.
MAX_ROWS = int(os.getenv("MAX_ROWS", "500"))
QUERY_TIMEOUT = int(os.getenv("QUERY_TIMEOUT", "30"))  # seconds, SQL Server only


def get_dialect() -> str:
    """The SQL flavour to tell Claude to write."""
    return "T-SQL for Microsoft SQL Server" if DB_KIND == "mssql" else "SQLite"


def describe_source() -> str:
    """Short id for the active database, e.g. "mssql:myserver/MyDatabase".

    The vector index is stamped with this so switching databases can be
    detected and the old vectors thrown away.
    """
    if DB_KIND == "mssql":
        server = re.search(r"SERVER=([^;]+)", MSSQL_CONN_STR, re.IGNORECASE)
        database = re.search(r"DATABASE=([^;]+)", MSSQL_CONN_STR, re.IGNORECASE)
        return (f"mssql:{server.group(1).strip() if server else '?'}"
                f"/{database.group(1).strip() if database else '?'}")
    return f"sqlite:{DB_FILE}"


def _connect():
    if DB_KIND == "mssql":
        import pyodbc  # imported lazily so SQLite mode needs no driver

        if not MSSQL_CONN_STR:
            raise RuntimeError("DB_KIND=mssql but MSSQL_CONN_STR is not set in .env")
        conn = pyodbc.connect(MSSQL_CONN_STR, timeout=QUERY_TIMEOUT)
        conn.timeout = QUERY_TIMEOUT  # cancel queries that run too long
        conn.autocommit = True        # don't hold a read transaction open
        return conn
    return sqlite3.connect(DB_FILE)


# ---------------------------------------------------------------------------
# Demo data (SQLite only)
# ---------------------------------------------------------------------------
def setup_database():
    """Create the SQLite demo DB. Not used in SQL Server mode."""
    conn = sqlite3.connect(DB_FILE)
    conn.executescript("""
        DROP TABLE IF EXISTS payments;
        DROP TABLE IF EXISTS loans;
        DROP TABLE IF EXISTS employees;
        DROP TABLE IF EXISTS loan_products;
        DROP TABLE IF EXISTS customers;
        DROP TABLE IF EXISTS branches;

        CREATE TABLE branches (
            id       INTEGER PRIMARY KEY,
            name     TEXT NOT NULL,
            city     TEXT NOT NULL
        );

        CREATE TABLE customers (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE loan_products (
            id              INTEGER PRIMARY KEY,
            name            TEXT NOT NULL,
            interest_rate   REAL NOT NULL,
            max_amount      REAL NOT NULL
        );

        CREATE TABLE loans (
            id           INTEGER PRIMARY KEY,
            customer_id  INTEGER NOT NULL,
            amount       REAL NOT NULL,
            status       INTEGER NOT NULL,   -- 1 = pending, 3 = funded
            funded_at    TEXT
        );

        CREATE TABLE employees (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            branch_id   INTEGER NOT NULL,
            role        TEXT NOT NULL   -- officer, manager, underwriter
        );

        CREATE TABLE payments (
            id          INTEGER PRIMARY KEY,
            loan_id     INTEGER NOT NULL,
            amount      REAL NOT NULL,
            paid_at     TEXT NOT NULL
        );

        INSERT INTO branches (name, city) VALUES
            ('Downtown', 'Austin'),
            ('Northside', 'Dallas'),
            ('Riverside', 'Houston');

        INSERT INTO customers (name, created_at) VALUES
            ('Alice', '2026-05-01'),
            ('Bob',   '2026-05-15'),
            ('Carol', '2026-06-02');

        INSERT INTO loan_products (name, interest_rate, max_amount) VALUES
            ('Personal Loan', 9.5, 25000),
            ('Auto Loan',     6.2, 40000),
            ('Home Equity',   7.1, 150000);

        INSERT INTO loans (customer_id, amount, status, funded_at) VALUES
            (1,  5000, 3, '2026-05-20'),
            (2, 12000, 3, '2026-06-10'),
            (3,  8000, 1, NULL);

        INSERT INTO employees (name, branch_id, role) VALUES
            ('Priya', 1, 'officer'),
            ('Sam',   1, 'manager'),
            ('Lee',   2, 'officer'),
            ('Maya',  3, 'underwriter');

        INSERT INTO payments (loan_id, amount, paid_at) VALUES
            (1, 500,  '2026-06-20'),
            (1, 500,  '2026-07-20'),
            (2, 1000, '2026-07-10'),
            (4, 2000, '2026-07-15');
    """)
    conn.commit()
    conn.close()
    print("Database created with sample data.")


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
# Active connection for the in-flight user query — Stop calls interrupt/cancel.
_active_conn = None


def cancel_active_query():
    """Best-effort cancel of the SQL currently running (if any)."""
    conn = _active_conn
    if conn is None:
        return
    try:
        if DB_KIND == "mssql":
            conn.cancel()
        else:
            conn.interrupt()
    except Exception:  # noqa: BLE001 - cancel is best-effort
        pass


def run_query(sql, max_rows=None, cancel_event=None):
    """Run SQL, return (column_names, rows, truncated). Rows are plain tuples.

    At most `max_rows` rows are returned (default MAX_ROWS; pass 0 for no cap,
    which the schema-discovery queries below do).
    """
    global _active_conn
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Stopped.")

    limit = MAX_ROWS if max_rows is None else max_rows
    conn = _connect()
    _active_conn = conn
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Stopped.")
        columns = [d[0] for d in cursor.description] if cursor.description else []
        if limit:
            # One extra row tells us whether there were more behind the cap.
            fetched = cursor.fetchmany(limit + 1)
            truncated = len(fetched) > limit
            rows = [tuple(r) for r in fetched[:limit]]
        else:
            rows = [tuple(r) for r in cursor.fetchall()]
            truncated = False
        return columns, rows, truncated
    finally:
        _active_conn = None
        conn.close()


def run_sql(sql):
    """Backwards-compatible helper: return only the rows."""
    _columns, rows, _truncated = run_query(sql)
    return rows


# ---------------------------------------------------------------------------
# Schema discovery (used by the vector store)
# ---------------------------------------------------------------------------
def _sqlite_table_schemas():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


_MSSQL_FK_SQL = """
    SELECT SCHEMA_NAME(ct.schema_id) + '.' + ct.name AS child_table,
           cc.name AS child_column,
           SCHEMA_NAME(pt.schema_id) + '.' + pt.name AS parent_table,
           pc.name AS parent_column
    FROM sys.foreign_key_columns fkc
    JOIN sys.tables  ct ON ct.object_id = fkc.parent_object_id
    JOIN sys.columns cc ON cc.object_id = fkc.parent_object_id
                       AND cc.column_id = fkc.parent_column_id
    JOIN sys.tables  pt ON pt.object_id = fkc.referenced_object_id
    JOIN sys.columns pc ON pc.object_id = fkc.referenced_object_id
                       AND pc.column_id = fkc.referenced_column_id
    ORDER BY child_table, child_column
"""


def _mssql_relationships():
    """{table: [fk description, ...]} covering both ends of each relationship.

    Without this the model has to guess join conditions from column names,
    which is where most plausible-but-wrong queries come from.
    """
    try:
        _cols, rows, _truncated = run_query(_MSSQL_FK_SQL, max_rows=0)
    except Exception:  # noqa: BLE001 - a locked-down login may not see sys views
        return {}

    relationships = {}
    for child, child_col, parent, parent_col in rows:
        line = f"--   {child}.{child_col} -> {parent}.{parent_col}"
        for table in (child, parent):
            lines = relationships.setdefault(table, [])
            if line not in lines:
                lines.append(line)
    return relationships


def _mssql_table_schemas():
    """Build a CREATE TABLE-style string per table from INFORMATION_SCHEMA."""
    _cols, rows, _truncated = run_query(
        """
        SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE,
               CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        """,
        max_rows=0,
    )

    tables = OrderedDict()
    for schema, table, col, dtype, maxlen, nullable in rows:
        tables.setdefault(f"{schema}.{table}", []).append((col, dtype, maxlen, nullable))

    relationships = _mssql_relationships()

    result = []
    for name, coldefs in tables.items():
        lines = []
        for col, dtype, maxlen, nullable in coldefs:
            typ = dtype
            if maxlen and dtype.lower() in ("varchar", "nvarchar", "char", "nchar"):
                typ = f"{dtype}({maxlen})"
            null = "" if str(nullable).upper() == "YES" else " NOT NULL"
            lines.append(f"    {col} {typ}{null}")
        text = f"CREATE TABLE {name} (\n" + ",\n".join(lines) + "\n);"
        if name in relationships:
            text += "\n-- foreign keys:\n" + "\n".join(relationships[name])
        result.append((name, text))
    return result


def get_table_schemas():
    """Return [(table_name, create_table_text), ...] for the active database."""
    if DB_KIND == "mssql":
        return _mssql_table_schemas()
    return _sqlite_table_schemas()


def get_schema():
    """The full schema as one string (all tables)."""
    return "\n\n".join(sql for _name, sql in get_table_schemas())


if __name__ == "__main__":
    if DB_KIND == "sqlite":
        setup_database()
    else:
        print(f"DB_KIND={DB_KIND}; found {len(get_table_schemas())} tables.")
