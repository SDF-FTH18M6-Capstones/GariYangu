import re
from datetime import timedelta

from app.extensions import db
from app.models import SignupOtp, User, utcnow

BUYER = {"email": "otp@x.com", "password": "secret123", "full_name": "Otp User", "role": "buyer"}
DEALER = {"email": "dealer-otp@x.com", "password": "secret123", "full_name": "D", "role": "dealer",
          "business_name": "D Ltd", "id_number": "23456789", "county": "Nairobi"}


def last_code(app):
    return re.search(r"\b(\d{6})\b", app.extensions["outbox"][-1]["body"]).group(1)


def verify(c, email, code):
    return c.post("/api/auth/register/verify", json={"email": email, "code": code})


def test_signup_creates_nothing_until_code_verified(c, app):
    r = c.post("/api/auth/register", json=BUYER)
    assert r.status_code == 202 and "token" not in r.json
    assert User.query.filter_by(email=BUYER["email"]).first() is None
    assert app.extensions["outbox"][-1]["to"] == BUYER["email"]
    assert c.post("/api/auth/login", json={"email": BUYER["email"], "password": "secret123"}).status_code == 401
    r = verify(c, BUYER["email"], last_code(app))
    assert r.status_code == 201 and r.json["user"]["email"] == BUYER["email"]
    assert c.post("/api/auth/login", json={"email": BUYER["email"], "password": "secret123"}).status_code == 200
    assert SignupOtp.query.count() == 0


def test_plaintext_password_and_code_not_stored(app, c):
    c.post("/api/auth/register", json=BUYER)
    row = SignupOtp.query.one()
    assert "secret123" not in str(row.payload) and last_code(app) not in str(row.code_hash)


def test_wrong_code_then_lockout(c, app):
    c.post("/api/auth/register", json=BUYER)
    good = last_code(app)
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert verify(c, BUYER["email"], bad).status_code == 400
    assert verify(c, BUYER["email"], good).status_code == 429  


def test_expired_code(c, app):
    c.post("/api/auth/register", json=BUYER)
    SignupOtp.query.one().expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    r = verify(c, BUYER["email"], last_code(app))
    assert r.status_code == 400 and "expired" in r.json["error"]


def test_resend_cooldown_and_new_code(c, app):
    c.post("/api/auth/register", json=BUYER)
    assert c.post("/api/auth/register/resend", json={"email": BUYER["email"]}).status_code == 429
    SignupOtp.query.one().last_sent_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert c.post("/api/auth/register/resend", json={"email": BUYER["email"]}).status_code == 202
    assert len(app.extensions["outbox"]) == 2
    assert verify(c, BUYER["email"], last_code(app)).status_code == 201


def test_verify_without_signup_and_bad_format(c):
    assert verify(c, "nobody@x.com", "123456").status_code == 404
    assert verify(c, "nobody@x.com", "12ab").status_code == 400
    assert c.post("/api/auth/register/resend", json={"email": "nobody@x.com"}).status_code == 404


def test_dealer_requires_valid_id_number(c):
    for bad in ("", "A123456789Z", "123456", "123456789"):
        r = c.post("/api/auth/register", json={**DEALER, "id_number": bad})
        assert r.status_code == 400 and "ID number" in r.json["error"]


def test_dealer_signup_stores_id_number(c, app):
    assert c.post("/api/auth/register", json=DEALER).status_code == 202
    r = verify(c, DEALER["email"], last_code(app))
    assert r.status_code == 201
    d = r.json["user"]["dealer"]
    assert d["id_number"] == "23456789" and d["status"] == "pending" and "kra_pin" not in d
