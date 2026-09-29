"""
Profile Agent.

Understands a user's profile and natural-language fashion request, and turns
them into a predictable, structured set of styling requirements that later
agents (e.g. a Stylist Agent) can consume.

This module is intentionally standalone:
    - It does not call the LLM, the RAG service, or any product/shopping API.
    - It does not build an avatar, fitting room, or search for products.
    - It only reads plain text with simple rules (regex/keyword matching).

Architecture:

    User Profile
         +
    Natural-language Request
         v
    Profile Agent               <-- this file
         v
    Structured Styling Requirements
         v
    Future Stylist Agent
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.agents.state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Profile handling
# ---------------------------------------------------------------------------

# Fields the agent understands on a profile, and how to validate/convert them.
# Only fields the caller actually provided are kept; nothing is invented.
_PROFILE_FIELD_TYPES: Dict[str, tuple] = {
    "age": (int, float),
    "gender": (str,),
    "body_shape": (str,),
    "skin_tone": (str,),
    "height": (int, float),
    "weight": (int, float),
}


def normalize_profile(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate and clean a user profile without inventing missing information.

    Only the known fields (age, gender, body_shape, skin_tone, height, weight)
    are kept. A field is dropped (with a logged warning) if it is missing,
    empty, or cannot be safely converted to its expected type. Numeric fields
    given as numeric strings (e.g. "24") are converted to numbers.

    Args:
        profile: The raw profile dict, or None.

    Returns:
        A new dict containing only the valid, provided fields.
    """
    if not isinstance(profile, dict):
        if profile is not None:
            logger.warning("Ignoring profile: expected a dict, got %s", type(profile))
        return {}

    normalized: Dict[str, Any] = {}

    for field, expected_types in _PROFILE_FIELD_TYPES.items():
        if field not in profile:
            continue  # not provided: leave it out, do not invent a default

        value = profile[field]
        if value is None or value == "":
            continue

        if isinstance(value, bool):
            # bool is a subclass of int; explicitly reject it for numeric fields
            logger.warning("Ignoring profile field '%s': boolean is not valid", field)
            continue

        if isinstance(value, expected_types):
            normalized[field] = value
            continue

        # Try converting numeric-looking strings (e.g. "24", "165.5")
        if expected_types == (int, float) and isinstance(value, str):
            try:
                number = float(value.strip())
                normalized[field] = int(number) if number.is_integer() else number
                continue
            except ValueError:
                pass

        # String field given as something else: use its string form
        if expected_types == (str,) and not isinstance(value, str):
            normalized[field] = str(value)
            continue

        logger.warning(
            "Ignoring profile field '%s': could not interpret value %r", field, value
        )

    return normalized


# ---------------------------------------------------------------------------
# Budget extraction
# ---------------------------------------------------------------------------

