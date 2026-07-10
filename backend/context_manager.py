"""
context_manager.py — In-Memory Session & Conversation History
"""

import time
from typing import List, Dict


class ContextManager:
    """Manages per-session chat history and metadata."""

    def __init__(self, max_history: int = 30):
        self.sessions: Dict[str, dict] = {}
        self.max_history = max_history

    def _ensure_session(self, session_id: str) -> dict:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "messages": [],
                "created_at": time.time(),
                "tool_call_count": 0,
                "message_count": 0,
            }
        return self.sessions[session_id]

    def add_message(self, session_id: str, role: str, content: str) -> None:
        session = self._ensure_session(session_id)
        session["messages"].append({"role": role, "content": content})
        session["message_count"] += 1
        # Trim to avoid unbounded growth
        if len(session["messages"]) > self.max_history:
            # Always keep system-level context; trim oldest turns
            session["messages"] = session["messages"][-self.max_history:]

    def get_messages(self, session_id: str) -> List[Dict]:
        return self._ensure_session(session_id)["messages"]

    def increment_tool_count(self, session_id: str) -> None:
        self._ensure_session(session_id)["tool_call_count"] += 1

    def get_stats(self, session_id: str) -> dict:
        session = self._ensure_session(session_id)
        return {
            "message_count": session["message_count"],
            "tool_call_count": session["tool_call_count"],
            "uptime_seconds": round(time.time() - session["created_at"]),
        }

    def clear_session(self, session_id: str) -> None:
        if session_id in self.sessions:
            del self.sessions[session_id]
