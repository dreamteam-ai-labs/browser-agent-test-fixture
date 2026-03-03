"""Tests for project management endpoints."""


def test_list_projects_empty(client, auth_headers):
    resp = client.get("/api/projects", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_project(client, auth_headers):
    resp = client.post("/api/projects", json={
        "name": "My Project",
        "description": "A test project",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Project"
    assert data["description"] == "A test project"
    assert "id" in data
    assert "user_id" in data


def test_get_project(client, auth_headers):
    create = client.post("/api/projects", json={"name": "Fetch Me"}, headers=auth_headers)
    pid = create.json()["id"]
    resp = client.get(f"/api/projects/{pid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Fetch Me"


def test_get_project_not_found(client, auth_headers):
    resp = client.get("/api/projects/99999", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_project(client, auth_headers):
    create = client.post("/api/projects", json={"name": "Delete Me"}, headers=auth_headers)
    pid = create.json()["id"]
    resp = client.delete(f"/api/projects/{pid}", headers=auth_headers)
    assert resp.status_code == 204
    # Confirm deleted
    resp = client.get(f"/api/projects/{pid}", headers=auth_headers)
    assert resp.status_code == 404


def test_projects_require_auth(client):
    resp = client.get("/api/projects")
    assert resp.status_code == 403


def test_project_isolation(client):
    """Users cannot see other users' projects."""
    # Create user A project
    a = client.post("/api/auth/register", json={
        "email": "a@example.com", "password": "PassA123!", "name": "A"
    }).json()
    # Create user B project
    b = client.post("/api/auth/register", json={
        "email": "b@example.com", "password": "PassB123!", "name": "B"
    }).json()

    headers_a = {"Authorization": f"Bearer {a['token']}"}
    headers_b = {"Authorization": f"Bearer {b['token']}"}

    client.post("/api/projects", json={"name": "User A Project"}, headers=headers_a)

    resp = client.get("/api/projects", headers=headers_b)
    assert resp.json() == []
