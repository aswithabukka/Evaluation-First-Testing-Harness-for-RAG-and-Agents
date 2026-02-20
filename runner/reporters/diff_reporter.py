"""
Diff reporter — generates a regression diff between two runs.

This is called by the CLI `rageval report --diff` and by the dashboard DiffView.
"""


def format_diff(diff: dict) -> str:
    """Returns a terminal-friendly diff string."""
    lines = []
    regressions = diff.get("regressions", [])
    improvements = diff.get("improvements", [])
    metric_deltas = diff.get("metric_deltas", {})

    lines.append("\n── REGRESSION DIFF ──────────────────────────────────────────────────")
    lines.append(f"  Baseline Run : {diff.get('baseline_run_id', 'none')}")
    lines.append(f"  Current Run  : {diff.get('run_id', 'unknown')}")
    lines.append("")

    if metric_deltas:
        lines.append("  Metric Deltas (current − baseline):")
        for metric, delta in metric_deltas.items():
            if delta is not None:
                arrow = "▲" if delta > 0 else "▼"
                color_marker = "+" if delta >= 0 else "-"
                lines.append(f"    {color_marker} {metric:<28} {arrow}{abs(delta):.3f}")
        lines.append("")

    if regressions:
        lines.append(f"  NEW FAILURES ({len(regressions)}) — previously passing, now failing:")
        for reg in regressions:
            lines.append(f"    ✗ {reg.get('query', '')[:60]}")
            lines.append(f"      Reason : {reg.get('failure_reason') or 'metric threshold breach'}")
            c = reg.get("current_scores", {})
            b = reg.get("baseline_scores", {})
            for m in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
                cv = c.get(m)
                bv = b.get(m)
                if cv is not None and bv is not None:
                    delta = cv - bv
                    arrow = "▲" if delta > 0 else "▼"
                    lines.append(f"      {m:<24} {bv:.3f} → {cv:.3f}  ({arrow}{abs(delta):.3f})")
        lines.append("")
    else:
        lines.append("  No regressions detected ✓")
        lines.append("")

    if improvements:
        lines.append(f"  IMPROVEMENTS ({len(improvements)}) — previously failing, now passing:")
        for imp in improvements:
            lines.append(f"    ✓ {imp.get('query', '')[:60]}")

    lines.append("─" * 70 + "\n")
    return "\n".join(lines)
