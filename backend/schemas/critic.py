from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class CriticFeedback(BaseModel):
    """
    Structured feedback from the Critic Agent about a generated outfit.

    The workflow uses this to decide whether the outfit is approved or should
    be revised. It contains only user-facing findings and suggestions.
    """

    approved: bool
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    style_match: str
    budget_match: bool
    color_match: bool
    occasion_match: bool
    overall_feedback: str