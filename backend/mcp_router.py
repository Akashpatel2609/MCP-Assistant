"""
mcp_router.py — MCP Server / Router
Uses the LLM to decide which tool agents to invoke, executes them,
and returns the aggregated tool results.
"""

import json
import re
from typing import List

from llm_client import NVIDIAClient
from agents.web_search import WebSearchAgent
from agents.file_handler import FileHandlerAgent
from agents.db_query import DBQueryAgent
from agents.code_runner import CodeRunnerAgent
from agents.weather import WeatherAgent


# ── Prompt sent to the LLM purely for tool-selection ────────────────────────
_TOOL_SELECTION_SYSTEM = """You are an MCP (Model Context Protocol) Router.
Your ONLY job is to read the user's message and decide which tools to call.

AVAILABLE TOOLS:
1. web_search     — params: {"query": "search terms"}
2. get_weather    — params: {"city": "CityName"}
3. get_news       — params: {}
4. read_file      — params: {"filename": "name.ext"}
5. list_files     — params: {}
6. db_query       — params: {"sql": "SELECT ..."}
7. run_code       — params: {"code": "python code here"}
8. none           — params: {}  (use when no tool is needed)

DATABASE SCHEMA (use for db_query):
- employees: id, name, department, salary, hire_date, email
- products:  id, name, category, price, stock
- sales:     id, product_id, employee_id, quantity, sale_date, total

RULES:
- Respond ONLY with a valid JSON object — no prose, no markdown fences.
- You may include multiple tools in the array.
- For db_query generate a complete, safe SELECT statement.
- For run_code write complete, runnable Python code.

RESPONSE FORMAT (strict JSON):
{
  "tools": [
    {"tool": "tool_name", "params": {"key": "value"}},
    ...
  ],
  "reasoning": "one-line explanation"
}"""


class MCPRouter:
    """Routes user messages to the correct tool agents."""

    def __init__(self):
        self.llm          = NVIDIAClient()
        self.web_search   = WebSearchAgent()
        self.file_handler = FileHandlerAgent()
        self.db_query     = DBQueryAgent()
        self.code_runner  = CodeRunnerAgent()
        self.weather      = WeatherAgent()

    # ── Tool Selection ───────────────────────────────────────────────────────
    async def _decide_tools(self, user_message: str) -> dict:
        messages = [
            {"role": "system", "content": _TOOL_SELECTION_SYSTEM},
            {"role": "user",   "content": user_message},
        ]
        try:
            resp = await self.llm.chat(messages, temperature=0.1, max_tokens=512)
            content = resp.choices[0].message.content or ""

            # Extract the first JSON object from the response
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, Exception):
            pass
        # Fallback — no tool
        return {"tools": [{"tool": "none", "params": {}}], "reasoning": "Fallback: direct answer"}

    # ── Tool Execution ───────────────────────────────────────────────────────
    async def _execute_tool(self, tool: str, params: dict) -> str:
        try:
            if tool == "web_search":
                return await self.web_search.search(params.get("query", ""))

            elif tool == "get_weather":
                return await self.weather.get_weather(params.get("city", ""))

            elif tool == "get_news":
                return await self.weather.get_news()

            elif tool == "read_file":
                return await self.file_handler.read_file(params.get("filename", ""))

            elif tool == "list_files":
                return await self.file_handler.list_files()

            elif tool == "db_query":
                return await self.db_query.query(params.get("sql", ""))

            elif tool == "run_code":
                return await self.code_runner.execute(params.get("code", ""))

            elif tool == "none":
                return ""

            else:
                return f"Unknown tool: {tool}"

        except Exception as exc:
            return f"Tool '{tool}' error: {exc}"

    # ── Public entry-point ───────────────────────────────────────────────────
    async def route(self, user_message: str, history: List[dict]) -> dict:
        """
        Returns:
            {
                "tool_decision": { "tools": [...], "reasoning": "..." },
                "tool_results":  [ {"tool": str, "result": str}, ... ]
            }
        """
        decision = await self._decide_tools(user_message)
        tools_to_run: List[dict] = decision.get("tools", [{"tool": "none", "params": {}}])

        results = []
        for call in tools_to_run:
            tool   = call.get("tool", "none")
            params = call.get("params", {})
            result = await self._execute_tool(tool, params)
            results.append({"tool": tool, "params": params, "result": result})

        return {"tool_decision": decision, "tool_results": results}
