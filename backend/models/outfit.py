from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base

if TYPE_CHECKING:
    from backend.models.user import User


class Outfit(Base):
    """
    Outfit represents a complete outfit generated/assembled by the AI Stylist.

    It is the generated outfit itself, distinct from a Product (one shopping
    item), a WardrobeItem (one product saved by a user) and a SavedLook (an
    outfit the user explicitly saves). Product details such as brand, title,
    URL, image and price are not duplicated here; they belong to Product.
    """

    __tablename__ = "outfits"

    outfit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    occasion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Total outfit price in INR
    total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # URL of the fitting-room visualization (no image binary stored)
    fitting_room_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="outfits")

    def __repr__(self) -> str:
        return (
            f"<Outfit {self.outfit_id} name={self.name!r} "
            f"user_id={self.user_id}>"
        )