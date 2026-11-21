import pytest

from app import create_app
from app.extensions import db
from app.seed import seed

SECRET = "test-secret-key-that-is-long-enough-123456"
ORIGIN = "http://localhost:5173"


@pytest.fixture()
def app():
    app = create_app({"TESTING": True, "BCRYPT_LOG_ROUNDS": 4, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                      "SECRET_KEY": SECRET, "CORS_ORIGINS": [ORIGIN]})
    with app.app_context():
        db.create_all()
        seed()
        yield app
        db.drop_all()


@pytest.fixture()
def c(app):
    return app.test_client()


def register_user(c, payload, app=None):
    
    import re
    from flask import current_app
    r = c.post("/api/auth/register", json=payload)
    if r.status_code != 202:
        return r
    code = re.search(r"\b(\d{6})\b", current_app.extensions["outbox"][-1]["body"]).group(1)
    return c.post("/api/auth/register/verify", json={"email": payload["email"], "code": code})


def login(c, email, pw="demo1234"):
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.json
    return {"Authorization": "Bearer " + r.json["token"]}


@pytest.fixture()
def buyer(c):
    return login(c, "buyer@demo.com")


@pytest.fixture()
def dealer(c):
    return login(c, "dealer@demo.com")


@pytest.fixture()
def admin(c):
    return login(c, "admin@demo.com")
