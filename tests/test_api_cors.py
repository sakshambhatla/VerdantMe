"""Tests for CORS header configuration."""
from __future__ import annotations


class TestCorsHeaders:
    def test_preflight_allows_expected_methods(self, client):
        resp = client.options(
            "/api/resume",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        allowed = resp.headers.get("access-control-allow-methods", "")
        for method in ("GET", "POST", "PUT", "DELETE"):
            assert method in allowed
        # Wildcard or unexpected methods should not be present
        assert "PATCH" not in allowed

    def test_preflight_allows_expected_headers(self, client):
        resp = client.options(
            "/api/resume",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        allowed = resp.headers.get("access-control-allow-headers", "")
        assert "Authorization" in allowed or "authorization" in allowed.lower()
        assert "Content-Type" in allowed or "content-type" in allowed.lower()

    def test_cors_allows_configured_origin(self, client):
        resp = client.options(
            "/api/resume",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_cors_rejects_unknown_origin(self, client):
        resp = client.options(
            "/api/resume",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Should not echo back the evil origin
        allow_origin = resp.headers.get("access-control-allow-origin", "")
        assert "evil.com" not in allow_origin
