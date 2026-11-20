
import html
import math
import re
from datetime import datetime, timezone

from flask import request
from marshmallow import EXCLUDE, Schema, ValidationError, fields, post_load, pre_load, validate, validates_schema

from .auth import ApiError
from .constants import BODIES, COUNTIES, FUELS, LISTING_STATUSES, ROLES_SELF_SERVICE, TRANSMISSIONS

TAG_RE = re.compile(r"<[^>]*>")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ID_RE = re.compile(r"^\d{7,8}$")  
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")
COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|[A-Za-z ]{1,30})$")
MAX_MONEY = 10**10


def sanitize(text, multiline=False):
    text = html.unescape(text)
    text = TAG_RE.sub("", text)
    text = CTRL_RE.sub("", text)
    text = text.replace("<", "").replace(">", "")
    if multiline:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text.strip()


class Clean(fields.String):

    def __init__(self, max=255, multiline=False, **kw):
        self.multiline = multiline
        extra = kw.pop("validate", None)
        extra = [extra] if callable(extra) else list(extra or [])
        kw["validate"] = [validate.Length(max=max, error=f"Must be at most {max} characters.")] + extra
        super().__init__(**kw)

    def _deserialize(self, value, attr, data, **kw):
        text = sanitize(super()._deserialize(value, attr, data, **kw), self.multiline)
        if not text and self.required:  
            raise self.make_error("required")
        return text


def _county(**kw):
    return Clean(max=50, validate=validate.OneOf(COUNTIES, error="Choose a valid Kenyan county."), **kw)


def _money(msg, **kw):
    em = {"invalid": msg, **kw.pop("error_messages", {})}
    return fields.Float(validate=validate.Range(min=1, max=MAX_MONEY, error=msg), error_messages=em, **kw)


def _one_of(values, msg, **kw):
    return Clean(max=20, validate=validate.OneOf(values, error=msg), **kw)


class Base(Schema):
    class Meta:
        unknown = EXCLUDE 

    @pre_load
    def blank_to_missing(self, data, **kw):
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items() if v not in ("", None)}

    @validates_schema
    def _finite(self, data, **kw):
        for k, v in data.items():
            if isinstance(v, float) and not math.isfinite(v):
                raise ValidationError("Enter a valid number.", k)


class LoginSchema(Base):
    email = Clean(max=254, required=True, error_messages={"required": "Enter your email."})
    password = fields.String(required=True, validate=validate.Length(max=128), error_messages={"required": "Enter your password."})

    @post_load
    def lower(self, d, **kw):
        d["email"] = d["email"].lower()
        return d


class RegisterSchema(Base):
    email = Clean(max=254, required=True, validate=validate.Email(error="Enter a valid email address."),
                  error_messages={"required": "Enter a valid email address."})
    password = fields.String(required=True, error_messages={"required": "Password must be at least 8 characters."})
    full_name = Clean(max=150, required=True, error_messages={"required": "Enter your full name."})
    phone = Clean(max=20, load_default="", validate=validate.Regexp(PHONE_RE, error="Enter a valid phone number."))
    role = _one_of(ROLES_SELF_SERVICE, "Choose buyer or dealer.", load_default="buyer")
    county = _county(load_default="")
    business_name = Clean(max=150, load_default="")
    id_number = Clean(max=20, load_default="")
    address = Clean(max=255, load_default="")

    @validates_schema
    def rules(self, d, **kw):
        pw = d.get("password", "")
        if not 8 <= len(pw) <= 72 or len(pw.encode()) > 72:  
            raise ValidationError("Password must be 8 to 72 characters.", "password")
        if not d.get("full_name"):
            raise ValidationError("Enter your full name.", "full_name")
        if d.get("role") == "dealer":
            if not d.get("business_name"):
                raise ValidationError("Enter your business name.", "business_name")
            if not ID_RE.match(d.get("id_number", "")):
                raise ValidationError("Enter a valid National ID number (7 or 8 digits).", "id_number")

    @post_load
    def normalise(self, d, **kw):
        d["email"] = d["email"].lower()
        return d


YEAR_MAX = lambda: datetime.now(timezone.utc).year + 1


class RequestSchema(Base):
    make = Clean(max=60, load_default="")
    model = Clean(max=80, load_default="")
    min_year = fields.Integer(strict=False, load_default=None, error_messages={"invalid": "Invalid year."})
    max_price = _money("Enter your maximum budget.", required=True, error_messages={"required": "Enter your maximum budget."})
    fuel = _one_of(FUELS, "Invalid fuel or body type.", load_default="")
    body_type = _one_of(BODIES, "Invalid fuel or body type.", load_default="")
    county = _county(load_default="")
    notes = Clean(max=1000, multiline=True, load_default="")
    days = fields.Integer(strict=False, load_default=30, error_messages={"invalid": "Invalid duration."})

    @validates_schema
    def year_range(self, d, **kw):
        y = d.get("min_year")
        if y is not None and not 1950 <= y <= YEAR_MAX():
            raise ValidationError("Invalid year.", "min_year")

    @post_load
    def clamp_days(self, d, **kw):
        d["days"] = min(max(d["days"], 1), 90)
        return d


