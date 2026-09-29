"""
Central LLM communication layer for the AI Fashion Stylist.

All communication with the LLM happens through this file.

Agents should NOT create their own Groq clients.
They should call generate_text() or generate_with_tools() instead:

    Agent
       |
       v
generate_text() / generate_with_tools()
       |
       v
    Groq API
       |
       v
llama-3.3-70b-versatile
"""

import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from groq import Groq


# Load variables from .env
load_dotenv()


# Configuration
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile",
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# Make sure the API key exists
if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is not set in the .env file"
    )


# Create the Groq client
client = Groq(
    api_key=GROQ_API_KEY
)


def generate_text(prompt: str) -> str:
    """
    Send a prompt to the Groq LLM and return the generated text.

    Args:
        prompt: The text prompt sent to the model.

    Returns:
        The model's generated response as a string.
    """

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    return response.choices[0].message.content or ""


def generate_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    tool_choice: str = "auto",
):
    """
    Send a conversation to the Groq LLM together with tool/function
    definitions, letting the model decide whether to call a tool.

    Groq's chat-completions API mirrors OpenAI's tool-calling conventions:
    the returned message object has `.content` (set when the model answered
    directly) and `.tool_calls` (set when the model wants to call one or
    more tools, each with `.id`, `.function.name`, `.function.arguments`).

    The caller is expected to append this raw message object onto `messages`
    before sending tool results back for a follow-up call -- this is the
    standard Groq/OpenAI tool-calling pattern.

    Args:
        messages: Full conversation so far, e.g.
            [{"role": "system", "content": ...}, {"role": "user", "content": ...}].
        tools: Tool/function definitions in Groq/OpenAI "tools" format.
        tool_choice: Passed through to the API. "auto" (default) lets the
            model decide whether a tool call is needed.

    Returns:
        The raw assistant message object from the Groq API.
    """
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
    )
    return response.choices[0].message