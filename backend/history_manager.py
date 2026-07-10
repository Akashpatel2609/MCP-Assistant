"""
history_manager.py — Persistent Chat History (SQLite)

Stores sessions and messages to disk so conversations survive server restarts.
Each session has an auto-generated title derived from the first user message.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import os

# Use in-memory SQLite on Vercel to prevent filesystem locking and container freeze operational errors
if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.path.exists("/var/task"):
    DB_PATH = ":memory:"
else:
    DB_PATH = "data/nexus_history.db"


class HistoryManager:
    """SQLite-backed persistent conversation storage."""

    def __init__(self):
        if DB_PATH != ":memory:":
            Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    # ── Schema ────────────────────────────────────────────────────────────────
    def _migrate(self):
        with self._conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id           TEXT PRIMARY KEY,
                title        TEXT    NOT NULL DEFAULT 'New Chat',
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT    NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role         TEXT    NOT NULL,
                content      TEXT    NOT NULL,
                tools_used   TEXT    NOT NULL DEFAULT '[]',
                timestamp    TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.path.exists("/var/task"):
            conn.execute("PRAGMA journal_mode = DELETE")
        else:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Sessions ──────────────────────────────────────────────────────────────
    def ensure_session(self, session_id: str) -> None:
        """Create session record if it doesn't exist yet."""
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (id, created_at, updated_at) VALUES (?,?,?)",
                (session_id, now, now),
            )

    def get_sessions(self, limit: int = 60) -> List[Dict]:
        """Return recent sessions ordered by last activity."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, title, created_at, updated_at, message_count
                   FROM sessions ORDER BY updated_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))

    def _set_title(self, session_id: str, first_message: str) -> None:
        """Auto-title: first 60 chars of the first user message."""
        title = first_message.strip()[:60]
        if len(first_message) > 60:
            title += "…"
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET title=? WHERE id=? AND title='New Chat'",
                (title, session_id),
            )

    # ── Messages ──────────────────────────────────────────────────────────────
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tools_used: Optional[List[str]] = None,
    ) -> None:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO messages (session_id, role, content, tools_used, timestamp)
                   VALUES (?,?,?,?,?)""",
                (session_id, role, content, json.dumps(tools_used or []), now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=?, message_count=message_count+1 WHERE id=?",
                (now, session_id),
            )
        # Auto-title from the first user message
        if role == "user":
            self._set_title(session_id, content)

    def get_messages(self, session_id: str) -> List[Dict]:
        """Return all messages for a session (full objects with metadata)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT role, content, tools_used, timestamp
                   FROM messages WHERE session_id=? ORDER BY id ASC""",
                (session_id,),
            ).fetchall()
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "tools_used": json.loads(r["tools_used"]),
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    def get_context_window(self, session_id: str, max_turns: int = 20) -> List[Dict]:
        """Return recent messages as {role, content} dicts for LLM context."""
        all_msgs = self.get_messages(session_id)
        recent = all_msgs[-max_turns:] if len(all_msgs) > max_turns else all_msgs
        return [{"role": m["role"], "content": m["content"]} for m in recent]

    def get_message_count(self, session_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT message_count FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
        return row["message_count"] if row else 0
