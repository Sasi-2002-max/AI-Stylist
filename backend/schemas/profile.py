from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ProfileSchema(BaseModel):
    """
    Fashion-relevant profile information about a user.

    Used by the API layer and by the AI agents. It holds only basic body and
    style information, with no face, avatar or biometric data.
    """

    age: Optional[int] = Field(default=None, ge=1, le=120)
    gender: Optional[str] = None
    body_shape: Optional[str] = None
    skin_tone: Optional[str] = None
    height_cm: Optional[float] = Field(default=None, gt=0)
    weight_kg: Optional[float] = Field(default=None, gt=0)