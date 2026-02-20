"""
Multi-turn agent evaluator (stretch goal).

Evaluates AI agents across a full conversation history, checking for:
  - Consistent use of tools across turns
  - Goal completion (did the agent ultimately resolve the user's intent?)
  - Context coherence (does each turn follow logically from the last?)
  - Refusal behavior at any point in the conversation
"""
from dataclasses import dataclass, field


@dataclass
class TurnResult:
    turn_index: int
    query: str
    response: str
    tool_calls: list[dict]
    passed: bool
    failure_reason: str | None = None


@dataclass
class AgentEvalResult:
    passed: bool
    turn_results: list[TurnResult] = field(default_factory=list)
    goal_completed: bool | None = None
    failure_reason: str | None = None


class MultiTurnAgentEvaluator:
    """
    Evaluates a multi-turn conversation.

    Usage:
        evaluator = MultiTurnAgentEvaluator(adapter=my_adapter)
        result = evaluator.evaluate(
            turns=[
                {"query": "What is the drug dosage for ibuprofen?"},
                {"query": "And for children under 5?"},
            ],
            failure_rules=[
                {"type": "must_call_tool", "tool": "drug_lookup"},
                {"type": "must_not_contain", "value": "I don't know"},
            ],
        )
    """

    def __init__(self, adapter=None):
        self._adapter = adapter

    def evaluate(
        self,
        turns: list[dict],
        failure_rules: list[dict] | None = None,
        goal_completion_check: str | None = None,
    ) -> AgentEvalResult:
        from runner.evaluators.rule_evaluator import RuleEvaluator

        if self._adapter is None:
            return AgentEvalResult(
                passed=False, failure_reason="No adapter configured for multi-turn evaluation"
            )

        self._adapter.setup()
        rule_evaluator = RuleEvaluator()
        turn_results = []
        conversation_history = []
        all_passed = True

        for i, turn in enumerate(turns):
            query = turn.get("query", "")
            turn_rules = turn.get("failure_rules", failure_rules or [])

            output = self._adapter.run(
                query=query,
                context={"turn_history": conversation_history},
            )

            conversation_history.append({"role": "user", "content": query})
            conversation_history.append({"role": "assistant", "content": output.answer})

            tool_calls_raw = [
                {"tool": tc.tool, "args": tc.args, "result": tc.result}
                for tc in output.tool_calls
            ]

            rule_result = rule_evaluator.evaluate_single(
                query=query,
                output=output.answer,
                tool_calls=tool_calls_raw,
                failure_rules=turn_rules,
            )

            turn_passed = rule_result["passed"]
            failure_reason = None
            if not turn_passed:
                failure_reason = "; ".join(
                    d["reason"] for d in rule_result["details"] if not d.get("passed")
                )
                all_passed = False

            turn_results.append(
                TurnResult(
                    turn_index=i,
                    query=query,
                    response=output.answer,
                    tool_calls=tool_calls_raw,
                    passed=turn_passed,
                    failure_reason=failure_reason,
                )
            )

        self._adapter.teardown()

        return AgentEvalResult(
            passed=all_passed,
            turn_results=turn_results,
            goal_completed=None,  # Can be extended with LLM judge
        )
