"""
Stylist Agent.

Turns a Profile Agent's style_context, the user's original query, and
fashion knowledge into a structured OutfitPlan.

Architecture (Part 25 -- function calling):

    User Profile
         +
    User Query
         v
    Profile Agent
         v
    style_context
         v
    Stylist Agent             <-- this file
         v
    LLM (Groq)
         v
    [LLM decides knowledge is needed]
         v
    retrieve_fashion_knowledge()  tool call
         v
    backend.rag.retriever -> ChromaDB
         v
    tool results returned to the LLM
         v
    OutfitPlan

This module only decides WHAT the outfit should contain. It never searches
for real products, never calls the Shopping Agent or MCP, never creates an
avatar or fitting-room image, and never touches the database. All LLM calls
go through the single centralized helpers in backend.utils.llm.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from backend.agents.state import AgentState
from backend.rag.tools import RETRIEVE_FASHION_KNOWLEDGE_TOOL, retrieve_fashion_knowledge
from backend.schemas.outfit import OutfitItem, OutfitPlan
from backend.utils.llm import generate_text, generate_with_tools

logger = logging.getLogger(__name__)

# Maximum number of LLM round-trips in the tool-calling loop, so a model
# that keeps requesting tools can never hang the application forever.
MAX_TOOL_CALLS = 5


class StylistAgentError(Exception):
    """Raised when the Stylist Agent cannot produce a valid OutfitPlan."""


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert fashion stylist creating one complete outfit recommendation.

You will be given:
- USER PROFILE: known attributes about the user's body and appearance.
- USER REQUIREMENTS: structured requirements already extracted from the user's
  request (occasion, formality, budget, and any explicitly stated style/fit
  preferences).
- USER QUERY: the user's original natural-language request.

When building the outfit:
- Match the stated occasion and formality level.
- Use body shape, skin tone, height and weight only as general styling input
  (visual balance and color coordination), never as a judgment.
- Only include style or fit preferences the user explicitly stated. Do not
  invent preferences they did not mention.
- Keep the total outfit within the stated budget when one is given.
- Make sure the colors coordinate and the items form one coherent, complete
  outfit (for example a top, a bottom or dress, and footwear).
- Accessories are optional; include zero or more that suit the occasion.
- Write a short, user-facing "reasoning" that explains the choices in plain
  language. It must be a brief summary for the user, not internal reasoning.

Respond with a single JSON object only, using exactly these fields, and
nothing else (no markdown fences, no commentary before or after it):

{schema}
"""

TOOL_GUIDANCE = """
You have access to a fashion knowledge retrieval tool named retrieve_fashion_knowledge.

Use the retrieval tool when additional fashion knowledge would improve the
recommendation. You may retrieve knowledge about:
- color coordination
- skin tone
- body shape
- occasion
- formality
- fit
- silhouettes
- styling principles

Do not use the tool for information that is already clearly provided by the
user. Do not retrieve products. Do not search shopping websites. Do not call
MCP.

Use retrieved fashion knowledge as supporting information. After gathering
the information you need, produce the final structured OutfitPlan as
described above.
"""


def _format_profile(profile: Dict[str, Any]) -> str:
    """Render the user profile as simple "Label: value" lines."""
    if not profile:
        return "No profile details were provided."
    lines = [f"{key.replace('_', ' ').title()}: {value}" for key, value in profile.items()]
    return "\n".join(lines)


def _format_requirements(requirements: Dict[str, Any]) -> str:
    """Render the Profile Agent's structured requirements as readable text."""
    occasion = requirements.get("occasion") or "Not specified"
    formality = requirements.get("formality") or "Not specified"

    budget = requirements.get("budget")
    budget_line = f"₹{budget}" if budget is not None else "Not specified"

    style_preferences = requirements.get("style_preferences") or []
    fit_preferences = requirements.get("fit_preferences") or []

    return "\n".join(
        [
            f"Occasion: {occasion}",
            f"Formality: {formality}",
            f"Budget: {budget_line}",
            "Style preferences: "
            + (", ".join(style_preferences) if style_preferences else "None stated"),
            "Fit preferences: "
            + (", ".join(fit_preferences) if fit_preferences else "None stated"),
        ]
    )


def _format_rag_context(rag_context: Optional[List[str]]) -> str:
    """
    Render manually supplied RAG passages as a numbered "FASHION KNOWLEDGE"
    block. Used only by the legacy manual-rag_context path.
    """
    if not rag_context:
        return "No additional fashion knowledge context was provided."

    lines = ["FASHION KNOWLEDGE:", ""]
    for index, passage in enumerate(rag_context, start=1):
        lines.append(f"[Document {index}]")
        lines.append(str(passage).strip())
        lines.append("")
    return "\n".join(lines).strip()


