"""
agents/weather.py — Weather (OpenWeatherMap) + News (RSS) Agent
"""

import asyncio
import os

import feedparser
import httpx
from dotenv import load_dotenv

load_dotenv()

WEATHER_KEY = os.getenv("OPENWEATHER_API_KEY", "")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

NEWS_FEEDS = {
    "BBC News":  "https://feeds.bbci.co.uk/news/rss.xml",
    "Reuters":   "https://feeds.reuters.com/reuters/topNews",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
}


class WeatherAgent:
    # ------------------------------------------------------------------
    # Weather
    # ------------------------------------------------------------------
    async def get_weather(self, city: str) -> str:
        if not city.strip():
            return "Please specify a city name."
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    WEATHER_URL,
                    params={"q": city, "appid": WEATHER_KEY, "units": "metric"},
                )
            if resp.status_code == 404:
                return f"❌ City **'{city}'** not found. Please check the spelling."
            if resp.status_code == 401:
                return "❌ Invalid OpenWeatherMap API key."
            resp.raise_for_status()
            d = resp.json()

            name     = d["name"]
            country  = d["sys"]["country"]
            temp     = d["main"]["temp"]
            feels    = d["main"]["feels_like"]
            humidity = d["main"]["humidity"]
            desc     = d["weather"][0]["description"].capitalize()
            wind     = d["wind"]["speed"]
            icon_map = {
                "clear":     "☀️",
                "cloud":     "☁️",
                "rain":      "🌧️",
                "drizzle":   "🌦️",
                "thunder":   "⛈️",
                "snow":      "❄️",
                "mist":      "🌫️",
                "fog":       "🌫️",
                "haze":      "🌫️",
            }
            icon = next(
                (v for k, v in icon_map.items() if k in desc.lower()), "🌡️"
            )

            return (
                f"{icon} **Weather in {name}, {country}**\n\n"
                f"| Metric | Value |\n"
                f"|---|---|\n"
                f"| 🌡️ Temperature | {temp}°C (feels like {feels}°C) |\n"
                f"| ☁️ Condition | {desc} |\n"
                f"| 💧 Humidity | {humidity}% |\n"
                f"| 💨 Wind Speed | {wind} m/s |"
            )
        except httpx.RequestError as exc:
            return f"Network error fetching weather: {exc}"
        except Exception as exc:
            return f"Weather error: {exc}"

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------
    async def get_news(self) -> str:
        loop = asyncio.get_event_loop()
        all_items = []

        for source, url in NEWS_FEEDS.items():
            try:
                feed = await loop.run_in_executor(
                    None, lambda u=url: feedparser.parse(u)
                )
                for entry in feed.entries[:3]:
                    all_items.append({
                        "source":  source,
                        "title":   entry.get("title", "No title"),
                        "summary": (entry.get("summary") or "")[:200].strip(),
                        "link":    entry.get("link", ""),
                    })
            except Exception:
                continue

        if not all_items:
            return "📰 Unable to fetch news at this time. Please try again later."

        lines = ["📰 **Latest World News Headlines:**\n"]
        for i, item in enumerate(all_items[:8], 1):
            lines.append(
                f"**{i}. [{item['source']}] {item['title']}**\n"
                f"   {item['summary']}\n"
                f"   🔗 {item['link']}\n"
            )
        return "\n".join(lines)
