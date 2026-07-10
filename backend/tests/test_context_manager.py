"""
Tests for context_manager.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from context_manager import ContextManager


class TestContextManagerInit:
    def test_default_max_history(self):
        cm = ContextManager()
        assert cm.max_history == 30

    def test_custom_max_history(self):
        cm = ContextManager(max_history=5)
        assert cm.max_history == 5

    def test_sessions_initially_empty(self):
        cm = ContextManager()
        assert cm.sessions == {}


class TestAddAndGetMessages:
    def test_add_user_message(self):
        cm = ContextManager()
        cm.add_message("s1", "user", "Hello")
        msgs = cm.get_messages("s1")
        assert len(msgs) == 1
        assert msgs[0] == {"role": "user", "content": "Hello"}

    def test_add_assistant_message(self):
        cm = ContextManager()
        cm.add_message("s1", "assistant", "Hi there")
        msgs = cm.get_messages("s1")
        assert msgs[0]["role"] == "assistant"

    def test_message_count_increments(self):
        cm = ContextManager()
        cm.add_message("s1", "user", "A")
        cm.add_message("s1", "user", "B")
        stats = cm.get_stats("s1")
        assert stats["message_count"] == 2

    def test_empty_session_returns_empty_list(self):
        cm = ContextManager()
        msgs = cm.get_messages("nonexistent")
        assert msgs == []

    def test_multiple_sessions_isolated(self):
        cm = ContextManager()
        cm.add_message("s1", "user", "Session1 msg")
        cm.add_message("s2", "user", "Session2 msg")
        assert len(cm.get_messages("s1")) == 1
        assert len(cm.get_messages("s2")) == 1
        assert cm.get_messages("s1")[0]["content"] == "Session1 msg"


class TestHistoryTrimming:
    def test_history_trimmed_to_max(self):
        cm = ContextManager(max_history=5)
        for i in range(10):
            cm.add_message("s1", "user", f"Message {i}")
        msgs = cm.get_messages("s1")
        assert len(msgs) == 5

    def test_oldest_messages_removed(self):
        cm = ContextManager(max_history=3)
        cm.add_message("s1", "user", "first")
        cm.add_message("s1", "user", "second")
        cm.add_message("s1", "user", "third")
        cm.add_message("s1", "user", "fourth")
        msgs = cm.get_messages("s1")
        contents = [m["content"] for m in msgs]
        assert "first" not in contents
        assert "fourth" in contents

    def test_message_count_not_capped(self):
        """message_count should reflect total msgs ever added, not just in history"""
        cm = ContextManager(max_history=2)
        for i in range(5):
            cm.add_message("s1", "user", f"msg{i}")
        stats = cm.get_stats("s1")
        assert stats["message_count"] == 5


class TestToolCount:
    def test_increment_tool_count(self):
        cm = ContextManager()
        cm.increment_tool_count("s1")
        cm.increment_tool_count("s1")
        stats = cm.get_stats("s1")
        assert stats["tool_call_count"] == 2

    def test_initial_tool_count_zero(self):
        cm = ContextManager()
        stats = cm.get_stats("s1")
        assert stats["tool_call_count"] == 0


class TestGetStats:
    def test_stats_keys_present(self):
        cm = ContextManager()
        stats = cm.get_stats("s1")
        assert "message_count" in stats
        assert "tool_call_count" in stats
        assert "uptime_seconds" in stats

    def test_uptime_non_negative(self):
        cm = ContextManager()
        cm.get_messages("s1")  # trigger session creation
        stats = cm.get_stats("s1")
        assert stats["uptime_seconds"] >= 0


class TestClearSession:
    def test_clear_removes_session(self):
        cm = ContextManager()
        cm.add_message("s1", "user", "hello")
        cm.clear_session("s1")
        assert "s1" not in cm.sessions

    def test_clear_nonexistent_session_no_error(self):
        cm = ContextManager()
        cm.clear_session("ghost")  # should not raise

    def test_clear_then_get_returns_empty(self):
        cm = ContextManager()
        cm.add_message("s1", "user", "hi")
        cm.clear_session("s1")
        msgs = cm.get_messages("s1")
        assert msgs == []


class TestEdgeCases:
    def test_empty_content_message(self):
        cm = ContextManager()
        cm.add_message("s1", "user", "")
        msgs = cm.get_messages("s1")
        assert msgs[0]["content"] == ""

    def test_long_session_id(self):
        cm = ContextManager()
        sid = "x" * 256
        cm.add_message(sid, "user", "test")
        assert cm.get_messages(sid)[0]["content"] == "test"

    def test_unicode_content(self):
        cm = ContextManager()
        cm.add_message("s1", "user", "你好世界 🌍")
        assert cm.get_messages("s1")[0]["content"] == "你好世界 🌍"
