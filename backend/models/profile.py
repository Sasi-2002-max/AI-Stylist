from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base

if TYPE_CHECKING:
    from backend.models.user import User


class Profile(Base):
    """
    Basic user information used by the AI Stylist agents.

    Stores standardized values only:
      - height in centimeters (height_cm)
      - weight in kilograms (weight_kg)
    Unit conversion (ft/in, lb) is handled by the API layer before saving.

    No face, avatar, body mesh or biometric data is stored here.
    """

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # One profile per user (unique FK)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)

    gender: Mapped[str] = mapped_column(String(20), nullable=False)        # female | male
    body_shape: Mapped[str] = mapped_column(String(30), nullable=False)    # hourglass | pear | apple | rectangle | inverted_triangle
    skin_tone: Mapped[str] = mapped_column(String(30), nullable=False)     # very_light | light | medium | tan | brown | deep

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="profile")

    def __repr__(self) -> str:
        return f"<Profile {self.name} user_id={self.user_id}>"