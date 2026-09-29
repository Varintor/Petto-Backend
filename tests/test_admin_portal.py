"""Security and availability checks for the staging administration portal."""


def test_admin_portal_is_available_without_embedding_secret(client, monkeypatch):
    secret = "test-admin-key-that-must-not-leak"
    monkeypatch.setenv("ADMIN_API_KEY", secret)

    response = client.get("/admin")

    assert response.status_code == 200
    assert "Petto Admin Portal" in response.text
    assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_admin_portal_uses_protected_admin_api(client):
    response = client.get("/admin")

    assert "X-Admin-Key" in response.text
    assert "'/api/v1/admin'" in response.text

