"""Tests for user authentication endpoints."""
import pytest


def test_register_success(client):
    resp = client.post("/api/auth/register", json={
        "email": "new@example.com",
        "password": "Password123!",
        "name": "New User",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["user"]["email"] == "new@example.com"
    assert data["user"]["display_name"] == "New User"


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "Pass123!", "name": "User"}
    client.post("/api/auth/register", json=payload)
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 409


def test_login_success(client):
    client.post("/api/auth/register", json={
        "email": "login@example.com",
        "password": "MyPass123!",
        "name": "Login User",
    })
    resp = client.post("/api/auth/login", json={
        "email": "login@example.com",
        "password": "MyPass123!",
    })
    assert resp.status_code == 200
    assert "token" in resp.json()


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={
        "email": "wrong@example.com",
        "password": "Correct123!",
        "name": "User",
    })
    resp = client.post("/api/auth/login", json={
        "email": "wrong@example.com",
        "password": "WrongPassword!",
    })
    assert resp.status_code == 401


def test_me_authenticated(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"


def test_me_unauthenticated(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 403


def test_users_me_route(client, auth_headers):
    """Test the /api/users/me alias route."""
    resp = client.get("/api/users/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "email" in data
