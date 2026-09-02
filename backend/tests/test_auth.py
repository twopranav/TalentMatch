from app.models.user import UserRole

def test_register_defaults_to_user_role(client):
    resp = client.post("/api/auth/register", json={"email": "new@test.com", "password": "pass1234"})
    assert resp.status_code == 201
    assert resp.json()["role"] == UserRole.USER.value

def test_register_duplicate_email_rejected(client, make_user):
    user, _ = make_user()
    resp = client.post("/api/auth/register", json={"email": user.email, "password": "whatever123"})
    assert resp.status_code == 400

def test_login_success_returns_token(client, make_user):
    user, password = make_user()
    resp = client.post("/api/auth/login", data={"username": user.email, "password": password})
    assert resp.status_code == 200
    assert "access_token" in resp.json()

def test_login_wrong_password_rejected(client, make_user):
    user, _ = make_user()
    resp = client.post("/api/auth/login", data={"username": user.email, "password": "wrongpass"})
    assert resp.status_code == 401