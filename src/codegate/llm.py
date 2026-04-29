"""LLM helper — unified interface for calling language models via LiteLLM."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

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

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            return content, tokens
        except Exception as e:
            err_str = str(e).lower()
            # Retry on transient server errors, not on auth/validation errors
            is_transient = any(
                k in err_str
                for k in [
                    "server disconnected", "eof occurred", "internal server error",
                    "connection reset", "timeout", "502", "503", "429",
                ]
            )
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


def _try_parse_json(text: str) -> dict | list | None:
    """Attempt to parse text as JSON, with repair strategies.

    Returns parsed JSON or None if all strategies fail.
    """
    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract the earliest top-level JSON-looking block.
    # If an array appears before an object, prefer the array; otherwise a
    # wrapped list like `Result: [{"a": 1}] done` is incorrectly reduced to
    # its first inner object.
    obj_start = text.find("{")
    arr_start = text.find("[")
    candidates = [
        (obj_start, "{", "}"),
        (arr_start, "[", "]"),
    ]
    candidates = [c for c in candidates if c[0] >= 0]
    candidates.sort(key=lambda c: c[0])

    for start, _open_char, close_char in candidates:
        end = text.rfind(close_char) + 1
        if end <= start:
            continue
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            continue

    return None


def _save_malformed_response(raw: str, context: str = "") -> Path | None:
    """Save a malformed LLM response to an artifact file for debugging.

    Returns the path where the artifact was saved, or None on failure.
    """
    try:
        from codegate.config import get_config
        store_dir = Path(get_config().store_dir)
    except Exception:
        store_dir = Path("./artifacts")

    error_dir = store_dir / "llm_parse_errors"
    error_dir.mkdir(parents=True, exist_ok=True)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    error_file = error_dir / f"malformed_{timestamp}.json"

    try:
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "context": context,
            "raw_response_length": len(raw),
            "raw_response": raw[:10000],  # cap at 10KB
        }
        error_file.write_text(
            json.dumps(error_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return error_file
    except Exception as e:
        logger.debug(f"Could not save malformed response artifact: {e}")
        return None


def call_llm_json(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.2,
) -> tuple[dict | list, int]:
    """Call LLM and parse the response as JSON.

    Handles common issues like markdown code fences around JSON.
    On parse failure, automatically retries the LLM call once and
    saves the malformed raw response as an artifact for debugging.

    Returns:
        Tuple of (parsed_json, total_tokens_used)
    """
    total_tokens = 0

    for attempt in range(2):  # at most 1 retry
        raw, tokens = call_llm(
            model=model,
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        total_tokens += tokens

        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [line for line in lines[1:] if line.strip() != "```"]
            text = "\n".join(lines)

        parsed = _try_parse_json(text)
        if parsed is not None:
            return parsed, total_tokens

        # Parse failed
        if attempt == 0:
            # Save the malformed response and retry
            artifact_path = _save_malformed_response(
                raw, context=f"model={model}, attempt=1"
            )
            logger.warning(
                f"JSON parse failed (attempt 1), retrying. "
                f"Raw saved to: {artifact_path}. "
                f"Preview: {text[:200]}..."
            )
            time.sleep(1)  # brief pause before retry
        else:
            # Second attempt also failed — save and raise
            artifact_path = _save_malformed_response(
                raw, context=f"model={model}, attempt=2_final"
            )
            logger.error(
                f"JSON parse failed after retry. "
                f"Raw saved to: {artifact_path}. "
                f"Preview: {text[:200]}..."
            )
            raise ValueError(
                f"Could not parse JSON from LLM response after retry. "
                f"Raw response saved to: {artifact_path}"
            )

    # Should not reach here, but satisfy type checker
    raise ValueError("Unexpected: call_llm_json loop exited without return")