def _build_user_prompt(
    profile: Dict[str, Any],
    requirements: Dict[str, Any],
    user_query: str,
    rag_context: Optional[List[str]],
) -> str:
    """Legacy prompt: USER PROFILE / USER REQUIREMENTS / USER QUERY / manual RAG."""
    return (
        f"USER PROFILE:\n{_format_profile(profile)}\n\n"
        f"USER REQUIREMENTS:\n{_format_requirements(requirements)}\n\n"
        f'USER QUERY:\n"{user_query.strip()}"\n\n'
        f"FASHION RAG CONTEXT:\n{_format_rag_context(rag_context)}\n"
    )


def _build_user_prompt_for_tools(
    profile: Dict[str, Any],
    requirements: Dict[str, Any],
    user_query: str,
) -> str:
    """
    Tool-calling prompt: USER PROFILE / USER REQUIREMENTS / USER QUERY only.
    No RAG section here -- the LLM fetches fashion knowledge itself via the
    retrieve_fashion_knowledge tool, if and when it decides it needs to.
    """
    return (
        f"USER PROFILE:\n{_format_profile(profile)}\n\n"
        f"USER REQUIREMENTS:\n{_format_requirements(requirements)}\n\n"
        f'USER QUERY:\n"{user_query.strip()}"\n'
    )


def _build_system_prompt(include_tool_guidance: bool = False) -> str:
    """Fill the OutfitPlan JSON schema into the system prompt template."""
    schema = json.dumps(OutfitPlan.model_json_schema(), indent=2)
    prompt = SYSTEM_PROMPT.format(schema=schema)
    if include_tool_guidance:
        prompt = f"{prompt}\n{TOOL_GUIDANCE}"
    return prompt


# ---------------------------------------------------------------------------
# style_context validation
# ---------------------------------------------------------------------------

