"""
Tests for the Stylist Agent's tool-calling behavior (Part 25).

The LLM and, where noted, the RAG retriever are mocked so these tests run
without a real Groq API key or a populated ChromaDB collection.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.agents.stylist_agent import (
    StylistAgentError,
    create_outfit_plan,
)
from backend.rag.tools import retrieve_fashion_knowledge
from backend.schemas.outfit import OutfitPlan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_tool_call(call_id: str, name: str, arguments: dict) -> SimpleNamespace:
    """Build an object shaped like Groq/OpenAI's tool_call entries."""
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def _fake_message(content: str | None = None, tool_calls=None) -> SimpleNamespace:
    """Build an object shaped like Groq/OpenAI's response message."""
    return SimpleNamespace(content=content, tool_calls=tool_calls)


SAMPLE_STYLE_CONTEXT = {
    "profile": {
        "age": 24,
        "gender": "Female",
        "body_shape": "rectangle",
        "skin_tone": "warm",
        "height": 165,
        "weight": 55,
    },
    "requirements": {
        "occasion": "indoor wedding",
        "formality": "semi-formal",
        "budget": 5000,
        "style_preferences": [],
        "fit_preferences": [],
    },
}

WEDDING_OUTFIT_JSON = json.dumps(
    {
        "occasion": "indoor wedding",
        "style": "elegant",
        "color_palette": ["black", "cream", "brown"],
        "items": [
            {"category": "shirt", "item": "black oxford shirt", "color": "black"},
            {"category": "pants", "item": "cream trousers", "color": "cream"},
            {"category": "shoes", "item": "brown loafers", "color": "brown"},
        ],
        "accessories": [],
        "budget": 5000,
        "currency": "INR",
        "reasoning": "A polished, semi-formal look suited to an indoor wedding.",
    }
)

COLLEGE_STYLE_CONTEXT = {
    "profile": {
        "age": 20,
        "gender": "Male",
        "body_shape": "athletic",
        "skin_tone": "cool",
        "height": 178,
        "weight": 70,
    },
    "requirements": {
        "occasion": "casual college outfit",
        "formality": "casual",
        "budget": 2500,
        "style_preferences": [],
        "fit_preferences": [],
    },
}

COLLEGE_OUTFIT_JSON = json.dumps(
    {
        "occasion": "casual college outfit",
        "style": "streetwear",
        "color_palette": ["navy", "white"],
        "items": [
            {"category": "shirt", "item": "navy t-shirt", "color": "navy"},
            {"category": "pants", "item": "white joggers", "color": "white"},
            {"category": "shoes", "item": "white sneakers", "color": "white"},
        ],
        "accessories": [],
        "budget": 2500,
        "currency": "INR",
        "reasoning": "A relaxed, budget-friendly casual college look.",
    }
)


# ---------------------------------------------------------------------------
# Test 1 -- Basic outfit generation
# ---------------------------------------------------------------------------

def test_basic_outfit_generation():
    """create_outfit_plan() returns a valid OutfitPlan for a normal request."""
    with patch(
        "backend.agents.stylist_agent.generate_with_tools",
        return_value=_fake_message(content=WEDDING_OUTFIT_JSON, tool_calls=None),
    ):
        result = create_outfit_plan(
            style_context=SAMPLE_STYLE_CONTEXT,
            user_query="Indoor wedding under ₹5,000",
        )

    assert isinstance(result, OutfitPlan)
    assert result.occasion == "indoor wedding"


# ---------------------------------------------------------------------------
# Test 2 -- Tool is callable
# ---------------------------------------------------------------------------

def test_retrieve_fashion_knowledge_is_callable():
    """retrieve_fashion_knowledge() can be called without a real ChromaDB."""
    fake_chunks = [
        {"text": "Warm skin tones pair well with earthy colors.", "source": "skin_tone_colors.md"},
        {"text": "Semi-formal weddings favor tailored, comfortable pieces.", "source": "occasion_styling.md"},
    ]

    with patch(
        "backend.rag.tools.retrieve_relevant_chunks",
        return_value=fake_chunks,
    ):
        results = retrieve_fashion_knowledge("warm skin tone wedding styling", top_k=2)

    assert results == [
        "[Source 1]\nWarm skin tones pair well with earthy colors.",
        "[Source 2]\nSemi-formal weddings favor tailored, comfortable pieces.",
    ]


