from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class OutfitItem(BaseModel):
    """A single clothing item or accessory recommended as part of an outfit."""

    category: str
    item: str
    color: Optional[str] = None
    style: Optional[str] = None
    notes: Optional[str] = None


class OutfitPlan(BaseModel):
    """
    Structured outfit recommendation returned by the stylist agent.

    The reasoning field holds only a short, user-facing explanation of the
    recommendation.
    """

    occasion: str
    style: str
    color_palette: List[str] = Field(default_factory=list)
    items: List[OutfitItem] = Field(default_factory=list)
    accessories: List[OutfitItem] = Field(default_factory=list)
    budget: Optional[float] = Field(default=None, ge=0)
    currency: str = "INR"
    reasoning: Optional[str] = None