import time

import jwt as pyjwt
import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy import event

from app import create_app
from app.extensions import db
from app.models import User
from conftest import ORIGIN, SECRET, login, register_user



def test_health_returns_200(c):
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json == {"status": "ok", "database": "ok"}


def test_unknown_api_route_is_json_404(c):
    r = c.get("/api/nope")
    assert r.status_code == 404 and "error" in r.json


def test_security_headers(c):
    h = c.get("/api/health").headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"


def test_cors_allows_configured_origin(c):
    r = c.get("/api/health", headers={"Origin": ORIGIN})
    assert r.headers.get("Access-Control-Allow-Origin") == ORIGIN


def test_cors_blocks_other_origin(c):
    r = c.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in r.headers


def test_cors_preflight(c):
    r = c.options("/api/requests", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                                            "Access-Control-Request-Headers": "authorization,content-type"})
    assert r.status_code == 200 and r.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "authorization" in r.headers["Access-Control-Allow-Headers"].lower()


def test_production_refuses_unsafe_config():
    with pytest.raises(RuntimeError):
        create_app({"TESTING": True, "APP_ENV": "production", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with pytest.raises(RuntimeError):
        create_app({"TESTING": True, "APP_ENV": "production", "SECRET_KEY": "x" * 40, "CORS_ORIGINS": ["*"],
                    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})



def test_passwords_are_bcrypt_hashed(c):
    assert User.query.filter_by(email="buyer@demo.com").one().password_hash.startswith("$2")


def test_missing_garbage_and_tampered_tokens_rejected(c, buyer):
    assert c.get("/api/auth/me").status_code == 401
    assert c.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert c.get("/api/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401
    tampered = buyer["Authorization"][:-3] + "AAA"
    assert c.get("/api/auth/me", headers={"Authorization": tampered}).status_code == 401
    forged = pyjwt.encode({"sub": "1", "exp": time.time() + 600, "type": "access", "fresh": False, "jti": "x"},
                          "wrong-key-wrong-key-wrong-key-123456", algorithm="HS256")
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_expired_token_rejected_with_message(c, app):
    from datetime import timedelta
    tok = create_access_token(identity="1", expires_delta=timedelta(seconds=-5))
    r = c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401 and "expired" in r.json["error"].lower()


def test_token_for_deleted_or_disabled_user_rejected(c, buyer):
    User.query.filter_by(email="buyer@demo.com").one().is_active = False
    db.session.commit()
    assert c.get("/api/auth/me", headers=buyer).status_code == 401


def test_cannot_register_as_admin(c):
    r = c.post("/api/auth/register", json={"email": "a@x.com", "password": "secret123", "full_name": "A", "role": "admin"})
    assert r.status_code == 400


def test_protected_routes_block_guests_and_wrong_roles(c, buyer, dealer, admin):
    guest = [("get", "/api/requests/mine"), ("post", "/api/requests"), ("get", "/api/dealer/stats"),
             ("get", "/api/admin/dealers"), ("post", "/api/dealer/offers")]
    for m, url in guest:
        assert getattr(c, m)(url).status_code == 401, url
    assert c.get("/api/requests/mine", headers=dealer).status_code == 403
    assert c.get("/api/dealer/listings", headers=buyer).status_code == 403
    assert c.get("/api/admin/dealers", headers=dealer).status_code == 403
    assert c.post("/api/requests", headers=admin, json={"max_price": 1000000}).status_code == 403



def test_malformed_json_bodies(c, buyer):
    h = {**buyer, "Content-Type": "application/json"}
    assert c.post("/api/requests", headers=h, data="{not json").status_code == 400
    assert c.post("/api/requests", headers=buyer, json=[1, 2]).status_code == 400
    assert c.post("/api/auth/login", json="x").status_code == 400


@pytest.mark.parametrize("payload", [
    {"password": "short1", "email": "a@x.com", "full_name": "A"},
    {"password": "x" * 80, "email": "a@x.com", "full_name": "A"},
    {"password": "secret123", "email": "not-an-email", "full_name": "A"},
    {"password": "secret123", "email": "a@x.com", "full_name": "   "},
    {"password": "secret123", "email": "a@x.com", "full_name": "A", "county": "Atlantis"},
    {"password": "secret123", "email": "a@x.com", "full_name": "A", "phone": "call me maybe"},
    {"password": "secret123", "email": "a@x.com", "full_name": "A", "role": "dealer", "business_name": "B", "id_number": "BAD"},
    {"password": "secret123", "email": "a@x.com", "full_name": "A" * 500},
])
def test_register_rejects_bad_input(c, payload):
    r = c.post("/api/auth/register", json=payload)
    assert r.status_code == 400 and r.json["error"]


def test_html_is_stripped_from_text_fields(c, buyer):
    r = c.post("/api/requests", headers=buyer, json={
        "max_price": 2000000, "make": "<b>Toyota</b>", "model": "<script>alert(1)</script>Harrier",
        "notes": "Call me <img src=x onerror=alert(1)>\n\n\n\nafter 5pm &lt;script&gt;x&lt;/script&gt;"})
    assert r.status_code == 201
    d = r.json
    assert d["make"] == "Toyota" and d["model"] == "alert(1)Harrier"
    assert "<" not in d["notes"] and "\n\n\n" not in d["notes"]


def test_registration_name_sanitized(c):
    r = register_user(c, {"email": "x@x.com", "password": "secret123", "full_name": "  <i>Jane</i>   Doe\x00 "})
    assert r.status_code == 201 and r.json["user"]["full_name"] == "Jane Doe"


def test_email_is_case_insensitive(c):
    r = c.post("/api/auth/login", json={"email": "  BUYER@Demo.com ", "password": "demo1234"})
    assert r.status_code == 200


@pytest.mark.parametrize("payload", [
    {}, {"max_price": 0}, {"max_price": -5}, {"max_price": "abc"}, {"max_price": 1e30}, {"max_price": "NaN"},
    {"max_price": 1000000, "fuel": "steam"}, {"max_price": 1000000, "body_type": "tank"},
    {"max_price": 1000000, "min_year": 1800}, {"max_price": 1000000, "min_year": "soon"},
    {"max_price": 1000000, "county": "Narnia"}, {"max_price": 1000000, "notes": "x" * 1001},
])
def test_request_rejects_bad_input(c, buyer, payload):
    assert c.post("/api/requests", headers=buyer, json=payload).status_code == 400


def test_request_accepts_form_style_empty_strings(c, buyer):
    r = c.post("/api/requests", headers=buyer, json={"make": "", "model": "", "min_year": "", "max_price": "1500000",
                                                    "fuel": "", "body_type": "", "county": "Nairobi", "notes": "", "days": "30"})
    assert r.status_code == 201 and r.json["max_price"] == 1500000


def test_request_days_clamped(c, buyer):
    r = c.post("/api/requests", headers=buyer, json={"max_price": 1000000, "days": 9999})
    assert r.status_code == 201


LISTING = {"make": "Toyota", "model": "Vitz", "year": 2015, "price": 900000, "fuel": "petrol",
           "transmission": "automatic", "body_type": "hatchback", "county": "Nairobi", "color": "#ffffff"}


@pytest.mark.parametrize("patch", [
    {"year": 1900}, {"year": 2999}, {"year": "abc"}, {"price": 0}, {"price": "free"}, {"fuel": "water"},
    {"transmission": "cvt"}, {"body_type": "boat"}, {"mileage_km": -1}, {"mileage_km": "lots"}, {"status": "weird"},
    {"make": ""}, {"model": "   "}, {"county": "Mars"}, {"color": "<script>"}, {"description": "x" * 4001},
    {"engine_cc": 5},
])
def test_listing_rejects_bad_input(c, dealer, patch):
    assert c.post("/api/dealer/listings", headers=dealer, json={**LISTING, **patch}).status_code == 400


def test_listing_description_sanitized(c, dealer):
    r = c.post("/api/dealer/listings", headers=dealer, json={**LISTING, "description": "Clean <a href='x'>car</a>"})
    assert r.status_code == 201 and r.json["description"] == "Clean car"


def test_review_rating_bounds(c, buyer, dealer):
    req = c.post("/api/requests", headers=buyer, json={"max_price": 2000000}).json
    c.post("/api/dealer/offers", headers=dealer, json={"request_id": req["id"], "price": 1900000})
    oid = c.get("/api/requests/mine", headers=buyer).json[0]["offers"][0]["id"]
    c.post(f"/api/offers/{oid}/accept", headers=buyer)
    for bad in (0, 6, "x", None):
        assert c.post(f"/api/offers/{oid}/review", headers=buyer, json={"rating": bad}).status_code == 400
    assert c.post(f"/api/offers/{oid}/review", headers=buyer, json={"rating": 4, "comment": "<b>ok</b>"}).status_code == 201


def test_offer_validation(c, buyer, dealer):
    req = c.post("/api/requests", headers=buyer, json={"max_price": 2000000}).json
    for bad in ({}, {"request_id": req["id"]}, {"request_id": req["id"], "price": -1}, {"request_id": "x", "price": 5},
                {"request_id": req["id"], "price": 5, "listing_id": "abc"}, {"request_id": req["id"], "price": 5, "message": "m" * 1001}):
        assert c.post("/api/dealer/offers", headers=dealer, json=bad).status_code == 400, bad
    assert c.post("/api/dealer/offers", headers=dealer, json={"request_id": 99999, "price": 5}).status_code == 409


def test_dealer_cannot_attach_someone_elses_listing(c, buyer, dealer):
    req = c.post("/api/requests", headers=buyer, json={"max_price": 2000000}).json
    other = login(c, "capitalautohub@dealers.demo")
    foreign = c.get("/api/dealer/listings", headers=other).json[0]["id"]
    r = c.post("/api/dealer/offers", headers=dealer, json={"request_id": req["id"], "price": 5, "listing_id": foreign})
    assert r.status_code == 403


def test_admin_decision_validation(c, admin):
    uid = c.get("/api/admin/dealers", headers=admin).json[0]["id"]
    assert c.post(f"/api/admin/dealers/{uid}/review", headers=admin, json={}).status_code == 400
    assert c.post("/api/admin/dealers/99999/review", headers=admin, json={"decision": "approved"}).status_code == 404



def test_request_update_and_delete(c, buyer):
    req = c.post("/api/requests", headers=buyer, json={"max_price": 1000000, "make": "Mazda"}).json
    up = c.put(f"/api/requests/{req['id']}", headers=buyer, json={"max_price": 1200000, "make": "Subaru", "days": 10})
    assert up.status_code == 200 and up.json["make"] == "Subaru" and up.json["max_price"] == 1200000
    assert c.get(f"/api/requests/{req['id']}", headers=buyer).json["make"] == "Subaru"
    assert c.put(f"/api/requests/{req['id']}", headers=buyer, json={"max_price": -1}).status_code == 400
    assert c.delete(f"/api/requests/{req['id']}", headers=buyer).status_code == 200
    assert c.get(f"/api/requests/{req['id']}", headers=buyer).status_code == 404


def test_other_buyer_cannot_touch_request(c, buyer):
    req = c.post("/api/requests", headers=buyer, json={"max_price": 1000000}).json
    register_user(c, {"email": "b2@x.com", "password": "secret123", "full_name": "B Two"})
    other = login(c, "b2@x.com", "secret123")
    rid = req["id"]
    assert c.get(f"/api/requests/{rid}", headers=other).status_code == 404
    assert c.put(f"/api/requests/{rid}", headers=other, json={"max_price": 5}).status_code == 404
    assert c.delete(f"/api/requests/{rid}", headers=other).status_code == 404
    assert c.post(f"/api/requests/{rid}/close", headers=other).status_code == 404


def test_fulfilled_request_cannot_be_edited_or_deleted(c, buyer, dealer):
    req = c.post("/api/requests", headers=buyer, json={"max_price": 2000000}).json
    c.post("/api/dealer/offers", headers=dealer, json={"request_id": req["id"], "price": 1900000})
    oid = c.get("/api/requests/mine", headers=buyer).json[0]["offers"][0]["id"]
    assert c.post(f"/api/offers/{oid}/accept", headers=buyer).status_code == 200
    assert c.put(f"/api/requests/{req['id']}", headers=buyer, json={"max_price": 5000000}).status_code == 409
    assert c.delete(f"/api/requests/{req['id']}", headers=buyer).status_code == 409


def test_other_buyer_cannot_act_on_offer(c, buyer, dealer):
    req = c.post("/api/requests", headers=buyer, json={"max_price": 2000000}).json
    c.post("/api/dealer/offers", headers=dealer, json={"request_id": req["id"], "price": 1900000})
    oid = c.get("/api/requests/mine", headers=buyer).json[0]["offers"][0]["id"]
    register_user(c, {"email": "b3@x.com", "password": "secret123", "full_name": "B Three"})
    other = login(c, "b3@x.com", "secret123")
    for action in ("accept", "decline", "review"):
        assert c.post(f"/api/offers/{oid}/{action}", headers=other, json={"rating": 5}).status_code == 404



def _count_queries(app, fn):
    n = []
    def hook(conn, cursor, statement, *a):
        n.append(statement)
    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", hook)
        try:
            fn()
        finally:
            event.remove(db.engine, "before_cursor_execute", hook)
    return len(n)


def test_list_endpoints_use_constant_query_count(c, app, buyer, dealer):
    
    assert _count_queries(app, lambda: c.get("/api/cars")) <= 5
    assert _count_queries(app, lambda: c.get("/api/dealer/offers", headers=dealer)) <= 9
    assert _count_queries(app, lambda: c.get("/api/dealer/requests", headers=dealer)) <= 12
    assert _count_queries(app, lambda: c.get("/api/requests/mine", headers=buyer)) <= 9


def test_production_does_not_load_demo_accounts(tmp_path):
    app = create_app({"APP_ENV": "production", "SECRET_KEY": "p" * 40, "SMTP_HOST": "smtp.example", "CORS_ORIGINS": ["https://app.example"],
                      "BCRYPT_LOG_ROUNDS": 4, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'prod.db'}"})
    with app.app_context():
        assert User.query.count() == 0
        db.drop_all()
