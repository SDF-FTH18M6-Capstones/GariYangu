import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.orm import joinedload, selectinload

from ..auth import ApiError, login_required
from ..extensions import db
from ..models import BuyerRequest, Listing, ListingImage, Offer
from ..models import utcnow
from ..schemas import ListingSchema, OfferSchema, StatusSchema, load
from ..services import dealer_info, expand_offers

bp = Blueprint("dealer", __name__, url_prefix="/api/dealer")


def _approved():
    p = g.user.dealer
    return bool(p and p.status == "approved")


def _live_requests():
    return BuyerRequest.query.filter(BuyerRequest.status == "open", BuyerRequest.expires_at > utcnow())


@bp.get("/requests")
@login_required("dealer")
def open_requests():
    rows = (_live_requests().options(selectinload(BuyerRequest.offers).joinedload(Offer.listing), joinedload(BuyerRequest.buyer))
            .order_by(BuyerRequest.id.desc()).all())
    mine = {}
    for r in rows:
        mo = next((o for o in r.offers if o.status != "withdrawn" and o.dealer_id == g.user.id), None)
        if mo:
            mine[r.id] = mo
    expanded = {o.id: e for o, e in zip(mine.values(), expand_offers(mine.values()))}
    out = []
    for r in rows:
        live = [o for o in r.offers if o.status != "withdrawn"]
        d = r.base_dict()
        d.update(buyer_name=(r.buyer.full_name or "Buyer").split(" ")[0], offer_count=len(live),
                 my_offer=expanded[mine[r.id].id] if r.id in mine else None)
        out.append(d)
    return jsonify(out)


@bp.post("/offers")
@login_required("dealer")
def submit_offer():
    if not _approved():
        raise ApiError("Your dealer account must be approved before you can send offers.", 403)
    d = load(OfferSchema)
    r = db.session.get(BuyerRequest, d["request_id"])
    if not r or not r.is_live:
        raise ApiError("This request is no longer open.", 409)
    listing_id = d["listing_id"]
    if listing_id and not Listing.query.filter_by(id=listing_id, owner_id=g.user.id).first():
        raise ApiError("That listing isn't yours.", 403)
    existing = Offer.query.filter_by(request_id=r.id, dealer_id=g.user.id).first()
    if existing and existing.status != "withdrawn":
        raise ApiError("You already sent an offer on this request.", 409)
    if existing:  # re-offer after withdrawing
        o = existing
        o.created_at = utcnow()
    else:
        o = Offer(request_id=r.id, dealer_id=g.user.id)
        db.session.add(o)
    o.price, o.message, o.listing_id, o.status = d["price"], d["message"], listing_id, "pending"
    db.session.commit()
    return jsonify(ok=True), 201


@bp.post("/offers/<int:oid>/withdraw")
@login_required("dealer")
def withdraw_offer(oid):
    o = Offer.query.filter_by(id=oid, dealer_id=g.user.id).first()
    if not o:
        raise ApiError("Offer not found.", 404)
    if o.status != "pending":
        raise ApiError("Only pending offers can be withdrawn.", 409)
    o.status = "withdrawn"
    db.session.commit()
    return jsonify(ok=True)


@bp.get("/offers")
@login_required("dealer")
def my_offers():
    rows = (Offer.query.options(joinedload(Offer.request), joinedload(Offer.listing))
            .filter_by(dealer_id=g.user.id).order_by(Offer.id.desc()).all())
    out = []
    for o, e in zip(rows, expand_offers(rows, reveal=True)):
        e.update(request_title=o.request.title, request_county=o.request.county)
        out.append(e)
    return jsonify(out)


@bp.get("/stats")
@login_required("dealer")
def stats():
    uid = g.user.id
    county = g.user.dealer.county if g.user.dealer else None
    q = _live_requests()
    if county:
        q = q.filter(BuyerRequest.county == county)
    mine = Offer.query.filter(Offer.dealer_id == uid, Offer.status != "withdrawn")
    return jsonify(
        active_listings=Listing.query.filter_by(owner_id=uid, status="active").count(),
        open_requests=q.count(), offers_sent=mine.count(), accepted=mine.filter(Offer.status == "accepted").count(),
        rating=dealer_info(uid)["rating"],
    )


# ---- listings ----
def _clean_listing():
    d = load(ListingSchema)
    d["county"] = d["county"] or g.user.county or ""
    if not d["county"]:
        raise ApiError("Choose a county.")
    return d


@bp.get("/listings")
@login_required("dealer")
def my_listings():
    rows = Listing.query.options(selectinload(Listing.images)).filter_by(owner_id=g.user.id).order_by(Listing.id.desc()).all()
    return jsonify([l.to_dict() for l in rows])


@bp.post("/listings")
@login_required("dealer")
def create_listing():
    l = Listing(owner_id=g.user.id, **_clean_listing())
    db.session.add(l)
    db.session.commit()
    return jsonify(l.to_dict()), 201


