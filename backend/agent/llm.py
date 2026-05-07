"""Anthropic SDK wrapper for the FieldPulse agent.

Centralizes:
  - Client construction with API key from settings
  - Per-call token + cost tracking (CallStats accumulator)
  - Prompt caching helpers (system prompt prefix gets cache_control)
  - Standard retry + error handling
  - JSON-only response parsing for the structured steps (mood, editor)

Pricing (per million tokens, Anthropic published as of model GA):
  Sonnet 4.6: input $3 / output $15 / cache write $3.75 / cache read $0.30
  Haiku 4.5:  input $1 / output $5  / cache write $1.25 / cache read $0.10

Model IDs come from backend.config (AGENT_MODEL_PRIMARY / AGENT_MODEL_CRITIC)
so they can be bumped via .env without touching code.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anthropic import Anthropic, APIError, APIStatusError, RateLimitError

from backend.config import get_settings

logger = logging.getLogger(__name__)


# Pricing in USD per token (divide-by-million already applied).
_PRICES: dict[str, dict[str, float]] = {
    "sonnet": {
        "input": 3.0 / 1_000_000,
        "output": 15.0 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
        "cache_read": 0.30 / 1_000_000,
    },
    "haiku": {
        "input": 1.0 / 1_000_000,
        "output": 5.0 / 1_000_000,
        "cache_write": 1.25 / 1_000_000,
        "cache_read": 0.10 / 1_000_000,
    },
}


def _model_family(model_id: str) -> str:
    if "haiku" in model_id.lower():
        return "haiku"
    return "sonnet"


@dataclass
class CallStats:
    """Per-call usage and cost. Accumulator pattern — one CallStats per run."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    n_calls: int = 0
    n_tool_calls: int = 0

    def add(self, model_id: str, usage: Any) -> None:
        """Add a single API call's usage to the running total."""
        family = _model_family(model_id)
        prices = _PRICES[family]
        in_tok = getattr(usage, "input_tokens", 0) or 0
        out_tok = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0

        self.input_tokens += in_tok
        self.output_tokens += out_tok
        self.cache_read_tokens += cache_read
        self.cache_creation_tokens += cache_create
        self.n_calls += 1

        self.cost_usd += (
            in_tok * prices["input"]
            + out_tok * prices["output"]
            + cache_read * prices["cache_read"]
            + cache_create * prices["cache_write"]
        )

    def __str__(self) -> str:
        return (
            f"calls={self.n_calls} tools={self.n_tool_calls} "
            f"in={self.input_tokens} out={self.output_tokens} "
            f"cache_r={self.cache_read_tokens} cache_w={self.cache_creation_tokens} "
            f"cost=${self.cost_usd:.4f}"
        )


def get_client() -> Anthropic:
    """Construct an Anthropic client. Errors loudly if API key missing."""
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is empty. Check .env (and that no empty system "
            "env var is shadowing it — see env_ignore_empty in config.py)."
        )
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def call_text(
    *,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 2048,
    cache_system: bool = True,
    stats: CallStats | None = None,
    temperature: float = 0.3,
) -> str:
    """Single-shot text call (no tools). Returns the assistant's text content.

    `cache_system=True` adds cache_control to the system prompt so the
    same prefix gets a 90% discount on subsequent calls within the 5-min TTL.
    """
    settings = get_settings()
    client = get_client()
    model_id = model or settings.AGENT_MODEL_PRIMARY

    system_param: list[dict[str, Any]] | str
    if cache_system and len(system) > 1024:  # only worth caching prefixes >= ~1KB
        system_param = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system_param = system

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_param,
                messages=[{"role": "user", "content": user}],
            )
            if stats is not None:
                stats.add(model_id, resp.usage)
            # Concatenate text blocks; reject anything else.
            chunks = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            return "".join(chunks)
        except (RateLimitError, APIStatusError) as exc:
            last_err = exc
            wait = 2 ** attempt
            logger.warning("Anthropic transient error (attempt %d/3): %s — sleeping %ds",
                           attempt + 1, exc, wait)
            time.sleep(wait)
        except APIError as exc:
            raise
    raise RuntimeError(f"Anthropic call_text failed after retries: {last_err}")


