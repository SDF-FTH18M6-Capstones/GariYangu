from flask import Blueprint, jsonify
from sqlalchemy.orm import joinedload

from ..auth import ApiError, login_required
from ..extensions import db
from ..models import DealerProfile, User, utcnow
from ..schemas import DealerDecisionSchema, load

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/dealers")
@login_required("admin")
def all_dealers():
    rows = User.query.join(DealerProfile).options(joinedload(User.dealer)).order_by(User.id.desc()).all()
    return jsonify([u.to_dict() for u in rows])


@bp.post("/dealers/<int:uid>/review")
@login_required("admin")
def review_dealer(uid):
    d = load(DealerDecisionSchema)
    u = db.session.get(User, uid)
    if not u or not u.dealer:
        raise ApiError("Dealer not found.", 404)
    p = u.dealer
    if d["decision"] == "approved":
        p.status, p.rejection_reason, p.verified_at = "approved", "", utcnow()
    else:
        p.status, p.rejection_reason, p.verified_at = "rejected", d["reason"], None
    db.session.commit()
    return jsonify(ok=True)