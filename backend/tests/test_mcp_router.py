"""
Tests for mcp_router.py — the routing + tool dispatch layer.
All LLM calls and agent executions are mocked.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from mcp_router import MCPRouter


def run(coro):
    return asyncio.run(coro)


def _mock_llm_response(tool_name="none", params=None, reasoning="test"):
    """Build a mock LLM response that returns a tool-selection JSON."""
    params = params or {}
    content = json.dumps({
        "tools": [{"tool": tool_name, "params": params}],
        "reasoning": reasoning,
    })
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


@pytest.fixture
def router():
    with patch("mcp_router.NVIDIAClient"):
        r = MCPRouter()
    return r


class TestDecideTools:
    def test_returns_none_tool_on_llm_failure(self, router):
        router.llm.chat = AsyncMock(side_effect=Exception("API error"))
        result = run(router._decide_tools("hello"))
        assert result["tools"][0]["tool"] == "none"

    def test_returns_none_tool_on_bad_json(self, router):
        mock_choice = MagicMock()
        mock_choice.message.content = "this is not json"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        router.llm.chat = AsyncMock(return_value=mock_resp)
        result = run(router._decide_tools("hello"))
        assert result["tools"][0]["tool"] == "none"

    def test_parses_web_search_decision(self, router):
        router.llm.chat = AsyncMock(return_value=_mock_llm_response(
            "web_search", {"query": "python tips"}
        ))
        result = run(router._decide_tools("search python tips"))
        assert result["tools"][0]["tool"] == "web_search"

    def test_parses_multi_tool_decision(self, router):
        content = json.dumps({
            "tools": [
                {"tool": "web_search", "params": {"query": "news"}},
                {"tool": "get_weather", "params": {"city": "NYC"}},
            ],
            "reasoning": "both needed",
        })
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        router.llm.chat = AsyncMock(return_value=mock_resp)
        result = run(router._decide_tools("news and weather in NYC"))
        assert len(result["tools"]) == 2

    def test_extracts_json_from_text_with_prose(self, router):
        """LLM sometimes wraps JSON in prose — should still be extracted."""
        content = 'Sure! Here is my decision:\n{"tools": [{"tool": "none", "params": {}}], "reasoning": "ok"}\nHope that helps!'
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        router.llm.chat = AsyncMock(return_value=mock_resp)
        result = run(router._decide_tools("hello"))
        assert result["tools"][0]["tool"] == "none"


class TestExecuteTool:
    def test_none_tool_returns_empty_string(self, router):
        result = run(router._execute_tool("none", {}))
        assert result == ""

    def test_unknown_tool_returns_error_message(self, router):
        result = run(router._execute_tool("flying_unicorn", {}))
        assert "Unknown tool" in result

    def test_web_search_called(self, router):
        router.web_search.search = AsyncMock(return_value="search results")
        result = run(router._execute_tool("web_search", {"query": "pytest"}))
        assert result == "search results"
        router.web_search.search.assert_called_once_with("pytest")

    def test_get_weather_called(self, router):
        router.weather.get_weather = AsyncMock(return_value="sunny in London")
        result = run(router._execute_tool("get_weather", {"city": "London"}))
        assert result == "sunny in London"
        router.weather.get_weather.assert_called_once_with("London")

    def test_get_news_called(self, router):
        router.weather.get_news = AsyncMock(return_value="latest news")
        result = run(router._execute_tool("get_news", {}))
        assert result == "latest news"

    def test_read_file_called(self, router):
        router.file_handler.read_file = AsyncMock(return_value="file content")
        result = run(router._execute_tool("read_file", {"filename": "test.txt"}))
        assert result == "file content"

    def test_list_files_called(self, router):
        router.file_handler.list_files = AsyncMock(return_value="file list")
        result = run(router._execute_tool("list_files", {}))
        assert result == "file list"

    def test_db_query_called(self, router):
        router.db_query.query = AsyncMock(return_value="db rows")
        result = run(router._execute_tool("db_query", {"sql": "SELECT 1"}))
        assert result == "db rows"

    def test_run_code_called(self, router):
        router.code_runner.execute = AsyncMock(return_value="code output")
        result = run(router._execute_tool("run_code", {"code": "print(1)"}))
        assert result == "code output"

    def test_tool_exception_returns_error_string(self, router):
        router.web_search.search = AsyncMock(side_effect=RuntimeError("crash"))
        result = run(router._execute_tool("web_search", {"query": "test"}))
        assert "Tool 'web_search' error" in result

    def test_missing_params_use_defaults(self, router):
        """Calling with empty params should use .get() defaults gracefully."""
        router.web_search.search = AsyncMock(return_value="ok")
        result = run(router._execute_tool("web_search", {}))
        # Should call search with empty string (default), not crash
        router.web_search.search.assert_called_once_with("")


class TestRoute:
    def test_route_returns_expected_keys(self, router):
        router.llm.chat = AsyncMock(return_value=_mock_llm_response())
        result = run(router.route("hello", []))
        assert "tool_decision" in result
        assert "tool_results" in result

    def test_route_tool_results_is_list(self, router):
        router.llm.chat = AsyncMock(return_value=_mock_llm_response())
        result = run(router.route("hello", []))
        assert isinstance(result["tool_results"], list)

    def test_route_each_result_has_tool_params_result(self, router):
        router.llm.chat = AsyncMock(return_value=_mock_llm_response(
            "web_search", {"query": "test"}
        ))
        router.web_search.search = AsyncMock(return_value="results")
        result = run(router.route("search test", []))
        tr = result["tool_results"][0]
        assert "tool" in tr
        assert "params" in tr
        assert "result" in tr

    def test_route_history_not_sent_to_tool_decider(self, router):
        """History is accepted but _decide_tools only uses user_message."""
        router.llm.chat = AsyncMock(return_value=_mock_llm_response())
        run(router.route("hello", [{"role": "user", "content": "prev"}]))
        # Should not raise
        router.llm.chat.assert_called_once()

    def test_route_no_tools_returns_none_entry(self, router):
        """Fallback when LLM fails returns none tool."""
        router.llm.chat = AsyncMock(side_effect=Exception("fail"))
        result = run(router.route("hello", []))
        assert result["tool_results"][0]["tool"] == "none"
