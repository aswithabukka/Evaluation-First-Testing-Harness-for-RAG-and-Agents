"""Prints a human-readable evaluation report to stdout."""


def print_report(report: dict) -> None:
    run = report.get("run", {})
    results = report.get("results", [])
    summary = report.get("summary", {})
    gate = report.get("gate", {})

    print("\n" + "=" * 70)
    print(f"  RAG EVAL HARNESS — Run Report")
    print("=" * 70)
    print(f"  Run ID        : {run.get('id', 'N/A')}")
    print(f"  Test Set      : {run.get('test_set_id', 'N/A')}")
    print(f"  Pipeline Ver  : {run.get('pipeline_version', 'N/A')}")
    print(f"  Git Commit    : {run.get('git_commit_sha', 'N/A')}")
    print(f"  Branch        : {run.get('git_branch', 'N/A')}")
    print(f"  Status        : {run.get('status', 'N/A').upper()}")
    print()

    print("  METRICS SUMMARY")
    print("  " + "-" * 50)
    metrics_to_show = [
        ("Faithfulness", "avg_faithfulness"),
        ("Answer Relevancy", "avg_answer_relevancy"),
        ("Context Precision", "avg_context_precision"),
        ("Context Recall", "avg_context_recall"),
        ("Pass Rate", "pass_rate"),
    ]
    for label, key in metrics_to_show:
        value = summary.get(key)
        if value is not None:
            bar = _bar(value)
            status = "✓" if value >= 0.7 else "✗"
            print(f"  {status} {label:<22} {value:.3f}  {bar}")
    print()

    print(f"  TEST CASES  ({summary.get('passed_cases', 0)}/{summary.get('total_cases', 0)} passed)")
    print("  " + "-" * 50)
    for r in results:
        icon = "✓" if r.get("passed") else "✗"
        query = r.get("query", r.get("test_case_id", ""))[:55]
        reason = f"  → {r.get('failure_reason', '')}" if not r.get("passed") else ""
        print(f"  {icon} {query}{reason}")
    print()

    if gate:
        passed = gate.get("passed")
        label = "APPROVED ✓" if passed else "BLOCKED ✗"
        print(f"  RELEASE GATE : {label}")
        for failure in gate.get("metric_failures", []):
            print(
                f"    - {failure['metric']}: {failure['actual']:.3f} < {failure['threshold']:.3f} "
                f"(Δ {failure['delta']:.3f})"
            )
        for failure in gate.get("rule_failures", []):
            print(f"    - Rule failure on test_case_id={failure.get('test_case_id')}")

    diff = report.get("diff")
    if diff and diff.get("regressions"):
        print()
        print(f"  REGRESSIONS ({len(diff['regressions'])} new failures vs baseline)")
        print("  " + "-" * 50)
        for reg in diff["regressions"]:
            print(f"  ✗ {reg.get('query', '')[:55]}")
            print(f"      Reason: {reg.get('failure_reason', 'unknown')}")
            for metric, delta in diff.get("metric_deltas", {}).items():
                if delta is not None and delta < 0:
                    print(f"      {metric}: Δ{delta:+.3f}")

    print("=" * 70 + "\n")


def _bar(value: float, width: int = 20) -> str:
    filled = int(value * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"
