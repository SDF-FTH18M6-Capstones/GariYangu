
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload

from .extensions import db
from .models import BuyerRequest, Listing, Offer, Review, User, iso, num


def _info(user_id, u, rating):
    p = u.dealer if u else None
    avg, cnt = rating if rating else (None, 0)
    return {
        "id": user_id,
        "name": (p.business_name if p else None) or (u.full_name if u else "Dealer"),
        "verified": bool(p and p.status == "approved"),
        "county": (p.county if p else None) or (u.county if u else ""),
        "phone": (u.phone if u else "") or "",
        "rating": round(float(avg), 1) if cnt else None,
        "review_count": cnt,
    }


def dealer_infos(user_ids):
    
    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    users = {u.id: u for u in User.query.options(joinedload(User.dealer)).filter(User.id.in_(ids))}
    ratings = {d: (a, c) for d, a, c in db.session.query(Review.dealer_id, func.avg(Review.rating), func.count(Review.id))
               .filter(Review.dealer_id.in_(ids)).group_by(Review.dealer_id)}
    return {i: _info(i, users.get(i), ratings.get(i)) for i in ids}


def dealer_info(user_id):
    return dealer_infos([user_id])[user_id]


def reviewed_offer_ids(offer_ids):
    ids = list(offer_ids)
    if not ids:
        return set()
    return {i for (i,) in db.session.query(Review.offer_id).filter(Review.offer_id.in_(ids))}


def public_listings(listings):
    infos = dealer_infos(l.owner_id for l in listings)
    out = []
    for l in listings:
        d = l.to_dict()
        info = infos[l.owner_id]
        d.update(dealer=info["name"], verified=info["verified"], dealer_info=info)
        out.append(d)
    return out


def listing_public(l):
    return public_listings([l])[0]


def expand_offer(o, reveal=False, infos=None, reviewed=None):
    infos = infos if infos is not None else dealer_infos([o.dealer_id])
    reviewed = reviewed if reviewed is not None else reviewed_offer_ids([o.id])
    info = dict(infos[o.dealer_id])
    info["phone"] = info["phone"] if (reveal or o.status == "accepted") else None
    l = o.listing
    return {
        "id": o.id, "request_id": o.request_id, "dealer_id": o.dealer_id, "listing_id": o.listing_id,
        "price": num(o.price), "message": o.message or "", "status": o.status, "created_at": iso(o.created_at),
        "dealer": info,
        "listing": {"id": l.id, "title": f"{l.year} {l.make} {l.model}", "mileage_km": l.mileage_km,
                    "body_type": l.body_type, "color": l.color} if l else None,
        "reviewed": o.id in reviewed,
    }


def expand_offers(offers, reveal=False):
    offers = list(offers)
    infos = dealer_infos(o.dealer_id for o in offers)
    reviewed = reviewed_offer_ids(o.id for o in offers)
    return [expand_offer(o, reveal, infos, reviewed) for o in offers]


def request_query():
   
    return BuyerRequest.query.options(selectinload(BuyerRequest.offers).joinedload(Offer.listing), joinedload(BuyerRequest.buyer))


def expand_requests(rows):
    rows = list(rows)
    all_offers = [o for r in rows for o in r.offers if o.status != "withdrawn"]
    infos = dealer_infos(o.dealer_id for o in all_offers)
    reviewed = reviewed_offer_ids(o.id for o in all_offers)
    out = []
    for r in rows:
        live = sorted((o for o in r.offers if o.status != "withdrawn"), key=lambda o: o.price)
        d = r.base_dict()
        d.update(expired=r.status == "open" and not r.is_live, offers=[expand_offer(o, False, infos, reviewed) for o in live])
        out.append(d)
    return out


def expand_request(r):
    return expand_requests([r])[0]


def listing_query():
    return Listing.query.options(selectinload(Listing.images))
