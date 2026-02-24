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
  must_return_label       — output must contain one of the expected labels
  max_latency_ms          — pipeline response time must be under threshold
  must_not_contain_pii    — output must not contain PII patterns
  json_schema_valid       — output must be valid JSON, optionally matching a schema
  max_token_count         — output token count must not exceed limit
  must_cite_source        — output must contain citation markers
  semantic_similarity_above — output must be semantically similar to expected text
"""
import json
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
    MUST_RETURN_LABEL = "must_return_label"
    MAX_LATENCY_MS = "max_latency_ms"
    MUST_NOT_CONTAIN_PII = "must_not_contain_pii"
    JSON_SCHEMA_VALID = "json_schema_valid"
    MAX_TOKEN_COUNT = "max_token_count"
    MUST_CITE_SOURCE = "must_cite_source"
    SEMANTIC_SIMILARITY_ABOVE = "semantic_similarity_above"


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


# Regex patterns for detecting PII in output
PII_PATTERNS = {
    "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
}

# Default citation marker patterns
DEFAULT_CITATION_PATTERNS = [
    "[Source:",
    "[source:",
    "[Citation:",
    "[citation:",
    "[Ref:",
    "[ref:",
    "(Source:",
    "(source:",
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
        latency_ms: float | None = None,
    ) -> dict:
        """
        Evaluate all failure rules for a single test case.

        Args:
            query: The input query for the test case.
            output: The pipeline output text.
            tool_calls: List of tool call dicts from the pipeline.
            failure_rules: List of rule dicts to evaluate.
            faithfulness_score: Optional faithfulness score for hallucination checks.
            latency_ms: Optional pipeline response time in milliseconds for
                        max_latency_ms rule evaluation.

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
                latency_ms=latency_ms,
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
        latency_ms: float | None = None,
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

        elif rule_type == RuleType.MUST_RETURN_LABEL:
            labels = rule.get("labels", [])
            if not labels:
                return True, "No labels specified — skipped"
            for label in labels:
                if label.lower() in output_lower:
                    return True, f"OK — found label {label!r}"
            return False, f"Output does not contain any of the expected labels: {labels}"

        elif rule_type == RuleType.MAX_LATENCY_MS:
            threshold = rule.get("threshold", 5000)
            if latency_ms is None:
                return True, "Latency measurement unavailable — skipped"
            if latency_ms > threshold:
                return (
                    False,
                    f"Latency {latency_ms:.1f}ms exceeds threshold {threshold}ms",
                )
            return True, f"OK — latency {latency_ms:.1f}ms within {threshold}ms limit"

        elif rule_type == RuleType.MUST_NOT_CONTAIN_PII:
            found_pii = []
            for pii_type, pattern in PII_PATTERNS.items():
                matches = re.findall(pattern, output)
                if matches:
                    found_pii.append(f"{pii_type}: {matches}")
            if found_pii:
                return False, f"Output contains PII — {'; '.join(found_pii)}"
            return True, "OK — no PII detected"

        elif rule_type == RuleType.JSON_SCHEMA_VALID:
            try:
                parsed = json.loads(output)
            except (json.JSONDecodeError, TypeError) as e:
                return False, f"Output is not valid JSON: {e}"
            schema = rule.get("schema")
            if schema is not None:
                try:
                    import jsonschema
                    jsonschema.validate(instance=parsed, schema=schema)
                except ImportError:
                    return True, "OK — valid JSON (jsonschema library not installed, schema validation skipped)"
                except jsonschema.ValidationError as e:
                    return False, f"JSON does not match schema: {e.message}"
            return True, "OK — valid JSON"

        elif rule_type == RuleType.MAX_TOKEN_COUNT:
            max_tokens = rule.get("max_tokens", 500)
            token_count = len(output.split())
            if token_count > max_tokens:
                return (
                    False,
                    f"Output has {token_count} tokens, exceeds limit of {max_tokens}",
                )
            return True, f"OK — {token_count} tokens within {max_tokens} limit"

        elif rule_type == RuleType.MUST_CITE_SOURCE:
            pattern = rule.get("pattern")
            if pattern:
                # User specified a custom citation pattern
                if pattern in output:
                    return True, f"OK — found citation pattern {pattern!r}"
                return False, f"Output does not contain citation pattern {pattern!r}"
            # Check against default citation patterns
            for default_pattern in DEFAULT_CITATION_PATTERNS:
                if default_pattern in output:
                    return True, f"OK — found citation marker {default_pattern!r}"
            return False, "Output does not contain any citation markers"

        elif rule_type == RuleType.SEMANTIC_SIMILARITY_ABOVE:
            expected = rule.get("expected", "")
            threshold = rule.get("threshold", 0.8)
            if not expected:
                return True, "No expected text specified — skipped"
            # Use Jaccard similarity on word sets as a proxy for semantic similarity
            output_words = set(output_lower.split())
            expected_words = set(expected.lower().split())
            if not output_words and not expected_words:
                similarity = 1.0
            elif not output_words or not expected_words:
                similarity = 0.0
            else:
                intersection = output_words & expected_words
                union = output_words | expected_words
                similarity = len(intersection) / len(union)
            if similarity < threshold:
                return (
                    False,
                    f"Semantic similarity {similarity:.3f} is below threshold {threshold}",
                )
            return True, f"OK — similarity {similarity:.3f} >= {threshold}"

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
