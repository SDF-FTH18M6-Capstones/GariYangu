import hmac
import secrets
from datetime import timedelta
from hashlib import sha256

from flask import Blueprint, current_app, g, jsonify

from ..auth import ApiError, login_required, make_token
from ..extensions import db
from ..mail import send_reset_code, send_signup_code
from ..models import DealerProfile, PasswordReset, SignupOtp, User, utcnow
from ..schemas import LoginSchema, RegisterSchema, ResendSchema, ResetPasswordSchema, VerifySignupSchema, load

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login():
    d = load(LoginSchema)
    u = User.query.filter_by(email=d["email"]).first()
    if not u or not u.check_password(d["password"]):
        raise ApiError("Wrong email or password.", 401)
    if not u.is_active:
        raise ApiError("This account is disabled.", 403)
    return jsonify(token=make_token(u), user=u.to_dict())




def _hash_code(email, code):
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{email}:{code}".encode(), sha256).hexdigest()


def _check_available(email, role, id_number):
    if User.query.filter_by(email=email).first():
        raise ApiError("An account with this email already exists.", 409)
    if role == "dealer" and DealerProfile.query.filter_by(id_number=id_number).first():
        raise ApiError("That ID number is already registered.", 409)


def _issue_code(pending):
    cfg = current_app.config
    code = f"{secrets.randbelow(10**6):06d}"
    now = utcnow()
    pending.code_hash = _hash_code(pending.email, code)
    pending.attempts = 0
    pending.last_sent_at = now
    pending.expires_at = now + timedelta(minutes=cfg["OTP_TTL_MINUTES"])
    db.session.add(pending)
    db.session.commit()
    send_signup_code(pending.email, pending.payload["full_name"], code, cfg["OTP_TTL_MINUTES"])


def _sent_response(pending):
    cfg = current_app.config
    return jsonify(email=pending.email, expires_in=cfg["OTP_TTL_MINUTES"] * 60,
                   resend_after=cfg["OTP_RESEND_SECONDS"]), 202


def _cooldown(pending):
    wait = current_app.config["OTP_RESEND_SECONDS"] - (utcnow() - pending.last_sent_at).total_seconds()
    if wait > 0:
        raise ApiError(f"Please wait {int(wait) + 1} seconds before requesting another code.", 429)


@bp.post("/register")
def register():
    d = load(RegisterSchema)
    _check_available(d["email"], d["role"], d["id_number"])

    pending = SignupOtp.query.filter_by(email=d["email"]).first()
    if pending:
        _cooldown(pending)
    else:
        pending = SignupOtp(email=d["email"])
    u = User()
    u.set_password(d.pop("password"))  
    pending.payload = {**d, "password_hash": u.password_hash}
    _issue_code(pending)
    return _sent_response(pending)


@bp.post("/register/resend")
def resend():
    d = load(ResendSchema)
    pending = SignupOtp.query.filter_by(email=d["email"]).first()
    if not pending:
        raise ApiError("No signup in progress for this email. Please start again.", 404)
    _cooldown(pending)
    _issue_code(pending)
    return _sent_response(pending)


@bp.post("/register/verify")
def verify():
    d = load(VerifySignupSchema)
    cfg = current_app.config
    pending = SignupOtp.query.filter_by(email=d["email"]).first()
    if not pending:
        raise ApiError("No signup in progress for this email. Please start again.", 404)
    if pending.expires_at < utcnow():
        raise ApiError("That code has expired. Request a new one.", 400)
    if pending.attempts >= cfg["OTP_MAX_ATTEMPTS"]:
        raise ApiError("Too many wrong codes. Request a new one.", 429)
    if not hmac.compare_digest(pending.code_hash, _hash_code(pending.email, d["code"])):
        pending.attempts += 1
        db.session.commit()
        raise ApiError("That code is incorrect.", 400)

    p = pending.payload
    _check_available(p["email"], p["role"], p.get("id_number", ""))  
    u = User(email=p["email"], full_name=p["full_name"], phone=p["phone"], role=p["role"], county=p["county"],
             password_hash=p["password_hash"])
    if p["role"] == "dealer":
        u.dealer = DealerProfile(business_name=p["business_name"], id_number=p["id_number"], county=p["county"],
                                 address=p["address"], status="pending")
    db.session.add(u)
    db.session.delete(pending)
    db.session.commit()
    return jsonify(token=make_token(u), user=u.to_dict()), 201


@bp.post("/forgot")
def forgot():
    d = load(ResendSchema)
    cfg = current_app.config
    u = User.query.filter_by(email=d["email"]).first()
    if u and u.is_active:
        row = PasswordReset.query.filter_by(email=u.email).first()
        too_soon = row and (utcnow() - row.last_sent_at).total_seconds() < cfg["OTP_RESEND_SECONDS"]
        if not too_soon:
            code = f"{secrets.randbelow(10**6):06d}"
            row = row or PasswordReset(email=u.email)
            row.code_hash = _hash_code("reset:" + u.email, code)
            row.attempts = 0
            row.last_sent_at = utcnow()
            row.expires_at = row.last_sent_at + timedelta(minutes=cfg["OTP_TTL_MINUTES"])
            db.session.add(row)
            db.session.commit()
            send_reset_code(u.email, u.full_name, code, cfg["OTP_TTL_MINUTES"])
    return jsonify(message="If that email has an account, we sent a code to it.",
                   expires_in=cfg["OTP_TTL_MINUTES"] * 60, resend_after=cfg["OTP_RESEND_SECONDS"]), 202


@bp.post("/reset")
def reset():
    d = load(ResetPasswordSchema)
    cfg = current_app.config
    row = PasswordReset.query.filter_by(email=d["email"]).first()
    u = User.query.filter_by(email=d["email"]).first()
    if not row or not u or not u.is_active:
        raise ApiError("That code is incorrect or has expired. Request a new one.", 400)
    if row.expires_at < utcnow():
        raise ApiError("That code has expired. Request a new one.", 400)
    if row.attempts >= cfg["OTP_MAX_ATTEMPTS"]:
        raise ApiError("Too many wrong codes. Request a new one.", 429)
    if not hmac.compare_digest(row.code_hash, _hash_code("reset:" + row.email, d["code"])):
        row.attempts += 1
        db.session.commit()
        raise ApiError("That code is incorrect.", 400)
    u.set_password(d["password"])
    db.session.delete(row)
    db.session.commit()
    return jsonify(message="Password updated. You can log in now.")


@bp.get("/me")
@login_required()
def me():
    return jsonify(g.user.to_dict())