# ---------------------------------------------------------------------------
# Test 3 -- Tool calling path
# ---------------------------------------------------------------------------

def test_tool_calling_path_executes_tool_and_returns_outfit_plan():
    """
    When the LLM requests retrieve_fashion_knowledge, the tool runs, its
    result is sent back to the LLM, and the final response becomes an
    OutfitPlan.
    """
    tool_call = _fake_tool_call(
        call_id="call_1",
        name="retrieve_fashion_knowledge",
        arguments={"query": "semi-formal indoor wedding styling", "top_k": 3},
    )
    first_response = _fake_message(content=None, tool_calls=[tool_call])
    second_response = _fake_message(content=WEDDING_OUTFIT_JSON, tool_calls=None)

    with (
        patch(
            "backend.agents.stylist_agent.generate_with_tools",
            side_effect=[first_response, second_response],
        ) as mock_generate,
        patch(
            "backend.agents.stylist_agent.retrieve_fashion_knowledge",
            return_value=["[Source 1]\nSemi-formal weddings favor tailored pieces."],
        ) as mock_retrieve,
    ):
        result = create_outfit_plan(
            style_context=SAMPLE_STYLE_CONTEXT,
            user_query="Indoor wedding under ₹5,000",
        )

    assert mock_generate.call_count == 2
    mock_retrieve.assert_called_once_with(
        query="semi-formal indoor wedding styling", top_k=3
    )
    assert isinstance(result, OutfitPlan)
    assert result.occasion == "indoor wedding"


# ---------------------------------------------------------------------------
# Test 4 -- No tool call
# ---------------------------------------------------------------------------

def test_no_tool_call_still_produces_outfit_plan():
    """The system finishes correctly when the LLM never calls the tool."""
    with (
        patch(
            "backend.agents.stylist_agent.generate_with_tools",
            return_value=_fake_message(content=WEDDING_OUTFIT_JSON, tool_calls=None),
        ) as mock_generate,
        patch(
            "backend.agents.stylist_agent.retrieve_fashion_knowledge"
        ) as mock_retrieve,
    ):
        result = create_outfit_plan(
            style_context=SAMPLE_STYLE_CONTEXT,
            user_query="Indoor wedding under ₹5,000",
        )

    mock_generate.assert_called_once()
    mock_retrieve.assert_not_called()
    assert isinstance(result, OutfitPlan)


# ---------------------------------------------------------------------------
# Test 5 -- Different user query
# ---------------------------------------------------------------------------

def test_different_user_query_is_not_hardcoded():
    """A different occasion/query produces a matching, different OutfitPlan."""
    with patch(
        "backend.agents.stylist_agent.generate_with_tools",
        return_value=_fake_message(content=COLLEGE_OUTFIT_JSON, tool_calls=None),
    ):
        result = create_outfit_plan(
            style_context=COLLEGE_STYLE_CONTEXT,
            user_query="I need a casual college outfit under ₹2500.",
        )

    assert isinstance(result, OutfitPlan)
    assert result.occasion == "casual college outfit"
    assert result.budget == 2500


# ---------------------------------------------------------------------------
# Extra -- tool-call loop limit
# ---------------------------------------------------------------------------

def test_tool_loop_raises_after_max_tool_calls():
    """An LLM that keeps requesting tools forever is stopped, not looped forever."""
    tool_call = _fake_tool_call(
        call_id="call_x",
        name="retrieve_fashion_knowledge",
        arguments={"query": "anything"},
    )
    always_wants_tool = _fake_message(content=None, tool_calls=[tool_call])

    with (
        patch(
            "backend.agents.stylist_agent.generate_with_tools",
            return_value=always_wants_tool,
        ),
        patch(
            "backend.agents.stylist_agent.retrieve_fashion_knowledge",
            return_value=["[Source 1]\nSome fact."],
        ),
    ):
        with pytest.raises(StylistAgentError):
            create_outfit_plan(
                style_context=SAMPLE_STYLE_CONTEXT,
                user_query="Indoor wedding under ₹5,000",
            )