"""OpenAI-compatible client — happy path + failure modes.

We never hit a real network here. ``urllib.request.urlopen`` is patched
in each test; the body shape mirrors what OpenAI / DeepSeek actually
return.
"""

import io
import json
import socket
import unittest
import urllib.error
from contextlib import contextmanager
from unittest import mock

from thesis_agent.diagnoser.openai_client import (
    LLMSettings, LLMTelemetry, OpenAICompatibleClient, settings_from_env,
)


def _settings(**overrides) -> LLMSettings:
    base = {"api_key": "k", "model": "gpt-4o-mini", "base_url": "https://api.example.com/v1"}
    base.update(overrides)
    return LLMSettings(**base)


def _ok_response(content_dict, prompt_tokens=10, completion_tokens=20) -> bytes:
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(content_dict, ensure_ascii=False),
                }
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    return json.dumps(payload).encode("utf-8")


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@contextmanager
def _patched_urlopen(side_effect):
    with mock.patch(
        "thesis_agent.diagnoser.openai_client.urllib.request.urlopen",
        side_effect=side_effect,
    ) as m:
        yield m


class OpenAIClientHappyPathTests(unittest.TestCase):
    def test_returns_parsed_content_and_updates_telemetry(self):
        client = OpenAICompatibleClient(_settings(), telemetry=LLMTelemetry())
        canned = {
            "rule_id": "body.line_spacing",
            "root_cause": "set to 2.0",
            "fix_plan": [{"tool": "tool_format_body", "params": {"line_spacing": 1.5}}],
            "confidence": 0.92,
            "needs_human": False,
            "rationale": "ok",
        }
        with _patched_urlopen(side_effect=lambda req, timeout: _FakeResponse(_ok_response(canned))):
            out = client.complete("rule_id=body.line_spacing", schema={})
        self.assertEqual(out["rule_id"], "body.line_spacing")
        self.assertEqual(client.telemetry.calls, 1)
        self.assertEqual(client.telemetry.prompt_tokens, 10)
        self.assertEqual(client.telemetry.completion_tokens, 20)
        self.assertEqual(client.telemetry.total_tokens, 30)
        self.assertGreater(client.telemetry.cost_usd_estimate, 0)

    def test_unknown_model_yields_zero_cost(self):
        client = OpenAICompatibleClient(_settings(model="some-unknown-model"))
        with _patched_urlopen(side_effect=lambda req, timeout: _FakeResponse(_ok_response({"x": 1}))):
            client.complete("hi", schema={})
        self.assertEqual(client.telemetry.cost_usd_estimate, 0.0)


class OpenAIClientFailureTests(unittest.TestCase):
    def test_timeout_returns_empty_dict_and_increments_telemetry(self):
        client = OpenAICompatibleClient(_settings())
        with _patched_urlopen(side_effect=socket.timeout()):
            out = client.complete("rule_id=x", schema={})
        self.assertEqual(out, {})
        self.assertEqual(client.telemetry.timeouts, 1)
        self.assertEqual(client.telemetry.errors, 0)

    def test_http_error_returns_empty_dict_and_marks_error(self):
        client = OpenAICompatibleClient(_settings())
        with _patched_urlopen(side_effect=urllib.error.HTTPError(
            "u", 503, "service unavailable", {}, io.BytesIO(b""),
        )):
            out = client.complete("rule_id=x", schema={})
        self.assertEqual(out, {})
        self.assertGreaterEqual(client.telemetry.errors, 1)

    def test_non_json_response_returns_empty_dict(self):
        client = OpenAICompatibleClient(_settings())
        with _patched_urlopen(side_effect=lambda req, timeout: _FakeResponse(b"not json")):
            out = client.complete("rule_id=x", schema={})
        self.assertEqual(out, {})

    def test_non_json_message_content_returns_empty_dict(self):
        client = OpenAICompatibleClient(_settings())
        body = json.dumps({
            "choices": [{"message": {"content": "this is not json at all"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode("utf-8")
        with _patched_urlopen(side_effect=lambda req, timeout: _FakeResponse(body)):
            out = client.complete("rule_id=x", schema={})
        self.assertEqual(out, {})

    def test_outbound_guard_blocks_long_cjk_payload(self):
        client = OpenAICompatibleClient(_settings())
        leak = "中" * 200
        with _patched_urlopen(side_effect=lambda *a, **kw: self.fail("must not call")):
            out = client.complete(f"rule_id=x\nevidence={leak}", schema={})
        self.assertEqual(out, {})
        # The guard rejects before urllib is invoked, but the attempt
        # is still counted (calls=1) and errors+=1 so telemetry shows
        # the guard fired.
        self.assertEqual(client.telemetry.calls, 1)
        self.assertGreaterEqual(client.telemetry.errors, 1)


class SettingsFromEnvTests(unittest.TestCase):
    @staticmethod
    def _no_llm_env() -> dict:
        import os as _os
        env = dict(_os.environ)
        for k in list(env):
            if k.startswith("THESIS_AGENT_LLM_"):
                env.pop(k, None)
        return env

    def test_no_key_anywhere_returns_none(self):
        with mock.patch.dict("os.environ", self._no_llm_env(), clear=True):
            self.assertIsNone(settings_from_env())

    def test_explicit_key_overrides_env(self):
        env = self._no_llm_env()
        env["THESIS_AGENT_LLM_API_KEY"] = "env-key"
        with mock.patch.dict("os.environ", env, clear=True):
            s = settings_from_env(api_key="explicit-key")
        self.assertEqual(s.api_key, "explicit-key")

    def test_env_fallback_for_url_and_model(self):
        env = self._no_llm_env()
        env.update({
            "THESIS_AGENT_LLM_API_KEY": "k",
            "THESIS_AGENT_LLM_BASE_URL": "https://x.example/v1",
            "THESIS_AGENT_LLM_MODEL": "deepseek-chat",
        })
        with mock.patch.dict("os.environ", env, clear=True):
            s = settings_from_env()
        self.assertEqual(s.base_url, "https://x.example/v1")
        self.assertEqual(s.model, "deepseek-chat")


if __name__ == "__main__":
    unittest.main()
