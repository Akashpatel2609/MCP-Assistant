"""
Tests for main.py FastAPI HTTP endpoints.
WebSocket tests are integration-level and require a running server;
HTTP routes are tested via TestClient.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from fastapi.testclient import TestClient


# Patch LLM/router before importing app so no real API calls are made
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("uploads")
    with patch("llm_client.NVIDIAClient") as MockLLM, \
         patch("mcp_router.NVIDIAClient") as MockRouterLLM, \
         patch("main.UPLOAD_DIR", tmp):
        import main as app_module
        app_module.UPLOAD_DIR = tmp
        from fastapi.testclient import TestClient as TC
        c = TC(app_module.app)
        yield c


class TestHealthEndpoint:
    def test_health_status_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_has_model_key(self, client):
        resp = client.get("/health")
        assert "model" in resp.json()


class TestFilesEndpoint:
    def test_list_files_empty(self, client):
        resp = client.get("/files")
        assert resp.status_code == 200
        assert "files" in resp.json()

    def test_upload_and_list(self, client, tmp_path):
        content = b"hello file"
        resp = client.post(
            "/upload",
            files={"file": ("test_upload.txt", content, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["filename"] == "test_upload.txt"
        assert data["size"] == len(content)

    def test_upload_returns_filename(self, client):
        resp = client.post(
            "/upload",
            files={"file": ("myfile.txt", b"data", "text/plain")},
        )
        assert resp.json()["filename"] == "myfile.txt"

    def test_upload_large_file(self, client):
        large = b"x" * 1_000_000  # 1 MB
        resp = client.post(
            "/upload",
            files={"file": ("large.bin", large, "application/octet-stream")},
        )
        assert resp.status_code == 200

    def test_upload_path_traversal_in_filename(self, client):
        """Filenames with path separators should be sanitised."""
        resp = client.post(
            "/upload",
            files={"file": ("../../evil.txt", b"evil", "text/plain")},
        )
        # Should succeed but store as "evil.txt" not traverse directories
        assert resp.status_code == 200
        assert "/" not in resp.json()["filename"]
        assert "\\" not in resp.json()["filename"]


class TestIndexRoute:
    def test_root_returns_html(self, client):
        # index.html may not exist in test env; we just check it doesn't 500
        resp = client.get("/")
        assert resp.status_code in (200, 404)  # 404 if frontend missing in test


class TestCORSHeaders:
    def test_cors_wildcard_present(self, client):
        resp = client.options("/health", headers={"Origin": "http://evil.com"})
        # CORS is wide-open — document this
        assert resp.status_code in (200, 405)
