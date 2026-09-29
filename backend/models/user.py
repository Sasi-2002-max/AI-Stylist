from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from backend.models.saved_look import SavedLook
from backend.models.outfit import Outfit

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base

if TYPE_CHECKING:
    from backend.models.outfit import Outfit
    from backend.models.profile import Profile
    from backend.models.saved_look import SavedLook
    from backend.models.wardrobe_item import WardrobeItem
    from backend.models.conversation import Conversation


class User(Base):
    """
    Account / identity of the person using the app.
    Fashion and body information lives in Profile, not here.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    # Hashed only (bcrypt/argon2 later). Nullable so auth can be added later
    # without blocking user creation. Never store a plain-text password.
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # One User -> one Profile
    profile: Mapped[Optional["Profile"]] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    saved_looks: Mapped[list["SavedLook"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    wardrobe_items: Mapped[list["WardrobeItem"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    outfits: Mapped[list["Outfit"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    conversations: Mapped[list["Conversation"]] = relationship(
       back_populates="user",
       cascade="all, delete-orphan",
    )
    

    def __repr__(self) -> str:
        return f"<User {self.email}>"