"""Thin wrapper over the Anthropic SDK: text generation, schema-validated extraction, and local spend tracking."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from . import config, db

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None
_client_key: str | None = None

# USD per million tokens: (input, output, cache read, cache write 5m). Anthropic has no balance endpoint for
# individual accounts, so we price every call ourselves from the usage block it returns.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-fable-5-1": (10.00, 50.00, 0.25, 12.50),
}


class LLMError(RuntimeError):
    pass


def client() -> anthropic.Anthropic:
    global _client, _client_key
    key = config.get("anthropic_api_key").strip()
    if not key:
        raise LLMError("No Anthropic API key. Set it in Settings (or env ANTHROPIC_API_KEY).")
    if _client is None or _client_key != key:
        _client = anthropic.Anthropic(api_key=key, max_retries=3, timeout=600.0)
        _client_key = key
    return _client


def _text_of(resp) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


def _price(model: str) -> tuple[float, float, float, float]:
    if model in PRICES:
        return PRICES[model]
    for k, v in PRICES.items():  # e.g. a dated alias of a known model
        if model.startswith(k):
            return v
    return PRICES["claude-sonnet-5-5"]


def cost_of(model: str, inp: int, out: int, cache_read: int, cache_write: int) -> float:
    pi, po, pr, pw = _price(model)
    return (inp * pi + out * po + cache_read * pr + cache_write * pw) / 1_000_000


def _record(resp, model: str, purpose: str) -> None:
    """Store the usage block of a response, priced. Never raises: tracking must not break the call."""
    try:
        u = resp.usage
        inp, out = int(u.input_tokens or 0), int(u.output_tokens or 0)
        cr = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        cw = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        used_model = getattr(resp, "model", None) or model   # server-side fallback may answer with another model
        db.insert("llm_usage", {"at": db.now_iso(), "model": used_model, "purpose": purpose, "input_tokens": inp,
                                "output_tokens": out, "cache_read_tokens": cr, "cache_write_tokens": cw,
                                "cost_usd": round(cost_of(used_model, inp, out, cr, cw), 6)})
    except Exception:  # noqa: BLE001
        pass


def _friendly(e: anthropic.APIStatusError) -> LLMError:
    msg = str(getattr(e, "message", "") or e)
    if "credit balance" in msg.lower():
        return LLMError("Anthropic says your credit balance is too low. Top up at platform.claude.com/settings/billing.")
    from .messages import friendly_error
    return LLMError(friendly_error(e) if e.status_code in (401, 429, 529) else f"Anthropic error {e.status_code}: {msg}")


def generate(system: str, user: str, *, model: str | None = None, effort: str = "medium",
             max_tokens: int = 8000, purpose: str = "generate") -> str:
    """Plain-text generation. Uses server-side refusal fallbacks so a safety decline
    on the main model is retried automatically on Anthropic's recommended fallback."""
    model = model or config.get("model_main")
    try:
        resp = client().beta.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIStatusError as e:
        raise _friendly(e) from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Couldn't reach Anthropic. Check your internet connection and try again.") from e
    _record(resp, model, purpose)
    if resp.stop_reason == "refusal":
        why = getattr(getattr(resp, "stop_details", None), "explanation", "") or "model declined"
        raise LLMError(f"Model refused: {why}")
    if resp.stop_reason == "max_tokens":
        raise LLMError("Output truncated (max_tokens). Raise the limit.")
    return _text_of(resp)


def extract(system: str, user: str, schema: type[T], *, model: str | None = None,
            effort: str = "low", max_tokens: int = 4000, purpose: str | None = None) -> T:
    """Schema-validated JSON extraction via structured outputs."""
    model = model or config.get("model_fast")
    try:
        resp = client().messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": effort},
        )
    except anthropic.APIStatusError as e:
        raise _friendly(e) from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Couldn't reach Anthropic. Check your internet connection and try again.") from e
    _record(resp, model, purpose or schema.__name__)
    if resp.stop_reason == "refusal":
        why = getattr(getattr(resp, "stop_details", None), "explanation", "") or "model declined"
        raise LLMError(f"Model refused: {why}")
    parsed = getattr(resp, "parsed_output", None)
    if parsed is None:
        # Fall back to parsing the text block ourselves.
        parsed = schema.model_validate_json(_text_of(resp))
    return parsed


def check_key() -> tuple[bool, str]:
    try:
        models = client().models.list()
        ids = [m.id for m in models][:5]
        return True, "OK. Models visible: " + ", ".join(ids)
    except LLMError as e:
        return False, str(e)
    except anthropic.AuthenticationError:
        return False, "Invalid API key."
    except anthropic.APIConnectionError:
        return False, "Network error reaching api.anthropic.com."
    except anthropic.APIStatusError as e:
        return False, f"API error {e.status_code}: {e.message}"


def spend_summary() -> dict:
    """What the app has spent (priced locally) and the estimated balance left, if the user told us a starting point."""
    def total(where: str = "", params: tuple = ()) -> tuple[float, int]:
        r = db.q1(f"SELECT COALESCE(SUM(cost_usd),0) AS c, COUNT(*) AS n FROM llm_usage {where}", params) or {}
        return float(r.get("c", 0) or 0), int(r.get("n", 0) or 0)

    all_c, all_n = total()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    today_c, today_n = total("WHERE at >= ?", (today,))
    start = config.get("credits_start_usd").strip()
    as_of = config.get("credits_as_of").strip()
    remaining = since_c = None
    if start and as_of:
        since_c, _ = total("WHERE at >= ?", (as_of,))
        try:
            remaining = float(start) - since_c
        except ValueError:
            remaining = None
    by_purpose = db.q("SELECT purpose, model, COUNT(*) AS n, SUM(cost_usd) AS c FROM llm_usage "
                      "GROUP BY purpose, model ORDER BY c DESC LIMIT 8")
    return {"all": all_c, "all_n": all_n, "today": today_c, "today_n": today_n, "start": start, "as_of": as_of,
            "since": since_c, "remaining": remaining, "by_purpose": by_purpose}


def safe_json(s: str, default=None):
    try:
        return json.loads(s)
    except Exception:
        return default
