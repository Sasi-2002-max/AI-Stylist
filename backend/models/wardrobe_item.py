from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base

if TYPE_CHECKING:
    from backend.models.product import Product
    from backend.models.saved_look import SavedLook
    from backend.models.user import User


class WardrobeItem(Base):
    """
    WardrobeItem represents an individual product saved by a user.

    A SavedLook is a whole outfit; a WardrobeItem is one product (e.g. a blue
    shirt or brown shoes). Product details such as price, title and images
    live in the Product table and are not duplicated here. The optional
    saved_from_look_id records which saved look the product came from.
    """

    __tablename__ = "wardrobe_items"

    wardrobe_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Optional: the saved look this product originally came from.
    # If that look is deleted, the wardrobe item stays and this becomes NULL.
    saved_from_look_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_looks.saved_look_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="wardrobe_items")
    product: Mapped["Product"] = relationship(back_populates="wardrobe_items")
    saved_look: Mapped[Optional["SavedLook"]] = relationship(
        back_populates="wardrobe_items"
    )

    def __repr__(self) -> str:
        return (
            f"<WardrobeItem {self.wardrobe_item_id} user_id={self.user_id} "
            f"product_id={self.product_id} category={self.category!r}>"
        )