"""LLM helper — unified interface for calling language models via LiteLLM."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import time

import litellm

logger = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 5, 10]  # seconds


def load_prompt(prompt_name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = Path(__file__).parent / "prompts" / f"{prompt_name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def call_llm(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    response_format: dict | None = None,
) -> tuple[str, int]:
    """Call an LLM via LiteLLM with retry logic.

    Retries up to MAX_RETRIES times with exponential backoff
    for transient server errors (SSL disconnects, 500s, etc.).
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        kwargs["response_format"] = response_format

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            return content, tokens
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            # Retry on transient server errors, not on auth/validation errors
            is_transient = any(k in err_str for k in [
                "server disconnected", "eof occurred", "internal server error",
                "connection reset", "timeout", "502", "503", "429",
            ])
            if is_transient and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[attempt]
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{MAX_RETRIES + 1}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
            else:
                logger.error(f"LLM call failed: {e}")
                raise


def call_llm_json(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.2,
) -> tuple[dict | list, int]:
    """Call LLM and parse the response as JSON.

    Handles common issues like markdown code fences around JSON.

    Returns:
        Tuple of (parsed_json, total_tokens_used)
    """
    raw, tokens = call_llm(
        model=model,
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=temperature,
        response_format={"type": "json_object"},
    )

    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(lines)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON, attempting repair. Raw: {text[:200]}...")
        # Try to extract JSON from the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
        else:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(text[start:end])
            else:
                raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}")

    return parsed, tokens