# Matches an amount together with a currency symbol/word and/or a budget
# trigger word (e.g. "under", "budget of") nearby. All parts are optional on
# their own, but at least one currency/trigger signal must be present for a
# match to be accepted -- this avoids mistaking an unrelated number (like a
# year) for a budget.
_BUDGET_PATTERN = re.compile(
    r"""
    (?P<trigger>under|below|within|less\ than|around|about|budget\ of|budget)?
    \s*
    (?P<currency1>[₹$]|rs\.?|inr)?
    \s*
    (?P<amount>\d[\d,]*(?:\.\d+)?)
    \s*
    (?P<currency2>inr|rs\.?|rupees)?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def extract_budget(text: str) -> Tuple[Optional[float], Optional[Tuple[int, int]]]:
    """
    Extract a budget amount from free text, if one is clearly present.

    Understands amounts written as "$5,000", "₹5,000", "5000 INR",
    "Rs. 5000", "under 5000", "budget of 5,000", etc. A bare number with no
    currency symbol/word and no budget-related trigger word (e.g. "under") is
    NOT treated as a budget, since that would be guessing.

    Args:
        text: The user's natural-language request.

    Returns:
        A tuple (amount, span). amount is an int when the value is a whole
        number, a float otherwise, or None if no budget was found. span is
        the (start, end) character range of the match in `text` (useful for
        removing it before extracting the occasion), or None.
    """
    if not text:
        return None, None

    for match in _BUDGET_PATTERN.finditer(text):
        has_signal = any(
            match.group(name) for name in ("trigger", "currency1", "currency2")
        )
        if not has_signal:
            continue  # a bare number with no currency/budget context: skip it

        amount_str = match.group("amount").replace(",", "")
        try:
            amount = float(amount_str)
        except ValueError:
            continue

        value: float = int(amount) if amount.is_integer() else amount
        return value, match.span()

    return None, None


# ---------------------------------------------------------------------------
# Occasion extraction
# ---------------------------------------------------------------------------

def extract_occasion(text: str, budget_span: Optional[Tuple[int, int]]) -> Optional[str]:
    """
    Extract the occasion phrase from the request text.

    The budget portion (if any) is removed first, along with common
    budget-trigger words, and the remainder is treated as the occasion.

    Args:
        text: The user's natural-language request.
        budget_span: The character span returned by extract_budget(), if any.

    Returns:
        A lowercase occasion phrase, or None if nothing meaningful remains.
    """
    if not text:
        return None

    remaining = text
    if budget_span:
        start, end = budget_span
        remaining = text[:start] + " " + text[end:]

    # Remove any leftover trigger words not already covered by the budget span.
    remaining = re.sub(
        r"\b(under|below|within|less than|around|about|budget of|budget)\b",
        " ",
        remaining,
        flags=re.IGNORECASE,
    )

    occasion = remaining.strip(" ,.-\t\n").strip()
    occasion = re.sub(r"\s+", " ", occasion)

    if not occasion:
        return None
    return occasion.lower()


# ---------------------------------------------------------------------------
# Formality
# ---------------------------------------------------------------------------

# Simple, explicit keyword -> formality mapping. Order matters: more specific
# phrases are checked before more general ones.
_FORMALITY_KEYWORDS: List[Tuple[str, str]] = [
    ("business formal", "formal"),
    ("business casual", "business casual"),
    ("smart casual", "smart casual"),
    ("office", "business casual"),
    ("formal", "formal"),
    ("wedding", "semi-formal"),
    ("reception", "formal"),
    ("festival", "festive"),
    ("party", "semi-formal"),
    ("date", "smart casual"),
    ("travel", "casual"),
    ("beach", "casual"),
    ("college", "casual"),
    ("casual", "casual"),
]


def extract_formality(request_text: str, occasion: Optional[str]) -> Optional[str]:
    """
    Extract or safely derive the formality level of the request.

    Formality is read directly from the request text when stated explicitly
    (e.g. "formal office event"), or derived from the occasion using a small,
    explicit keyword table. Returns None when neither source gives a
    confident answer, rather than guessing.

    Args:
        request_text: The user's natural-language request.
        occasion: The occasion extracted by extract_occasion(), if any.

    Returns:
        A formality label (e.g. "semi-formal"), or None.
    """
    haystacks = [h.lower() for h in (request_text, occasion) if h]

    for keyword, formality in _FORMALITY_KEYWORDS:
        for haystack in haystacks:
            if keyword in haystack:
                return formality
    return None


# ---------------------------------------------------------------------------
# Style and fit preferences
# ---------------------------------------------------------------------------

# Only explicit mentions of these terms are captured; nothing is inferred.
_STYLE_KEYWORDS = [
    "minimalist", "minimal", "elegant", "traditional", "ethnic", "western",
    "indo-western", "classic", "modern", "trendy", "chic", "boho",
    "streetwear", "vintage", "formal style", "casual style",
]

_FIT_KEYWORDS = [
    "slim fit", "relaxed fit", "regular fit", "oversized", "loose fit",
    "fitted", "tailored fit", "comfortable fit",
]


def _extract_keywords(text: str, vocabulary: List[str]) -> List[str]:
    """Return, in order, every keyword from `vocabulary` explicitly present in `text`."""
    if not text:
        return []

    lowered = text.lower()
    found: List[str] = []
    for keyword in vocabulary:
        if keyword in lowered and keyword not in found:
            found.append(keyword)
    return found


def extract_style_preferences(text: str) -> List[str]:
    """Return style preferences explicitly mentioned in the request (empty list if none)."""
    return _extract_keywords(text, _STYLE_KEYWORDS)


def extract_fit_preferences(text: str) -> List[str]:
    """Return fit preferences explicitly mentioned in the request (empty list if none)."""
    return _extract_keywords(text, _FIT_KEYWORDS)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_requirements(request_text: str) -> Dict[str, Any]:
    """
    Convert a natural-language fashion request into structured requirements.

    Args:
        request_text: The user's request, e.g. "Indoor wedding under ₹5,000".

    Returns:
        A JSON-serializable dict with keys: occasion, formality, budget,
        style_preferences, fit_preferences.
    """
    request_text = (request_text or "").strip()

    budget, budget_span = extract_budget(request_text)
    occasion = extract_occasion(request_text, budget_span)
    formality = extract_formality(request_text, occasion)
    style_preferences = extract_style_preferences(request_text)
    fit_preferences = extract_fit_preferences(request_text)

    return {
        "occasion": occasion,
        "formality": formality,
        "budget": budget,
        "style_preferences": style_preferences,
        "fit_preferences": fit_preferences,
    }


def run_profile_agent(
    profile: Optional[Dict[str, Any]], request_text: str
) -> Dict[str, Any]:
    """
    Run the Profile Agent: combine a user profile and a request into
    structured output for later agents.

    Args:
        profile: The user's profile dict (e.g. age, gender, body_shape,
            skin_tone, height, weight). Missing or invalid fields are dropped
            gracefully; nothing is invented.
        request_text: The user's natural-language fashion request.

    Returns:
        A JSON-serializable dict:
            {
                "profile": {...},        # cleaned, only the fields provided
                "requirements": {...},   # structured styling requirements
            }
    """
    return {
        "profile": normalize_profile(profile),
        "requirements": build_requirements(request_text),
    }


# ---------------------------------------------------------------------------
# Shared-state entry point (for the multi-agent workflow)
# ---------------------------------------------------------------------------

def profile_agent(state: AgentState) -> AgentState:
    """
    Workflow-facing wrapper that runs the Profile Agent on the shared AgentState.

    Reads state["user_profile"] and state["user_query"], runs the same logic
    as run_profile_agent(), and writes the result into state["style_context"]:

        {
            "profile": {...},
            "requirements": {
                "occasion": "...",
                "formality": "...",
                "budget": ...,
                "style_preferences": [],
                "fit_preferences": [],
            },
        }

    No other part of AgentState is read or modified.

    Args:
        state: The shared workflow state (see backend.agents.state.AgentState).

    Returns:
        The same state dict, with state["style_context"] populated.
    """
    user_profile = state.get("user_profile")
    user_query = state.get("user_query", "")

    state["style_context"] = run_profile_agent(user_profile, user_query)
    return state


if __name__ == "__main__":
    import json

    sample_state: AgentState = {
        "user_profile": {
            "age": 24,
            "gender": "Female",
            "body_shape": "rectangle",
            "skin_tone": "warm",
            "height": 165,
            "weight": 55,
        },
        "user_query": "Indoor wedding under ₹5,000",
        "style_context": {},
        "rag_context": [],
        "outfit_plan": {},
        "product_candidates": [],
        "selected_products": [],
        "fitting_room": {},
        "critic_feedback": {},
        "iteration": 0,
        "status": "running",
    }

    print("Input state:")
    print(f"  user_profile: {sample_state['user_profile']}")
    print(f"  user_query:   \"{sample_state['user_query']}\"\n")

    updated_state = profile_agent(sample_state)

    print("state[\"style_context\"]:")
    print(json.dumps(updated_state["style_context"], indent=4, ensure_ascii=False))