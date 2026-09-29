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
    from backend.models.wardrobe_item import WardrobeItem


class SavedLook(Base):
    """
    SavedLook represents a complete outfit saved by a user.

    This table stores only the saved look itself (name, occasion, total price
    and the fitting-room visualization URL). The individual outfit/product
    details are handled by other tables/models.
    """

    __tablename__ = "saved_looks"

    saved_look_id: Mapped[uuid.UUID] = mapped_column(
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

    # Total outfit price in the application's default currency (INR)
    total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # URL of the generated fitting-room / outfit visualization image (no binary data)
    fitting_room_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="saved_looks")

    wardrobe_items: Mapped[list["WardrobeItem"]] = relationship(
        back_populates="saved_look"
    )

    def __repr__(self) -> str:
        return (
            f"<SavedLook {self.saved_look_id} name={self.name!r} "
            f"user_id={self.user_id}>"
        )