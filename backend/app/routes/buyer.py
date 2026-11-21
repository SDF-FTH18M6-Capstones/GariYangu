from datetime import timedelta

from flask import Blueprint, g, jsonify

from ..auth import ApiError, login_required
from ..extensions import db
from ..models import BuyerRequest, Offer, Review, utcnow
from ..schemas import RequestSchema, ReviewSchema, load
from ..services import expand_request, expand_requests, request_query

bp = Blueprint("buyer", __name__, url_prefix="/api")


def _apply(r, d):
    r.make, r.model, r.min_year, r.max_price = d["make"], d["model"], d["min_year"], d["max_price"]
    r.fuel, r.body_type, r.county, r.notes = d["fuel"], d["body_type"], d["county"], d["notes"]


@bp.post("/requests")
@login_required("buyer")
def create_request():
    d = load(RequestSchema)
    r = BuyerRequest(buyer_id=g.user.id, expires_at=utcnow() + timedelta(days=d["days"]))
    _apply(r, d)
    db.session.add(r)
    db.session.commit()
    return jsonify(expand_request(r)), 201


@bp.get("/requests/mine")
@login_required("buyer")
def my_requests():
    rows = request_query().filter_by(buyer_id=g.user.id).order_by(BuyerRequest.id.desc()).all()
    return jsonify(expand_requests(rows))


def _own_request(rid):
    r = BuyerRequest.query.filter_by(id=rid, buyer_id=g.user.id).first()
    if not r:
        raise ApiError("Request not found.", 404)
    return r


def _own_offer(oid):
    o = db.session.get(Offer, oid)
    if not o or o.request.buyer_id != g.user.id:
        raise ApiError("Offer not found.", 404)
    return o


@bp.get("/requests/<int:rid>")
@login_required("buyer")
def get_request(rid):
    return jsonify(expand_request(_own_request(rid)))


@bp.put("/requests/<int:rid>")
@login_required("buyer")
def update_request(rid):
    r = _own_request(rid)
    if r.status != "open":
        raise ApiError("Only open requests can be edited.", 409)
    d = load(RequestSchema)
    _apply(r, d)
    r.expires_at = utcnow() + timedelta(days=d["days"])
    db.session.commit()
    return jsonify(expand_request(r))


@bp.delete("/requests/<int:rid>")
@login_required("buyer")
def delete_request(rid):
    r = _own_request(rid)
    if r.status == "fulfilled":
        raise ApiError("A fulfilled request can't be deleted. It's your record of the deal.", 409)
    db.session.delete(r)  # offers are removed with it (cascade)
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/requests/<int:rid>/close")
@login_required("buyer")
def close_request(rid):
    r = _own_request(rid)
    r.status = "closed"
    for o in r.offers:
        if o.status == "pending":
            o.status = "declined"
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/offers/<int:oid>/accept")
@login_required("buyer")
def accept_offer(oid):
    o = _own_offer(oid)
    r = o.request
    if r.status != "open":
        raise ApiError("This request is no longer open.", 409)
    if o.status != "pending":
        raise ApiError("This offer can no longer be accepted.", 409)
    for x in r.offers:
        if x.id == o.id:
            x.status = "accepted"
        elif x.status == "pending":
            x.status = "declined"
    r.status = "fulfilled"
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/offers/<int:oid>/decline")
@login_required("buyer")
def decline_offer(oid):
    o = _own_offer(oid)
    if o.status != "pending":
        raise ApiError("Only pending offers can be declined.", 409)
    o.status = "declined"
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/offers/<int:oid>/review")
@login_required("buyer")
def review_offer(oid):
    o = _own_offer(oid)
    if o.status != "accepted":
        raise ApiError("You can only review a dealer after accepting their offer.", 409)
    if Review.query.filter_by(offer_id=oid).first():
        raise ApiError("You already reviewed this deal.", 409)
    d = load(ReviewSchema)
    db.session.add(Review(reviewer_id=g.user.id, dealer_id=o.dealer_id, offer_id=oid, rating=d["rating"], comment=d["comment"]))
    db.session.commit()
    return jsonify(ok=True), 201
