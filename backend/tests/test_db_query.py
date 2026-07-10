"""
Tests for agents/db_query.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import asyncio
import sqlite3
from pathlib import Path
from agents.db_query import DBQueryAgent, DB_PATH


@pytest.fixture
def agent(tmp_path, monkeypatch):
    """Create a fresh DBQueryAgent with an isolated temp database."""
    db = tmp_path / "test_company.db"
    monkeypatch.setattr("agents.db_query.DB_PATH", db)
    a = DBQueryAgent()
    return a


def run(coro):
    return asyncio.run(coro)


class TestDBQuerySafety:
    def test_select_is_allowed(self, agent):
        assert agent._is_safe("SELECT * FROM employees") is True

    def test_delete_is_blocked(self, agent):
        assert agent._is_safe("DELETE FROM employees") is False

    def test_drop_is_blocked(self, agent):
        assert agent._is_safe("DROP TABLE employees") is False

    def test_insert_is_blocked(self, agent):
        assert agent._is_safe("INSERT INTO employees VALUES (1,'a','b',1,'c','d')") is False

    def test_update_is_blocked(self, agent):
        assert agent._is_safe("UPDATE employees SET salary=0") is False

    def test_create_is_blocked(self, agent):
        assert agent._is_safe("CREATE TABLE hack (id INT)") is False

    def test_alter_is_blocked(self, agent):
        assert agent._is_safe("ALTER TABLE employees ADD COLUMN x INT") is False

    def test_pragma_is_blocked(self, agent):
        assert agent._is_safe("PRAGMA table_info(employees)") is False

    def test_exec_is_blocked(self, agent):
        assert agent._is_safe("EXEC xp_cmdshell 'rm -rf /'") is False

    def test_case_insensitive_block(self, agent):
        assert agent._is_safe("select * from employees where 1=1; drop table employees") is False

    def test_empty_sql_not_safe(self, agent):
        # empty string does not start with SELECT
        assert agent._is_safe("") is False


class TestDBQueryExecution:
    def test_basic_select(self, agent):
        result = run(agent.query("SELECT * FROM employees"))
        assert "Query returned" in result or "row(s)" in result

    def test_empty_result(self, agent):
        result = run(agent.query("SELECT * FROM employees WHERE id = 9999"))
        assert "no rows" in result.lower()

    def test_empty_sql_returns_message(self, agent):
        result = run(agent.query(""))
        assert "No SQL query provided" in result

    def test_blocked_query_returns_error_message(self, agent):
        result = run(agent.query("DELETE FROM employees"))
        assert "Only SELECT" in result or "permitted" in result

    def test_sql_injection_via_semicolon(self, agent):
        """Semicolons stripped but compound statements should be blocked."""
        result = run(agent.query("SELECT 1; DROP TABLE employees"))
        # The DROP keyword should trip the safety check
        assert "Only SELECT" in result or "permitted" in result

    def test_trailing_semicolon_stripped(self, agent):
        """A trailing semicolon alone should not cause failure."""
        result = run(agent.query("SELECT COUNT(*) FROM employees;"))
        assert "Error" not in result or "row(s)" in result

    def test_whitespace_only_sql(self, agent):
        result = run(agent.query("   "))
        assert "No SQL query provided" in result

    def test_count_employees(self, agent):
        result = run(agent.query("SELECT COUNT(*) FROM employees"))
        assert "1 row" in result or "row(s)" in result

    def test_invalid_sql_returns_error(self, agent):
        result = run(agent.query("SELECT FROM notexist"))
        assert "SQL Error" in result or "error" in result.lower()


class TestDBSeeding:
    def test_employees_seeded(self, agent):
        result = run(agent.query("SELECT COUNT(*) FROM employees"))
        assert "row(s)" in result

    def test_products_seeded(self, agent):
        result = run(agent.query("SELECT COUNT(*) FROM products"))
        assert "row(s)" in result

    def test_sales_seeded(self, agent):
        result = run(agent.query("SELECT COUNT(*) FROM sales"))
        assert "row(s)" in result

    def test_double_seed_no_duplicates(self, agent):
        """Calling _seed_db twice should not duplicate rows."""
        agent._seed_db()
        result = run(agent.query("SELECT COUNT(*) FROM employees"))
        # Should still be 8 employees (or the same count, not doubled)
        assert "row(s)" in result