class VerifySignupSchema(Base):
    email = Clean(max=254, required=True, error_messages={"required": "Enter your email."})
    code = Clean(max=6, required=True, validate=validate.Regexp(r"^\d{6}$", error="Enter the 6-digit code."),
                 error_messages={"required": "Enter the 6-digit code."})

    @post_load
    def lower(self, d, **kw):
        d["email"] = d["email"].lower()
        return d


class ResendSchema(Base):
    email = Clean(max=254, required=True, error_messages={"required": "Enter your email."})

    @post_load
    def lower(self, d, **kw):
        d["email"] = d["email"].lower()
        return d


class ResetPasswordSchema(Base):
    email = Clean(max=254, required=True, error_messages={"required": "Enter your email."})
    code = Clean(max=6, required=True, validate=validate.Regexp(r"^\d{6}$", error="Enter the 6-digit code."),
                 error_messages={"required": "Enter the 6-digit code."})
    password = fields.String(required=True, error_messages={"required": "Password must be 8 to 72 characters."})

    @validates_schema
    def rules(self, d, **kw):
        pw = d.get("password", "")
        if not 8 <= len(pw) <= 72 or len(pw.encode()) > 72:
            raise ValidationError("Password must be 8 to 72 characters.", "password")

    @post_load
    def lower(self, d, **kw):
        d["email"] = d["email"].lower()
        return d


class OfferSchema(Base):
    request_id = fields.Integer(strict=False, required=True, error_messages={"required": "Choose a request.", "invalid": "Choose a request."})
    price = _money("Enter a valid price.", required=True, error_messages={"required": "Enter a valid price."})
    listing_id = fields.Integer(strict=False, load_default=None, error_messages={"invalid": "Choose a valid listing."})
    message = Clean(max=1000, multiline=True, load_default="")


class ReviewSchema(Base):
    rating = fields.Integer(strict=False, required=True, validate=validate.Range(min=1, max=5, error="Rating must be between 1 and 5."),
                            error_messages={"required": "Rating must be between 1 and 5.", "invalid": "Rating must be between 1 and 5."})
    comment = Clean(max=1000, multiline=True, load_default="")


class DealerDecisionSchema(Base):
    decision = _one_of(("approved", "rejected"), "Decision must be 'approved' or 'rejected'.", required=True,
                       error_messages={"required": "Decision must be 'approved' or 'rejected'."})
    reason = Clean(max=500, load_default="")


class StatusSchema(Base):
    status = _one_of(LISTING_STATUSES, "Invalid status.", required=True, error_messages={"required": "Invalid status."})


class ListingSchema(Base):
    make = Clean(max=60, required=True, error_messages={"required": "Make and model are required."})
    model = Clean(max=80, required=True, error_messages={"required": "Make and model are required."})
    year = fields.Integer(strict=False, required=True, error_messages={"required": "Year and price are required.", "invalid": "Enter a valid year."})
    price = _money("Enter a valid price.", required=True, error_messages={"required": "Year and price are required."})
    mileage_km = fields.Integer(strict=False, load_default=None, validate=validate.Range(min=0, max=3_000_000, error="Enter a valid mileage."),
                                error_messages={"invalid": "Enter a valid mileage."})
    fuel = _one_of(FUELS, "Choose a valid fuel and transmission.", required=True, error_messages={"required": "Choose a valid fuel and transmission."})
    transmission = _one_of(TRANSMISSIONS, "Choose a valid fuel and transmission.", required=True,
                           error_messages={"required": "Choose a valid fuel and transmission."})
    body_type = _one_of(BODIES, "Invalid body type.", load_default=None)
    color = Clean(max=30, load_default=None, validate=validate.Regexp(COLOR_RE, error="Invalid colour."))
    engine_cc = fields.Integer(strict=False, load_default=None, validate=validate.Range(min=50, max=20000, error="Enter a valid engine size."),
                               error_messages={"invalid": "Enter a valid engine size."})
    county = _county(load_default="")
    description = Clean(max=4000, multiline=True, load_default="")
    status = _one_of(LISTING_STATUSES, "Invalid status.", load_default="active")

    @validates_schema
    def year_range(self, d, **kw):
        if not 1980 <= d["year"] <= YEAR_MAX():
            raise ValidationError("Enter a valid year.", "year")


_DEFAULT_PREFIXES = ("Missing data", "Not a valid", "Must be", "Length must", "Shorter than", "Longer than",
                     "Field may not be null", "Invalid input type")


def _first_message(errors):
    for field, msgs in errors.items():
        if isinstance(msgs, dict):  # nested
            return _first_message(msgs)
        msg = msgs[0] if isinstance(msgs, list) else str(msgs)
        if msg.startswith(_DEFAULT_PREFIXES):
            return f"{field.replace('_', ' ').capitalize()}: {msg[0].lower()}{msg[1:]}"
        return msg
    return "Invalid input."


def load(schema_cls, data=None):
    
    if data is None:
        data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Send a JSON object.")
    try:
        return schema_cls().load(data)
    except ValidationError as e:
        raise ApiError(_first_message(e.normalized_messages()))
