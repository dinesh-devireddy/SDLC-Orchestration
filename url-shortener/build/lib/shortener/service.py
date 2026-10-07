import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from .errors import ServiceError
from .models import Link
from .schemas import RESERVED

MAX_ATTEMPTS = 5


def utc_now():
    return datetime.now(timezone.utc)


def generate_code():
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))


def create_link(session, request, clock=utc_now, code_factory=generate_code):
    now = clock().astimezone(timezone.utc)
    if request.expires_at is not None and request.expires_at <= now:
        raise ServiceError(422, "validation_error", "Expiration must be in the future")
    for _ in range(MAX_ATTEMPTS):
        code = request.alias if request.alias is not None else code_factory()
        if code in RESERVED:
            continue
        link = Link(code=code, destination=str(request.destination), created_at=now,
                    expires_at=request.expires_at, clicks=0)
        session.add(link)
        try:
            session.commit()
            return link
        except IntegrityError:
            session.rollback()
            # Distinguish code collisions from unrelated integrity failures.
            exists = session.scalar(select(Link.code).where(Link.code == code))
            session.rollback()
            if exists is None:
                raise
            if request.alias is not None:
                raise ServiceError(409, "alias_conflict", "Alias is already in use") from None
    raise ServiceError(503, "code_exhausted", "Could not allocate a code; try again")


def get_stats(session, code):
    link = session.get(Link, code)
    if link is None:
        raise ServiceError(404, "not_found", "Short link not found")
    return link


def redirect(session, code, clock=utc_now):
    now = clock().astimezone(timezone.utc)
    # A single conditional UPDATE prevents lost increments and avoids read-then-write locks.
    destination = session.execute(
        update(Link).where(Link.code == code, or_(Link.expires_at.is_(None), Link.expires_at > now))
        .values(clicks=Link.clicks + 1).returning(Link.destination)
    ).scalar_one_or_none()
    if destination is not None:
        session.commit()
        return destination
    session.rollback()
    get_stats(session, code)
    raise ServiceError(410, "expired", "Short link has expired")
