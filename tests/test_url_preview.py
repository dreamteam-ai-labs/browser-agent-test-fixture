"""Tests for URL preview (browser-agent integration) endpoint."""
from unittest.mock import MagicMock, patch


def test_preview_no_url(client, auth_headers):
    """Preview endpoint returns 400 when task has no URL."""
    create = client.post("/api/tasks", json={"title": "No URL Task"}, headers=auth_headers)
    tid = create.json()["id"]

    resp = client.post(f"/api/tasks/{tid}/preview", headers=auth_headers)
    assert resp.status_code == 400
    assert "no URL" in resp.json()["detail"]


def test_preview_not_found(client, auth_headers):
    """Preview endpoint returns 404 for unknown task."""
    resp = client.post("/api/tasks/99999/preview", headers=auth_headers)
    assert resp.status_code == 404


def test_preview_requires_auth(client):
    """Preview endpoint requires authentication."""
    resp = client.post("/api/tasks/1/preview")
    assert resp.status_code == 401


def test_preview_calls_browser_agent(client, auth_headers):
    """Preview endpoint calls browser-agent and stores screenshot URL."""
    create = client.post(
        "/api/tasks",
        json={"title": "Preview Task", "url": "https://example.com"},
        headers=auth_headers,
    )
    tid = create.json()["id"]

    mock_response = MagicMock()
    mock_response.json.return_value = {"screenshotUrl": "https://cdn.example.com/shot.png"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response) as mock_post:
        resp = client.post(f"/api/tasks/{tid}/preview", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["preview_url"] == "https://cdn.example.com/shot.png"
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "https://example.com" in str(call_args)


def test_preview_stored_on_task(client, auth_headers):
    """After preview, task GET returns the preview_url."""
    create = client.post(
        "/api/tasks",
        json={"title": "Store Preview", "url": "https://example.com"},
        headers=auth_headers,
    )
    tid = create.json()["id"]

    mock_response = MagicMock()
    mock_response.json.return_value = {"screenshotUrl": "https://cdn.example.com/stored.png"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response):
        client.post(f"/api/tasks/{tid}/preview", headers=auth_headers)

    task = client.get(f"/api/tasks/{tid}", headers=auth_headers)
    assert task.status_code == 200
    assert task.json()["preview_url"] == "https://cdn.example.com/stored.png"


def test_preview_browser_agent_error(client, auth_headers):
    """Preview returns 502 when browser-agent fails."""
    create = client.post(
        "/api/tasks",
        json={"title": "Error Task", "url": "https://bad-site.com"},
        headers=auth_headers,
    )
    tid = create.json()["id"]

    with patch("httpx.post", side_effect=Exception("Connection refused")):
        resp = client.post(f"/api/tasks/{tid}/preview", headers=auth_headers)

    assert resp.status_code == 502
