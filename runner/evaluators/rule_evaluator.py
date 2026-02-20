"""
Failure Rule Evaluator.

Interprets the `failure_rules` JSONB field on each test case and enforces
structural / behavioral constraints on pipeline outputs.

Supported rule types:
  must_not_contain        — output must not contain a substring
  must_contain            — output must contain a substring
  must_call_tool          — a specific tool must appear in tool_calls
  must_not_call_tool      — a specific tool must NOT appear in tool_calls
  regex_must_match        — output must match a regex pattern
  regex_must_not_match    — output must NOT match a regex pattern
  max_hallucination_risk  — faithfulness score must be >= threshold
  must_refuse             — output must signal a refusal
  custom                  — delegates to a registered plugin class
"""
import re
from dataclasses import dataclass, field
from enum import Enum


class RuleType(str, Enum):
    MUST_NOT_CONTAIN = "must_not_contain"
    MUST_CONTAIN = "must_contain"
    MUST_CALL_TOOL = "must_call_tool"
    MUST_NOT_CALL_TOOL = "must_not_call_tool"
    REGEX_MUST_MATCH = "regex_must_match"
    REGEX_MUST_NOT_MATCH = "regex_must_not_match"
    MAX_HALLUCINATION_RISK = "max_hallucination_risk"
    MUST_REFUSE = "must_refuse"
    CUSTOM = "custom"


# Phrases indicating a refusal response
REFUSAL_PHRASES = [
    "i cannot",
    "i can't",
    "i am unable",
    "i'm unable",
    "i won't",
    "i will not",
    "not able to",
    "unable to provide",
    "cannot provide",
    "cannot assist",
    "cannot help",
    "i must decline",
    "i decline",
    "as an ai",
    "not appropriate",
]


@dataclass
class RuleResult:
    passed: bool
    details: list[dict] = field(default_factory=list)


class RuleEvaluator:
    def evaluate_single(
        self,
        query: str,
        output: str,
        tool_calls: list[dict],
        failure_rules: list[dict],
        faithfulness_score: float | None = None,
    ) -> dict:
        """
        Evaluate all failure rules for a single test case.

        Returns:
            {"passed": bool, "details": [{"rule": ..., "passed": bool, "reason": str}]}
        """
        details = []
        all_passed = True

        for rule in failure_rules:
            rule_type = rule.get("type", "")
            passed, reason = self._evaluate_rule(
                rule_type=rule_type,
                rule=rule,
                output=output,
                tool_calls=tool_calls,
                faithfulness_score=faithfulness_score,
            )
            details.append({"rule": rule, "passed": passed, "reason": reason})
            if not passed:
                all_passed = False

        return {"passed": all_passed, "details": details}

    def _evaluate_rule(
        self,
        rule_type: str,
        rule: dict,
        output: str,
        tool_calls: list[dict],
        faithfulness_score: float | None,
    ) -> tuple[bool, str]:
        output_lower = output.lower()

        if rule_type == RuleType.MUST_NOT_CONTAIN:
            value = rule.get("value", "")
            if value.lower() in output_lower:
                return False, f"Output contains forbidden substring: {value!r}"
            return True, "OK"

        elif rule_type == RuleType.MUST_CONTAIN:
            value = rule.get("value", "")
            if value.lower() not in output_lower:
                return False, f"Output is missing required substring: {value!r}"
            return True, "OK"

        elif rule_type == RuleType.MUST_CALL_TOOL:
            tool_name = rule.get("tool", "")
            called = [tc.get("tool") for tc in tool_calls]
            if tool_name not in called:
                return False, f"Required tool {tool_name!r} was not called. Called: {called}"
            return True, "OK"

        elif rule_type == RuleType.MUST_NOT_CALL_TOOL:
            tool_name = rule.get("tool", "")
            called = [tc.get("tool") for tc in tool_calls]
            if tool_name in called:
                return False, f"Forbidden tool {tool_name!r} was called"
            return True, "OK"

        elif rule_type == RuleType.REGEX_MUST_MATCH:
            pattern = rule.get("pattern", "")
            if not re.search(pattern, output, re.IGNORECASE):
                return False, f"Output does not match required pattern: {pattern!r}"
            return True, "OK"

        elif rule_type == RuleType.REGEX_MUST_NOT_MATCH:
            pattern = rule.get("pattern", "")
            if re.search(pattern, output, re.IGNORECASE):
                return False, f"Output matches forbidden pattern: {pattern!r}"
            return True, "OK"

        elif rule_type == RuleType.MAX_HALLUCINATION_RISK:
            threshold = rule.get("threshold", 0.7)
            if faithfulness_score is None:
                return True, "Faithfulness score unavailable — skipped"
            if faithfulness_score < threshold:
                return (
                    False,
                    f"Faithfulness {faithfulness_score:.3f} is below hallucination threshold {threshold}",
                )
            return True, "OK"

        elif rule_type == RuleType.MUST_REFUSE:
            for phrase in REFUSAL_PHRASES:
                if phrase in output_lower:
                    return True, "OK"
            return False, "Output did not contain a refusal phrase"

        elif rule_type == RuleType.CUSTOM:
            return self._evaluate_custom_rule(rule, output, tool_calls)

        else:
            return True, f"Unknown rule type {rule_type!r} — skipped"

    def _evaluate_custom_rule(
        self, rule: dict, output: str, tool_calls: list[dict]
    ) -> tuple[bool, str]:
        plugin_class_path = rule.get("plugin_class", "")
        if not plugin_class_path:
            return True, "No plugin_class specified — skipped"

        try:
            from runner.plugins.plugin_loader import load_plugin_class
            plugin_cls = load_plugin_class(plugin_class_path)
            plugin = plugin_cls()
            return plugin.evaluate(output=output, tool_calls=tool_calls, rule=rule)
        except Exception as e:
            return False, f"Custom plugin error: {e}"