def _own_listing(lid):
    l = Listing.query.filter_by(id=lid, owner_id=g.user.id).first()
    if not l:
        raise ApiError("Listing not found.", 404)
    return l


@bp.put("/listings/<int:lid>")
@login_required("dealer")
def update_listing(lid):
    l = _own_listing(lid)
    for k, v in _clean_listing().items():
        setattr(l, k, v)
    db.session.commit()
    return jsonify(l.to_dict())


@bp.post("/listings/<int:lid>/status")
@login_required("dealer")
def listing_status(lid):
    status = load(StatusSchema)["status"]
    _own_listing(lid).status = status
    db.session.commit()
    return jsonify(ok=True)


@bp.delete("/listings/<int:lid>")
@login_required("dealer")
def delete_listing(lid):
    l = _own_listing(lid)
    Offer.query.filter_by(listing_id=lid).update({"listing_id": None})
    photo_paths = [_image_storage() / image.filename for image in l.images]
    db.session.delete(l)
    db.session.commit()
    for path in photo_paths:
        path.unlink(missing_ok=True)
    return jsonify(ok=True)


# ---- listing photo management ----
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_LISTING_IMAGES = 10


def _image_storage():
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@bp.post("/listings/<int:lid>/images")
@login_required("dealer")
def upload_listing_images(lid):
    listing = _own_listing(lid)
    files = request.files.getlist("images")
    if not files or all(not f.filename for f in files):
        raise ApiError("Choose at least one photo to upload.")
    existing_count = len(listing.images)
    selected = [f for f in files if f and f.filename]
    if existing_count + len(selected) > MAX_LISTING_IMAGES:
        raise ApiError(f"A listing can have at most {MAX_LISTING_IMAGES} photos. You can add {MAX_LISTING_IMAGES - existing_count} more.")

    folder = _image_storage()
    created = []
    try:
        for upload in selected:
            raw = upload.read(MAX_IMAGE_BYTES + 1)
            if len(raw) > MAX_IMAGE_BYTES:
                raise ApiError("Each photo must be 5 MB or smaller.")
            if not raw:
                raise ApiError("One of the selected photos is empty.")
            try:
                source = Image.open(io.BytesIO(raw))
                if source.format not in ALLOWED_IMAGE_FORMATS:
                    raise ApiError("Use JPG, PNG or WebP photos only.")
                source.verify()
                source = Image.open(io.BytesIO(raw))
                source = ImageOps.exif_transpose(source)
                if source.width < 320 or source.height < 200:
                    raise ApiError("Photos must be at least 320 × 200 pixels.")
                source.thumbnail((2400, 1800), Image.Resampling.LANCZOS)
                if source.mode not in ("RGB", "RGBA"):
                    source = source.convert("RGB")
                filename = f"{uuid.uuid4().hex}.webp"
                destination = folder / filename
                source.save(destination, "WEBP", quality=84, method=6)
            except (UnidentifiedImageError, OSError, ValueError):
                raise ApiError("One of the files is not a valid image. Please choose JPG, PNG or WebP photos.")

            image = ListingImage(listing_id=listing.id, filename=filename, is_primary=(existing_count == 0 and not created))
            db.session.add(image)
            created.append((image, destination))

        db.session.commit()
    except Exception:
        db.session.rollback()
        for _, path in created:
            path.unlink(missing_ok=True)
        raise

    return jsonify(images=[image.to_dict() for image, _ in created]), 201


@bp.post("/listings/<int:lid>/images/<int:image_id>/primary")
@login_required("dealer")
def set_primary_listing_image(lid, image_id):
    listing = _own_listing(lid)
    image = ListingImage.query.filter_by(id=image_id, listing_id=listing.id).first()
    if not image:
        raise ApiError("Photo not found.", 404)
    for item in listing.images:
        item.is_primary = item.id == image.id
    db.session.commit()
    return jsonify(images=[item.to_dict() for item in listing.images])


@bp.delete("/listings/<int:lid>/images/<int:image_id>")
@login_required("dealer")
def delete_listing_image(lid, image_id):
    listing = _own_listing(lid)
    image = ListingImage.query.filter_by(id=image_id, listing_id=listing.id).first()
    if not image:
        raise ApiError("Photo not found.", 404)
    was_primary = image.is_primary
    path = _image_storage() / image.filename
    db.session.delete(image)
    db.session.flush()
    remaining = [item for item in listing.images if item.id != image_id]
    if was_primary and remaining:
        remaining[0].is_primary = True
    db.session.commit()
    path.unlink(missing_ok=True)
    return jsonify(images=[item.to_dict() for item in ListingImage.query.filter_by(listing_id=listing.id).order_by(ListingImage.is_primary.desc(), ListingImage.id.asc()).all()])
