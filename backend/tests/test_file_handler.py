"""
Tests for agents/file_handler.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import asyncio
from pathlib import Path
from agents.file_handler import FileHandlerAgent


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def agent(tmp_path, monkeypatch):
    """Patch UPLOAD_DIR so we work in a temp folder."""
    monkeypatch.setattr("agents.file_handler.UPLOAD_DIR", tmp_path)
    a = FileHandlerAgent()
    return a, tmp_path


class TestReadFile:
    def test_read_existing_file(self, agent):
        a, d = agent
        (d / "hello.txt").write_text("Hello World", encoding="utf-8")
        result = run(a.read_file("hello.txt"))
        assert "Hello World" in result

    def test_read_nonexistent_file(self, agent):
        a, d = agent
        result = run(a.read_file("ghost.txt"))
        assert "not found" in result.lower()

    def test_path_traversal_blocked(self, agent):
        """../../etc/passwd should be stripped to just 'passwd'."""
        a, d = agent
        # Should not try to read outside UPLOAD_DIR
        result = run(a.read_file("../../etc/passwd"))
        assert "not found" in result.lower()

    def test_file_truncated_at_8000_chars(self, agent):
        a, d = agent
        (d / "big.txt").write_text("A" * 10_000, encoding="utf-8")
        result = run(a.read_file("big.txt"))
        assert "truncated" in result.lower()
        # The actual content slice must be present
        assert "A" * 100 in result

    def test_small_file_not_truncated(self, agent):
        a, d = agent
        (d / "small.txt").write_text("tiny", encoding="utf-8")
        result = run(a.read_file("small.txt"))
        assert "truncated" not in result.lower()

    def test_empty_filename(self, agent):
        a, d = agent
        result = run(a.read_file(""))
        # Empty name → file with name "" not found
        assert "not found" in result.lower() or "error" in result.lower()

    def test_binary_file_read_with_errors_replace(self, agent):
        """Binary file should not crash; errors='replace' handles it."""
        a, d = agent
        (d / "bin.dat").write_bytes(bytes(range(256)))
        result = run(a.read_file("bin.dat"))
        # Should not raise; returns something
        assert result is not None

    def test_unicode_content(self, agent):
        a, d = agent
        (d / "unicode.txt").write_text("日本語テスト 🇯🇵", encoding="utf-8")
        result = run(a.read_file("unicode.txt"))
        assert "日本語テスト" in result


class TestListFiles:
    def test_no_files_returns_empty_message(self, agent):
        a, d = agent
        result = run(a.list_files())
        assert "no files" in result.lower()

    def test_lists_uploaded_files(self, agent):
        a, d = agent
        (d / "a.txt").write_text("aaa")
        (d / "b.txt").write_text("bbb")
        result = run(a.list_files())
        assert "a.txt" in result
        assert "b.txt" in result

    def test_shows_file_size(self, agent):
        a, d = agent
        (d / "sized.txt").write_text("x" * 1024)
        result = run(a.list_files())
        assert "KB" in result


class TestWriteFile:
    def test_write_creates_file(self, agent):
        a, d = agent
        result = run(a.write_file("new.txt", "content here"))
        assert "written successfully" in result.lower()
        assert (d / "new.txt").exists()

    def test_write_correct_content(self, agent):
        a, d = agent
        run(a.write_file("out.txt", "hello from test"))
        assert (d / "out.txt").read_text() == "hello from test"

    def test_write_path_traversal_blocked(self, agent):
        a, d = agent
        result = run(a.write_file("../../evil.txt", "pwned"))
        # Should write to UPLOAD_DIR/evil.txt, not two levels up
        assert (d / "evil.txt").exists()
        assert not Path("evil.txt").exists()

    def test_write_overwrites_existing(self, agent):
        a, d = agent
        (d / "exist.txt").write_text("old")
        run(a.write_file("exist.txt", "new"))
        assert (d / "exist.txt").read_text() == "new"

    def test_write_empty_content(self, agent):
        a, d = agent
        result = run(a.write_file("empty.txt", ""))
        assert "written successfully" in result.lower()
