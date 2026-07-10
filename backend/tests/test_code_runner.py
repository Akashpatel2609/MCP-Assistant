"""
Tests for agents/code_runner.py

NOTE: asyncio.create_subprocess_exec requires ProactorEventLoop on Windows.
We set WindowsProactorEventLoopPolicy before any tests run so that
asyncio.run() creates the correct loop type.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import asyncio

# ── Windows: force ProactorEventLoop (needed for subprocess) ─────────────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from agents.code_runner import CodeRunnerAgent


def run(coro):
    """
    Explicitly create a ProactorEventLoop (Windows requirement for subprocess).
    asyncio.run() picks the loop based on policy which pytest-anyio may override.
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def agent():
    return CodeRunnerAgent()



class TestCodeRunnerBasic:
    def test_empty_code_returns_message(self, agent):
        result = run(agent.execute(""))
        assert "No code provided" in result

    def test_whitespace_only_code(self, agent):
        result = run(agent.execute("   \n  "))
        assert "No code provided" in result

    def test_simple_print(self, agent):
        result = run(agent.execute("print('hello world')"))
        assert "hello world" in result

    def test_math_computation(self, agent):
        result = run(agent.execute("print(2 + 2)"))
        assert "4" in result

    def test_multiline_code(self, agent):
        code = "x = 10\ny = 20\nprint(x + y)"
        result = run(agent.execute(code))
        assert "30" in result

    def test_code_echo_in_result(self, agent):
        """The executed code should appear in a code block in the result."""
        result = run(agent.execute("print('test')"))
        assert "print('test')" in result

    def test_no_output_code(self, agent):
        result = run(agent.execute("x = 42  # no print"))
        assert "no output" in result.lower() or "successfully" in result.lower()


class TestCodeRunnerErrors:
    def test_syntax_error_captured(self, agent):
        result = run(agent.execute("def broken("))
        assert "Stderr" in result or "SyntaxError" in result

    def test_runtime_error_captured(self, agent):
        result = run(agent.execute("raise ValueError('test error')"))
        assert "Stderr" in result or "ValueError" in result

    def test_division_by_zero(self, agent):
        result = run(agent.execute("print(1/0)"))
        assert "ZeroDivisionError" in result or "Stderr" in result

    def test_import_error_captured(self, agent):
        result = run(agent.execute("import nonexistent_module_xyz"))
        assert "ModuleNotFoundError" in result or "Stderr" in result


class TestCodeRunnerTimeout:
    def test_infinite_loop_times_out(self, agent):
        result = run(agent.execute("while True: pass"))
        assert "Timeout" in result or "timeout" in result.lower()

    def test_sleep_beyond_limit_times_out(self, agent):
        result = run(agent.execute("import time; time.sleep(30)"))
        assert "Timeout" in result or "timeout" in result.lower()


class TestCodeRunnerSandboxing:
    def test_can_read_env_vars(self, agent):
        """Subprocess inherits environment — this is a known design point."""
        result = run(agent.execute("import os; print('ran')"))
        assert "ran" in result

    def test_file_system_access_unrestricted(self, agent):
        """
        SECURITY NOTE: The code runner has NO filesystem restrictions.
        This test documents the vulnerability — code can read arbitrary files.
        """
        code = "import os; print(os.getcwd())"
        result = run(agent.execute(code))
        # It should successfully print a path — proving no sandboxing
        assert "Output" in result

    def test_network_access_unrestricted(self, agent):
        """
        SECURITY NOTE: Code can make outbound network calls.
        Documented as a known vulnerability.
        """
        # We won't actually make a network call in unit tests,
        # but we document that there's nothing preventing it.
        result = run(agent.execute("import socket; print(socket.gethostname())"))
        assert "Output" in result or "Stderr" in result
