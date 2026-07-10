"""
Tests for agents/weather.py — uses mocks to avoid real API calls.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from agents.weather import WeatherAgent


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def agent():
    return WeatherAgent()


# ── Mock response builders ──────────────────────────────────────────────────

def _make_weather_response(status_code=200, city="London", country="GB",
                            temp=15.0, feels_like=13.0, humidity=75,
                            desc="clear sky", wind=5.0):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "name": city,
        "sys": {"country": country},
        "main": {"temp": temp, "feels_like": feels_like, "humidity": humidity},
        "weather": [{"description": desc}],
        "wind": {"speed": wind},
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


class TestGetWeather:
    def test_empty_city_returns_message(self, agent):
        result = run(agent.get_weather(""))
        assert "specify a city" in result.lower()

    def test_whitespace_city_returns_message(self, agent):
        result = run(agent.get_weather("   "))
        assert "specify a city" in result.lower()

    def test_successful_weather(self, agent):
        mock_resp = _make_weather_response()
        with patch("agents.weather.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = run(agent.get_weather("London"))
        assert "London" in result
        assert "15" in result or "°C" in result

    def test_404_city_not_found(self, agent):
        mock_resp = _make_weather_response(status_code=404)
        with patch("agents.weather.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = run(agent.get_weather("NotACityXYZ"))
        assert "not found" in result.lower()

    def test_401_invalid_api_key(self, agent):
        mock_resp = _make_weather_response(status_code=401)
        with patch("agents.weather.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = run(agent.get_weather("London"))
        assert "Invalid" in result or "API key" in result

    def test_network_error_handled(self, agent):
        import httpx
        with patch("agents.weather.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(side_effect=httpx.RequestError("timeout"))
            ))
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = run(agent.get_weather("London"))
        assert "network error" in result.lower() or "error" in result.lower()

    def test_icon_clear_sky(self, agent):
        mock_resp = _make_weather_response(desc="clear sky")
        with patch("agents.weather.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = run(agent.get_weather("London"))
        assert "☀️" in result

    def test_icon_rain(self, agent):
        mock_resp = _make_weather_response(desc="heavy rain")
        with patch("agents.weather.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            result = run(agent.get_weather("London"))
        assert "🌧️" in result

    def test_missing_api_key_no_crash(self, agent):
        """If OPENWEATHER_API_KEY is empty, the request should still be made
        (and fail with 401 handled gracefully) — not crash on startup."""
        with patch.dict(os.environ, {"OPENWEATHER_API_KEY": ""}):
            a = WeatherAgent()
        # Agent instantiation should not raise
        assert a is not None


class TestGetNews:
    def test_news_returns_string(self, agent):
        """Mock feedparser to return controllable data."""
        # feedparser entries support .get() — use real dicts
        entry = {"title": "Test Headline", "summary": "Short summary.", "link": "http://example.com"}
        mock_feed = MagicMock()
        mock_feed.entries = [entry] * 3

        with patch("agents.weather.feedparser.parse", return_value=mock_feed):
            result = run(agent.get_news())
        assert isinstance(result, str)
        assert "Test Headline" in result

    def test_news_handles_empty_feeds(self, agent):
        mock_feed = MagicMock()
        mock_feed.entries = []
        with patch("agents.weather.feedparser.parse", return_value=mock_feed):
            result = run(agent.get_news())
        assert "unable to fetch" in result.lower() or "no" in result.lower()

    def test_news_handles_feed_exception(self, agent):
        with patch("agents.weather.feedparser.parse", side_effect=Exception("feed error")):
            result = run(agent.get_news())
        assert isinstance(result, str)

    def test_news_max_8_items(self, agent):
        """Even if feeds return many items, output is capped at 8."""
        entry = {"title": "Headline", "summary": "Summary.", "link": "http://x.com"}
        mock_feed = MagicMock()
        mock_feed.entries = [entry] * 20
        with patch("agents.weather.feedparser.parse", return_value=mock_feed):
            result = run(agent.get_news())
        # Count numbered headlines: "1.", "2.", ..., max "8."
        assert "8." in result
        assert "9." not in result
