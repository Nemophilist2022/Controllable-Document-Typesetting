"""Outbound payload guard — R13.3 enforcement."""

import unittest

from thesis_agent.diagnoser.outbound_guard import (
    MAX_CJK_RUN, MAX_PROMPT_BYTES, OutboundPayloadGuardError, enforce,
)


class OutboundGuardTests(unittest.TestCase):
    def test_short_prompt_passes(self):
        enforce("rule_id=body.font.size\nseverity=must\n")  # no raise

    def test_short_cjk_passes(self):
        # 30 CJK chars is well below the cap.
        enforce("rule_id=body.font.size\n" + "中" * 30)

    def test_long_cjk_run_blocked(self):
        leak = "中" * (MAX_CJK_RUN + 5)
        with self.assertRaises(OutboundPayloadGuardError) as cm:
            enforce(f"rule_id=x\nevidence={leak}")
        self.assertIn("CJK run", str(cm.exception))

    def test_oversize_prompt_blocked(self):
        # MAX_PROMPT_BYTES is 4096; pad with ASCII to overflow without
        # tripping the CJK rule first.
        big = "a" * (MAX_PROMPT_BYTES + 10)
        with self.assertRaises(OutboundPayloadGuardError):
            enforce(big)

    def test_non_string_blocked(self):
        with self.assertRaises(OutboundPayloadGuardError):
            enforce(b"bytes")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
