import re
from datetime import timedelta

from app.extensions import db
from app.models import PasswordReset, utcnow


def code_from(app):
    return re.search(r"\b(\d{6})\b", app.extensions["outbox"][-1]["body"]).group(1)


def reset(c, code, pw="newpass123", email="buyer@demo.com"):
    return c.post("/api/auth/reset", json={"email": email, "code": code, "password": pw})


def test_forgot_and_reset_changes_password(c, app):
    r = c.post("/api/auth/forgot", json={"email": "buyer@demo.com"})
    assert r.status_code == 202 and app.extensions["outbox"][-1]["to"] == "buyer@demo.com"
    assert reset(c, code_from(app)).status_code == 200
    assert c.post("/api/auth/login", json={"email": "buyer@demo.com", "password": "demo1234"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "buyer@demo.com", "password": "newpass123"}).status_code == 200
    assert PasswordReset.query.count() == 0


def test_unknown_email_gets_same_answer_and_no_email(c, app):
    r = c.post("/api/auth/forgot", json={"email": "nobody@x.com"})
    assert r.status_code == 202 and not app.extensions.get("outbox")
    assert reset(c, "123456", email="nobody@x.com").status_code == 400


def test_code_cannot_be_reused_and_wrong_code_locks(c, app):
    c.post("/api/auth/forgot", json={"email": "buyer@demo.com"})
    good = code_from(app)
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert reset(c, bad).status_code == 400
    assert reset(c, good).status_code == 429
    c.post("/api/auth/forgot", json={"email": "buyer@demo.com"})  
    PasswordReset.query.one().last_sent_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    c.post("/api/auth/forgot", json={"email": "buyer@demo.com"})
    good = code_from(app)
    assert reset(c, good).status_code == 200
    assert reset(c, good).status_code == 400  


def test_expired_code_and_weak_password(c, app):
    c.post("/api/auth/forgot", json={"email": "buyer@demo.com"})
    code = code_from(app)
    assert reset(c, code, pw="short").status_code == 400
    PasswordReset.query.one().expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    r = reset(c, code)
    assert r.status_code == 400 and "expired" in r.json["error"]
