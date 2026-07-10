"""
agents/db_query.py — SQLite Database Query Agent
Pre-populated with a realistic demo company dataset.
Only SELECT queries are allowed for safety.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("data") / "company.db"


class DBQueryAgent:
    def __init__(self):
        DB_PATH.parent.mkdir(exist_ok=True)
        self._seed_db()

    # ------------------------------------------------------------------
    # DB setup
    # ------------------------------------------------------------------
    def _seed_db(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS employees (
            id         INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            department TEXT NOT NULL,
            salary     REAL NOT NULL,
            hire_date  TEXT NOT NULL,
            email      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id       INTEGER PRIMARY KEY,
            name     TEXT NOT NULL,
            category TEXT NOT NULL,
            price    REAL NOT NULL,
            stock    INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sales (
            id          INTEGER PRIMARY KEY,
            product_id  INTEGER REFERENCES products(id),
            employee_id INTEGER REFERENCES employees(id),
            quantity    INTEGER NOT NULL,
            sale_date   TEXT NOT NULL,
            total       REAL NOT NULL
        );
        """)
        if c.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            c.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?)", [
                (1, "Alice Johnson",   "Engineering", 95000,  "2020-01-15", "alice@acme.com"),
                (2, "Bob Smith",       "Marketing",   75000,  "2019-03-20", "bob@acme.com"),
                (3, "Carol Davis",     "Engineering", 105000, "2018-06-01", "carol@acme.com"),
                (4, "David Wilson",    "Sales",        80000, "2021-09-10", "david@acme.com"),
                (5, "Eve Martinez",    "HR",           70000, "2022-01-05", "eve@acme.com"),
                (6, "Frank Brown",     "Engineering",  98000, "2019-11-15", "frank@acme.com"),
                (7, "Grace Lee",       "Marketing",    82000, "2020-07-22", "grace@acme.com"),
                (8, "Henry Taylor",    "Sales",        88000, "2018-12-01", "henry@acme.com"),
            ])
            c.executemany("INSERT INTO products VALUES (?,?,?,?,?)", [
                (1, "AI Analytics Suite",   "Software", 2999.99, 50),
                (2, "Cloud Storage Pro",    "Software",  499.99, 200),
                (3, "Security Shield",      "Software", 1499.99, 75),
                (4, "Data Processor X1",   "Hardware", 3500.00, 25),
                (5, "Smart Router Pro",    "Hardware",  899.99, 60),
            ])
            c.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?)", [
                (1, 1, 4,  3, "2024-01-10",  8999.97),
                (2, 2, 8, 10, "2024-01-15",  4999.90),
                (3, 3, 4,  2, "2024-02-01",  2999.98),
                (4, 1, 8,  5, "2024-02-14", 14999.95),
                (5, 4, 4,  1, "2024-03-01",  3500.00),
                (6, 5, 8,  3, "2024-03-10",  2699.97),
                (7, 2, 4, 15, "2024-04-01",  7499.85),
                (8, 1, 8,  2, "2024-04-20",  5999.98),
            ])
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------
    def _is_safe(self, sql: str) -> bool:
        upper = sql.strip().upper()
        if not upper.startswith("SELECT"):
            return False
        blocked = {"DROP", "DELETE", "INSERT", "UPDATE", "CREATE", "ALTER", "EXEC", "PRAGMA"}
        for kw in blocked:
            if kw in upper:
                return False
        return True

    async def query(self, sql: str) -> str:
        sql = sql.strip().rstrip(";")
        if not sql:
            return "No SQL query provided."
        if not self._is_safe(sql):
            return "⛔ Only SELECT queries are permitted. Please ask a read-only question."
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(sql)
            rows = c.fetchall()
            conn.close()

            if not rows:
                return "✅ Query executed — no rows returned."

            cols = rows[0].keys()
            header = " | ".join(cols)
            sep = "-" * max(len(header), 40)
            data_rows = [" | ".join(str(row[col]) for col in cols) for row in rows]
            table = f"```\n{header}\n{sep}\n" + "\n".join(data_rows) + "\n```"
            return f"📊 **Query returned {len(rows)} row(s):**\n\n{table}"
        except sqlite3.Error as exc:
            return f"❌ SQL Error: {exc}"

    def get_schema(self) -> str:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        tables = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        schema_parts = []
        for (table,) in tables:
            cols = c.execute(f"PRAGMA table_info({table})").fetchall()
            col_str = ", ".join(f"{col[1]} ({col[2]})" for col in cols)
            schema_parts.append(f"**{table}**: {col_str}")
        conn.close()
        return "\n".join(schema_parts)
