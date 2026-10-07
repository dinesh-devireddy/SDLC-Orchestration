from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCInstant(TypeDecorator):
    """Fixed-width UTC ISO text; SQLite has no native timezone-aware timestamp."""
    impl = String(27)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone-aware datetime required")
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def process_result_value(self, value, dialect):
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class Base(DeclarativeBase):
    pass


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (CheckConstraint("clicks >= 0", name="ck_links_clicks"),)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    destination: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCInstant())
    expires_at: Mapped[datetime | None] = mapped_column(UTCInstant(), nullable=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
