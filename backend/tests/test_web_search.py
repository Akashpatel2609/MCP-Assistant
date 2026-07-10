"""
Tests for agents/web_search.py — mocks DDGS to avoid live network calls.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from agents.web_search import WebSearchAgent


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def agent():
    return WebSearchAgent()


class TestWebSearch:
    def test_empty_query_returns_message(self, agent):
        result = run(agent.search(""))
        assert "No search query provided" in result

    def test_whitespace_query_returns_message(self, agent):
        result = run(agent.search("   "))
        assert "No search query provided" in result

    def test_successful_search(self, agent):
        mock_results = [
            {"title": "Test Title", "body": "Test body text.", "href": "https://example.com"},
        ]
        with patch("agents.web_search.DDGS") as MockDDGS:
            MockDDGS.return_value.text.return_value = mock_results
            result = run(agent.search("test query"))
        assert "Test Title" in result
        assert "example.com" in result

    def test_no_results_returns_message(self, agent):
        with patch("agents.web_search.DDGS") as MockDDGS:
            MockDDGS.return_value.text.return_value = []
            result = run(agent.search("something obscure"))
        assert "No results found" in result

    def test_search_exception_handled(self, agent):
        with patch("agents.web_search.DDGS") as MockDDGS:
            MockDDGS.return_value.text.side_effect = Exception("network error")
            result = run(agent.search("hello"))
        assert "Search error" in result or "error" in result.lower()

    def test_body_truncated_to_300_chars(self, agent):
        long_body = "x" * 600
        mock_results = [{"title": "T", "body": long_body, "href": "http://x.com"}]
        with patch("agents.web_search.DDGS") as MockDDGS:
            MockDDGS.return_value.text.return_value = mock_results
            result = run(agent.search("test"))
        # The result should not contain 600 x's
        assert "x" * 301 not in result

    def test_multiple_results_numbered(self, agent):
        mock_results = [
            {"title": f"Result {i}", "body": "body", "href": f"http://r{i}.com"}
            for i in range(1, 4)
        ]
        with patch("agents.web_search.DDGS") as MockDDGS:
            MockDDGS.return_value.text.return_value = mock_results
            result = run(agent.search("test"))
        assert "1." in result
        assert "2." in result
        assert "3." in result

    def test_missing_fields_handled(self, agent):
        """Results with missing keys should not crash."""
        mock_results = [{}]  # completely empty dict
        with patch("agents.web_search.DDGS") as MockDDGS:
            MockDDGS.return_value.text.return_value = mock_results
            result = run(agent.search("test"))
        assert result is not None  # should not raise

    def test_max_results_parameter(self, agent):
        """Verify max_results is passed to DDGS."""
        mock_results = []
        with patch("agents.web_search.DDGS") as MockDDGS:
            MockDDGS.return_value.text.return_value = mock_results
            run(agent.search("test", max_results=3))
            MockDDGS.return_value.text.assert_called_once_with("test", max_results=3)
