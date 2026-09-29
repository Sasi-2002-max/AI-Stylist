from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Optional
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base

if TYPE_CHECKING:
    from backend.models.wardrobe_item import WardrobeItem


class Product(Base):
    """
    Global product catalog entry discovered by the shopping/search system.
    Not tied to any user or profile.
    """

    __tablename__ = "products"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    store: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR", server_default="INR"
    )

    # e.g. ["S", "M", "L"] or ["6", "7", "8"]
    sizes: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)

    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)

    availability: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # "metadata" is reserved by SQLAlchemy's declarative Base, so the Python
    # attribute is product_metadata while the DB column is still named "metadata".
    product_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    wardrobe_items: Mapped[list["WardrobeItem"]] = relationship(
        back_populates="product"
    )
    def __repr__(self) -> str:
        return (
            f"<Product {self.product_id} store={self.store!r} "
            f"title={self.title[:30]!r} price={self.price} {self.currency}>"
        )