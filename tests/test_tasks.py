"""Tests for task management endpoints."""


def test_list_tasks_empty(client, auth_headers):
    resp = client.get("/api/tasks", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_task(client, auth_headers):
    resp = client.post("/api/tasks", json={
        "title": "My Task",
        "status": "todo",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My Task"
    assert data["status"] == "todo"
    assert "id" in data


def test_create_task_with_project(client, auth_headers):
    proj = client.post("/api/projects", json={"name": "Task Proj"}, headers=auth_headers)
    pid = proj.json()["id"]
    resp = client.post("/api/tasks", json={
        "title": "Linked Task",
        "project_id": pid,
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["project_id"] == pid


def test_get_task(client, auth_headers):
    create = client.post("/api/tasks", json={"title": "Fetch Me"}, headers=auth_headers)
    tid = create.json()["id"]
    resp = client.get(f"/api/tasks/{tid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Fetch Me"


def test_get_task_not_found(client, auth_headers):
    resp = client.get("/api/tasks/99999", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_task(client, auth_headers):
    create = client.post("/api/tasks", json={"title": "Delete Me"}, headers=auth_headers)
    tid = create.json()["id"]
    resp = client.delete(f"/api/tasks/{tid}", headers=auth_headers)
    assert resp.status_code == 204
    resp = client.get(f"/api/tasks/{tid}", headers=auth_headers)
    assert resp.status_code == 404


def test_update_task(client, auth_headers):
    create = client.post("/api/tasks", json={"title": "Old Title", "status": "todo"}, headers=auth_headers)
    tid = create.json()["id"]
    resp = client.put(f"/api/tasks/{tid}", json={"title": "New Title", "status": "done"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New Title"
    assert data["status"] == "done"


def test_tasks_require_auth(client):
    resp = client.get("/api/tasks")
    assert resp.status_code == 401


def test_task_isolation(client):
    """Users cannot see other users' tasks."""
    a = client.post("/api/auth/register", json={
        "email": "ta@example.com", "password": "PassA123!", "name": "A"
    }).json()
    b = client.post("/api/auth/register", json={
        "email": "tb@example.com", "password": "PassB123!", "name": "B"
    }).json()

    headers_a = {"Authorization": f"Bearer {a['token']}"}
    headers_b = {"Authorization": f"Bearer {b['token']}"}

    client.post("/api/tasks", json={"title": "A Task"}, headers=headers_a)

    resp = client.get("/api/tasks", headers=headers_b)
    assert resp.json() == []