def _extract_profile_and_requirements(
    style_context: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Pull the profile and requirements out of the Profile Agent's style_context.

    Raises:
        StylistAgentError: if style_context is missing or has no requirements,
            since an outfit cannot be planned without at least that much.
    """
    if not isinstance(style_context, dict):
        raise StylistAgentError(
            "style_context is missing or invalid. Run the Profile Agent first "
            "and pass its output as style_context."
        )

    requirements = style_context.get("requirements")
    if not isinstance(requirements, dict):
        raise StylistAgentError(
            "style_context is missing 'requirements'. Run the Profile Agent "
            "first and pass its output as style_context."
        )

    profile = style_context.get("profile")
    if not isinstance(profile, dict):
        logger.warning("style_context has no usable 'profile'; continuing without it.")
        profile = {}

    return profile, requirements


# ---------------------------------------------------------------------------
# Legacy single-call LLM path (used only when rag_context is supplied)
# ---------------------------------------------------------------------------

def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Send the combined prompt to the centralized plain-text LLM helper.

    generate_text() only accepts one prompt string, so the system and user
    sections are combined here. Used only by the legacy manual-rag_context
    path; the tool-calling path below uses generate_with_tools() instead.
    """
    combined_prompt = f"{system_prompt}\n\n{user_prompt}"
    try:
        return generate_text(combined_prompt)
    except Exception as exc:
        raise StylistAgentError(f"Stylist Agent could not reach the LLM: {exc}") from exc


# ---------------------------------------------------------------------------
# Tool-calling loop (Part 25)
# ---------------------------------------------------------------------------

def _execute_tool_call(tool_call: Any) -> str:
    """
    Run a single tool call requested by the LLM and return its result as
    plain text, suitable for a "tool" role message.
    """
    function_name = getattr(tool_call.function, "name", "")
    raw_arguments = getattr(tool_call.function, "arguments", "") or "{}"

    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        logger.warning("Could not parse tool arguments for %s: %r", function_name, raw_arguments)
        arguments = {}

    if function_name != "retrieve_fashion_knowledge":
        logger.warning("LLM requested an unknown tool: %s", function_name)
        return f"Unknown tool '{function_name}'."

    query = arguments.get("query", "")
    top_k = arguments.get("top_k", 5)

    logger.info(
        "LLM requested tool:\nretrieve_fashion_knowledge\nquery: %s", query
    )

    results = retrieve_fashion_knowledge(query=query, top_k=top_k)
    logger.info("Tool returned %d result(s)", len(results))

    return "\n\n".join(results) if results else "No relevant fashion knowledge found."


def _run_tool_calling_loop(system_prompt: str, user_prompt: str) -> str:
    """
    Run the LLM tool-calling loop for the Stylist Agent.

    Flow:
        LLM -> tool call requested? -> yes -> execute retrieve_fashion_knowledge()
             -> send tool result back to LLM -> repeat
             -> no -> return the LLM's final text (the OutfitPlan JSON)

    Raises:
        StylistAgentError: if the LLM cannot be reached, or the loop exceeds
            MAX_TOOL_CALLS iterations without producing a final answer.
    """
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tools = [RETRIEVE_FASHION_KNOWLEDGE_TOOL]

    for _ in range(MAX_TOOL_CALLS):
        try:
            message = generate_with_tools(messages, tools=tools)
        except Exception as exc:
            raise StylistAgentError(f"Stylist Agent could not reach the LLM: {exc}") from exc

        tool_calls = getattr(message, "tool_calls", None)

        if not tool_calls:
            logger.info("LLM did not request fashion knowledge.")
            return message.content or ""

        # Append the assistant's tool-call message verbatim before adding
        # the tool results -- required by Groq/OpenAI-style tool calling.
        messages.append(message)

        for tool_call in tool_calls:
            tool_content = _execute_tool_call(tool_call)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": getattr(tool_call.function, "name", ""),
                    "content": tool_content,
                }
            )

        logger.info("Sending tool results back to LLM")

    raise StylistAgentError(
        f"Stylist Agent exceeded the maximum of {MAX_TOOL_CALLS} tool-calling iterations."
    )


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _extract_json_block(raw_text: str) -> str:
    """Pull the JSON object out of the LLM's raw text, tolerating markdown code fences."""
    text = raw_text.strip()

    fenced = _JSON_FENCE_PATTERN.search(text)
    if fenced:
        return fenced.group(1)

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def _parse_outfit_plan(raw_text: str) -> OutfitPlan:
    """
    Parse the LLM's raw text into an OutfitPlan.

    Raises:
        StylistAgentError: if the text is not valid JSON, or the JSON does
            not match the OutfitPlan schema.
    """
    json_block = _extract_json_block(raw_text)

    try:
        data = json.loads(json_block)
    except json.JSONDecodeError as exc:
        raise StylistAgentError(
            f"The stylist LLM did not return valid JSON: {exc}"
        ) from exc

    try:
        return OutfitPlan.model_validate(data)
    except ValidationError as exc:
        raise StylistAgentError(
            f"The stylist LLM's output did not match the OutfitPlan schema: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_outfit_plan(
    style_context: Dict[str, Any],
    user_query: str,
    rag_context: Optional[List[str]] = None,
) -> OutfitPlan:
    """
    Produce a structured OutfitPlan from the Profile Agent's output.

    Two paths:
    - rag_context is None (the normal, production path): the LLM decides for
      itself, via the retrieve_fashion_knowledge tool, whether it needs
      fashion knowledge, and requests it directly from ChromaDB.
    - rag_context is provided explicitly (legacy path, kept for backward
      compatibility): that context is inserted into the prompt manually and
      no tool calling happens.

    Args:
        style_context: The Profile Agent's output:
            {"profile": {...}, "requirements": {...}}.
        user_query: The user's original natural-language request.
        rag_context: Optional list of fashion-knowledge passages. Passing
            this skips tool calling (legacy behavior). Leave as None to use
            the tool-calling path.

    Returns:
        A validated OutfitPlan.

    Raises:
        StylistAgentError: if style_context is invalid, the LLM cannot be
            reached, the tool-calling loop exceeds MAX_TOOL_CALLS, or the
            final output does not match the OutfitPlan schema.
    """
    profile, requirements = _extract_profile_and_requirements(style_context)
    user_query = user_query or ""

    if rag_context is not None:
        logger.info("rag_context supplied manually; using legacy single-call path.")
        system_prompt = _build_system_prompt(include_tool_guidance=False)
        user_prompt = _build_user_prompt(profile, requirements, user_query, rag_context)
        raw_output = _call_llm(system_prompt, user_prompt)
    else:
        system_prompt = _build_system_prompt(include_tool_guidance=True)
        user_prompt = _build_user_prompt_for_tools(profile, requirements, user_query)
        raw_output = _run_tool_calling_loop(system_prompt, user_prompt)

    return _parse_outfit_plan(raw_output)


def stylist_agent(state: AgentState) -> AgentState:
    """
    Workflow-facing wrapper that runs the Stylist Agent on the shared AgentState.

    Reads state["style_context"] and state["user_query"]. If
    state["rag_context"] already holds something, that is used as the
    legacy manual path; otherwise the tool-calling path runs and the LLM
    fetches fashion knowledge itself. Writes the resulting outfit plan (as a
    plain dict) into state["outfit_plan"]. No other part of AgentState is
    read or modified.

    Args:
        state: The shared workflow state (see backend.agents.state.AgentState).

    Returns:
        The same state dict, with state["outfit_plan"] populated.
    """
    style_context = state.get("style_context") or {}
    user_query = state.get("user_query", "")
    rag_context = state.get("rag_context") or None

    plan = create_outfit_plan(style_context, user_query, rag_context)
    state["outfit_plan"] = plan.model_dump()
    return state


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sample_style_context = {
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
    sample_user_query = "Indoor wedding under ₹5,000"

    print("Stylist Agent started\n")
    try:
        # No rag_context passed: the LLM decides for itself whether it
        # needs fashion knowledge, via the retrieve_fashion_knowledge tool.
        result = create_outfit_plan(
            style_context=sample_style_context,
            user_query=sample_user_query,
        )
        print("\nFinal OutfitPlan:")
        print(result.model_dump_json(indent=4))
    except StylistAgentError as error:
        print(f"Stylist Agent failed: {error}")