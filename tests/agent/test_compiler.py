"""RuleSet compiler — yaml dict → RuleSet (R1.1~R1.7)."""

import copy
import unittest

from thesis_config import DEFAULT_CONFIG


class CompilerHappyPathTests(unittest.TestCase):
    def test_compiles_default_config_to_mvp_rules(self):
        from thesis_agent.spec.compiler import compile

        rs = compile(DEFAULT_CONFIG)
        rule_ids = {r.id for r in rs.rules}
        self.assertIn("body.font.east_asia", rule_ids)
        self.assertIn("body.font.size", rule_ids)
        self.assertIn("body.line_spacing", rule_ids)
        self.assertIn("heading.h1.style_present", rule_ids)
        self.assertIn("toc.entry_count", rule_ids)

    def test_metadata_unknown_keys_collected_with_dotted_path(self):
        from thesis_agent.spec.compiler import compile

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["body"]["totally_unknown_subkey"] = 1
        cfg["new_top_level"] = "x"
        rs = compile(cfg)
        # Order is not contractual; presence is.
        unknown = set(rs.metadata.get("unknown_keys", []))
        self.assertIn("body.totally_unknown_subkey", unknown)
        self.assertIn("new_top_level", unknown)


class CompilerErrorTests(unittest.TestCase):
    def test_invalid_severity_in_yaml_rejected(self):
        from thesis_agent.spec.compiler import (
            CompilerError,
            compile,
        )

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg.setdefault("_overrides", {})["heading.h1.style_present"] = {
            "severity": "critical",  # invalid
        }
        with self.assertRaises(CompilerError):
            compile(cfg)

    def test_duplicate_rule_id_after_merge_raises(self):
        from thesis_agent.spec.compiler import (
            DuplicateRuleError,
            _build_rules_with_duplicates_for_testing,
            compile_rules,
        )

        rules = _build_rules_with_duplicates_for_testing()
        with self.assertRaises(DuplicateRuleError):
            compile_rules(rules)


class ProfileLoaderTests(unittest.TestCase):
    def test_load_profile_scau_2024_equivalent_to_yaml_compile(self):
        from thesis_agent.spec.compiler import compile
        from thesis_agent.spec.profiles import load_profile
        from thesis_agent.ingest.template_loader import from_yaml

        # The profile loader should produce the same rule ids as compiling
        # the on-disk YAML through the public from_yaml + compile path.
        rs_via_profile = load_profile("scau_2024")
        merged_yaml = from_yaml("defaults/scau_2024.yaml")
        rs_via_yaml = compile(merged_yaml)
        self.assertEqual(
            sorted(r.id for r in rs_via_profile.rules),
            sorted(r.id for r in rs_via_yaml.rules),
        )

    def test_unknown_profile_raises(self):
        from thesis_agent.spec.profiles import (
            UnknownProfileError,
            load_profile,
        )

        with self.assertRaises(UnknownProfileError):
            load_profile("definitely_not_real")


if __name__ == "__main__":
    unittest.main()
