from datetime import timedelta
from functools import wraps

from flask import current_app, g, jsonify
from flask_jwt_extended import create_access_token, get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import ExpiredSignatureError, PyJWTError

from .extensions import db, jwt
from .models import User


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def make_token(user):
    return create_access_token(identity=str(user.id), expires_delta=timedelta(hours=current_app.config["TOKEN_HOURS"]))


# ---- Flask-JWT-Extended error callbacks: always answer with our {"error": ...} shape ----
@jwt.unauthorized_loader
def _missing(reason):
    return jsonify(error="Please sign in."), 401


@jwt.invalid_token_loader
def _invalid(reason):
    return jsonify(error="Your session is invalid. Please sign in again."), 401


@jwt.expired_token_loader
def _expired(header, data):
    return jsonify(error="Your session has expired. Please sign in again."), 401


def _current_user():
    try:
        verify_jwt_in_request()
        user = db.session.get(User, int(get_jwt_identity()))
    except ExpiredSignatureError:
        raise ApiError("Your session has expired. Please sign in again.", 401)
    except (JWTExtendedException, PyJWTError, ValueError, TypeError):
        return None
    return user if user and user.is_active else None


def login_required(*roles):
    """@login_required() = any signed-in user; @login_required('dealer') = that role only."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            user = _current_user()
            if not user:
                return jsonify(error="Please sign in."), 401
            if roles and user.role not in roles:
                return jsonify(error="You don't have access to this."), 403
            g.user = user
            return fn(*a, **kw)
        return wrapper
    return deco
