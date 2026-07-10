"""
agents/web_search.py — DuckDuckGo Web Search Agent
"""

import asyncio
from duckduckgo_search import DDGS


class WebSearchAgent:
    """Searches the internet via DuckDuckGo (no API key required)."""

    async def search(self, query: str, max_results: int = 6) -> str:
        if not query.strip():
            return "No search query provided."
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(query, max_results=max_results)),
            )
            if not results:
                return f"No results found for: **{query}**"

            lines = [f"🔍 **Search results for:** `{query}`\n"]
            for i, r in enumerate(results, 1):
                title = r.get("title", "No title")
                body = r.get("body", "")[:300]
                href = r.get("href", "")
                lines.append(f"**{i}. {title}**\n{body}\n🔗 {href}\n")

            return "\n".join(lines)
        except Exception as exc:
            return f"Search error: {exc}"