def call_json(
    *,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 2048,
    cache_system: bool = True,
    stats: CallStats | None = None,
    schema_hint: str = "",
) -> dict[str, Any]:
    """Like call_text but parses a JSON object out of the response.

    Tolerates surrounding prose (extracts the first {...} block via regex)
    so we don't fail on chatty wrappers. Raises ValueError on unparseable.
    """
    suffix = (
        "\n\nRespond ONLY with a single JSON object. No prose, no markdown "
        "fences, no commentary. The schema is:\n" + schema_hint
        if schema_hint
        else "\n\nRespond ONLY with a single JSON object. No prose, no markdown."
    )
    text = call_text(
        system=system + suffix,
        user=user,
        model=model,
        max_tokens=max_tokens,
        cache_system=cache_system,
        stats=stats,
        temperature=0.1,  # JSON output wants low temperature
    )
    return _extract_json(text)


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first balanced {...} block from a string and json.loads it."""
    text = text.strip()
    if text.startswith("```"):
        # Strip code fences: ```json\n...\n```
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Find first '{' and matching '}'.
    start = text.find("{")
    if start < 0:
        raise ValueError(f"No JSON object found in response: {text[:200]}")
    depth = 0
    end = -1
    in_string = False
    escape = False
    for i, ch in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise ValueError(f"Unbalanced JSON in response: {text[:200]}")
    return json.loads(text[start:end])


# ---------------------------------------------------------------------------
# Tool-use loop helper (used by the researcher).
# ---------------------------------------------------------------------------


def call_with_tools(
    *,
    system: str,
    user: str,
    tools: list[dict[str, Any]],
    tool_handlers: dict[str, Any],
    model: str | None = None,
    max_tokens: int = 2048,
    max_tool_calls: int = 8,
    cache_system: bool = True,
    stats: CallStats | None = None,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """Run a tool-use loop until the model returns end_turn or hits the cap.

    Returns:
        {
            "final_text": str,
            "tool_log": [
                {"name": str, "input": dict, "output": Any, "is_error": bool},
                ...
            ],
        }

    The loop appends tool results back to messages and re-invokes the model
    until end_turn. On reaching max_tool_calls we send a final user message
    asking the model to finalize without further tool calls.
    """
    settings = get_settings()
    client = get_client()
    model_id = model or settings.AGENT_MODEL_PRIMARY

    system_param: list[dict[str, Any]] | str
    if cache_system and len(system) > 1024:
        system_param = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system_param = system

    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    tool_log: list[dict[str, Any]] = []

    for turn in range(max_tool_calls + 2):
        force_finalize = turn == max_tool_calls
        if force_finalize:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have hit the tool-call budget for this story. "
                        "Finalize your dossier with the evidence you have so far. "
                        "Do not call any more tools."
                    ),
                }
            )

        resp = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_param,
            tools=[t for t in tools] if not force_finalize else [],
            messages=messages,
        )
        if stats is not None:
            stats.add(model_id, resp.usage)

        if resp.stop_reason in ("end_turn", "stop_sequence", "max_tokens"):
            text_chunks = [
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            ]
            return {"final_text": "".join(text_chunks), "tool_log": tool_log}

        if resp.stop_reason != "tool_use":
            logger.warning("Unexpected stop_reason=%s — treating as end_turn", resp.stop_reason)
            text_chunks = [
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            ]
            return {"final_text": "".join(text_chunks), "tool_log": tool_log}

        # Append assistant message verbatim (must include all tool_use blocks).
        messages.append({"role": "assistant", "content": resp.content})

        # Run each tool_use block.
        tool_results: list[dict[str, Any]] = []
        for block in resp.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            name = block.name
            tool_input = dict(block.input or {})
            handler = tool_handlers.get(name)
            if handler is None:
                output = {"error": f"unknown tool: {name}"}
                is_error = True
            else:
                try:
                    output = handler(**tool_input)
                    is_error = False
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tool %s failed", name)
                    output = {"error": f"{type(exc).__name__}: {exc}"}
                    is_error = True
            if stats is not None:
                stats.n_tool_calls += 1
            tool_log.append(
                {
                    "name": name,
                    "input": tool_input,
                    "output": output,
                    "is_error": is_error,
                }
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output, default=str)[:30_000],
                    "is_error": is_error,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("call_with_tools: exceeded max iterations without finalizing")


# ---------------------------------------------------------------------------
# Prompt loader.
# ---------------------------------------------------------------------------


_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Read a system prompt from backend/agent/prompts/{name}.txt."""
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")
