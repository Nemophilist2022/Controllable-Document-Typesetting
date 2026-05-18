"""OpenAI-compatible LLM client.

Speaks the OpenAI Chat Completions JSON wire format, which is supported
by:
- OpenAI (api.openai.com/v1)
- DeepSeek (api.deepseek.com)
- 通义千问 dashscope-compatible mode
- Local vLLM / llama.cpp / Ollama via their OpenAI-compatible adapters

Zero external dependencies — uses ``urllib.request`` + ``json`` from
the standard library so MVP doesn't pull in ``openai`` or ``requests``.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from .outbound_guard import OutboundPayloadGuardError, enforce as guard_enforce

_LOG = logging.getLogger(__name__)

# Defaults frozen by D1 / R5.8 / R5.9.
DEFAULT_TIMEOUT_SEC = 30                # D1
DEFAULT_MAX_TOKENS = 4096               # R5.9
DEFAULT_TEMPERATURE = 0.2               # R5.8
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Settings + telemetry
# ---------------------------------------------------------------------------

@dataclass
class LLMSettings:
    """How to reach the LLM. ``api_key`` is required; everything else
    falls back to provider defaults."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class LLMTelemetry:
    """Aggregated counters surfaced via ``report.json.meta``."""

    calls: int = 0
    timeouts: int = 0
    errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd_estimate: float = 0.0


# Simple per-token price table (USD). Only used when telemetry is on
# and the provider didn't return cost itself. Numbers are intentionally
# conservative — actual billing varies by tier.
_PRICE_TABLE = {
    # OpenAI
    "gpt-4o-mini": (0.15e-6, 0.60e-6),
    "gpt-4o":      (2.50e-6, 10.0e-6),
    # DeepSeek
    "deepseek-chat":     (0.27e-6, 1.10e-6),
    "deepseek-reasoner": (0.55e-6, 2.19e-6),
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rate = _PRICE_TABLE.get(model)
    if rate is None:
        return 0.0
    in_rate, out_rate = rate
    return prompt_tokens * in_rate + completion_tokens * out_rate


# ---------------------------------------------------------------------------
# Loading from environment / CLI flags
# ---------------------------------------------------------------------------

def settings_from_env(
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[LLMSettings]:
    """Build :class:`LLMSettings` from explicit args + env, or return
    None when no API key is available — callers should treat None as
    "no LLM configured" (R5.7).
    """
    key = api_key or os.environ.get("THESIS_AGENT_LLM_API_KEY")
    if not key:
        return None
    return LLMSettings(
        api_key=key,
        base_url=base_url
            or os.environ.get("THESIS_AGENT_LLM_BASE_URL", DEFAULT_BASE_URL),
        model=model
            or os.environ.get("THESIS_AGENT_LLM_MODEL", DEFAULT_MODEL),
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class OpenAICompatibleClient:
    """Speaks OpenAI's ``/v1/chat/completions`` JSON.

    The expected response shape from the LLM is the structured
    Diagnosis JSON we ask for in the prompt; we don't enforce a schema
    here, that's the diagnoser's job. We only deliver ``raw`` to the
    diagnoser.
    """

    def __init__(self, settings: LLMSettings, *, telemetry: Optional[LLMTelemetry] = None):
        self._s = settings
        self.telemetry = telemetry or LLMTelemetry()

    @property
    def settings(self) -> LLMSettings:
        return self._s

    def complete(self, prompt: str, schema: dict) -> dict:
        """Send *prompt*, return parsed JSON dict.

        Returns an empty dict on any non-fatal error; the diagnoser
        treats that as "schema mismatch", retries, and ultimately
        falls back to ``needs_human=True``.
        """
        # R13.3 outbound guard. Raised as a normal error (not silently
        # swallowed) so the diagnoser can observe it via the schema
        # check loop and still tag the diagnosis needs_human.
        # Counted as an attempt + error so telemetry reflects that we
        # tried to fire something off.
        self.telemetry.calls += 1
        try:
            guard_enforce(prompt)
        except OutboundPayloadGuardError as exc:
            self.telemetry.errors += 1
            _LOG.warning("LLM outbound guard rejected payload: %s", exc)
            return {}

        payload = {
            "model": self._s.model,
            "messages": [
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self._s.temperature,
            "max_tokens": self._s.max_tokens,
            # Ask the model to return JSON when the provider supports
            # it; fallback to plain text if not.
            "response_format": {"type": "json_object"},
        }

        url = self._s.base_url.rstrip("/") + "/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._s.api_key}",
            "Content-Type": "application/json",
            **self._s.extra_headers,
        }

        started = time.perf_counter()
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self._s.timeout_sec) as resp:
                raw = resp.read().decode("utf-8")
        except socket.timeout:
            self.telemetry.timeouts += 1
            _LOG.warning("LLM call timed out after %.1fs", time.perf_counter() - started)
            return {}
        except urllib.error.URLError as exc:
            self.telemetry.errors += 1
            _LOG.warning("LLM call failed: %s", exc)
            return {}
        except Exception as exc:  # defensive
            self.telemetry.errors += 1
            _LOG.warning("LLM unexpected error: %s", exc)
            return {}

        return self._parse(raw)

    def _parse(self, raw: str) -> dict:
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            self.telemetry.errors += 1
            return {}

        usage = envelope.get("usage") or {}
        self.telemetry.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.telemetry.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        self.telemetry.total_tokens += int(usage.get("total_tokens", 0) or 0)

        choices = envelope.get("choices") or []
        if not choices:
            self.telemetry.errors += 1
            return {}
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content") or ""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # The model didn't produce JSON despite the response_format
            # hint. Diagnoser will see this as a schema mismatch and
            # retry / fall back.
            self.telemetry.errors += 1
            return {}

        # Update cost estimate after the parse succeeds.
        delta_cost = _estimate_cost(
            self._s.model,
            int(usage.get("prompt_tokens", 0) or 0),
            int(usage.get("completion_tokens", 0) or 0),
        )
        self.telemetry.cost_usd_estimate += delta_cost
        return parsed


# ---------------------------------------------------------------------------
# System prompt — kept short so token cost stays predictable
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a thesis-formatting compliance assistant. "
    "Given a single failed rule (rule_id, severity, locator, evidence), "
    "return ONE JSON object with these keys: "
    "rule_id, root_cause, fix_plan (array of {tool, params, expected_effect}), "
    "confidence (0..1), needs_human (bool), rationale. "
    "Tool names are restricted to those listed below. "
    "Do NOT echo or paraphrase document content; reason only from the "
    "fields you receive. Never include OOXML or raw paragraph text."
)
