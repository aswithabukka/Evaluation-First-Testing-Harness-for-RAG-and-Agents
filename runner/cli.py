"""
rageval CLI — the entry point for CI/CD pipelines.

Commands:
  rageval run    — execute an evaluation run against the configured test set
  rageval gate   — check if a run's release gate passed (exits non-zero if blocked)
  rageval report — print a structured report for a completed run
"""
import json
import os
import sys
import time

import click
import httpx


def _api_url(config) -> str:
    return config.api.url.rstrip("/") + "/api/v1"


def _headers(config) -> dict:
    h = {"Content-Type": "application/json"}
    if config.api.api_key:
        h["Authorization"] = f"Bearer {config.api.api_key}"
    return h


@click.group()
def cli():
    """RAG Evaluation Harness — evaluate your RAG pipeline before every release."""
    pass


@cli.command()
@click.option("--config", default="rageval.yaml", show_default=True, help="Path to rageval.yaml")
@click.option("--test-set", "test_set_id", default=None, help="Test set UUID (overrides config)")
@click.option("--commit-sha", default=None, envvar="GITHUB_SHA", help="Git commit SHA")
@click.option("--branch", default=None, envvar="GITHUB_REF_NAME", help="Git branch")
@click.option("--pr-number", default=None, envvar="GITHUB_PR_NUMBER", help="PR number")
@click.option("--pipeline-version", default=None, help="Pipeline version tag")
@click.option("--timeout", default=300, show_default=True, help="Max seconds to wait for completion")
def run(config, test_set_id, commit_sha, branch, pr_number, pipeline_version, timeout):
    """Execute a full evaluation run and wait for it to complete."""
    from runner.config_loader import ConfigLoader

    loader = ConfigLoader()
    cfg = loader.load(config)

    effective_test_set_id = test_set_id or cfg.test_set_id
    if not effective_test_set_id:
        click.echo("ERROR: No test set ID provided. Set test_set.id in rageval.yaml or use --test-set.")
        sys.exit(1)

    payload = {
        "test_set_id": effective_test_set_id,
        "pipeline_version": pipeline_version or os.getenv("PIPELINE_VERSION"),
        "git_commit_sha": commit_sha,
        "git_branch": branch,
        "git_pr_number": pr_number,
        "triggered_by": "ci",
        "thresholds": cfg.thresholds if cfg.thresholds else None,
        "metrics": cfg.metrics,
    }

    click.echo(f"Triggering evaluation run for test set {effective_test_set_id}...")
    with httpx.Client(base_url=_api_url(cfg), headers=_headers(cfg), timeout=30) as client:
        resp = client.post("/runs", json=payload)
        resp.raise_for_status()
        run_data = resp.json()

    run_id = run_data["id"]
    click.echo(f"Run ID: {run_id}")
    os.environ["EVAL_RUN_ID"] = run_id  # Available to subsequent CI steps

    # Write run ID to a file so subsequent CI steps can pick it up
    with open(".rageval_run_id", "w") as f:
        f.write(run_id)

    # Poll for completion
    click.echo("Waiting for evaluation to complete...")
    deadline = time.time() + timeout
    poll_interval = 5

    with httpx.Client(base_url=_api_url(cfg), headers=_headers(cfg), timeout=10) as client:
        while time.time() < deadline:
            resp = client.get(f"/runs/{run_id}/status")
            resp.raise_for_status()
            status_data = resp.json()
            status = status_data.get("status")
            click.echo(f"  Status: {status}", nl=False)

            if status in ("completed", "failed", "gate_blocked"):
                click.echo()
                break
            click.echo(" ⟳")
            time.sleep(poll_interval)
        else:
            click.echo("\nERROR: Evaluation timed out.")
            sys.exit(1)

    click.echo(f"Run {run_id} completed with status: {status.upper()}")
    overall_passed = status_data.get("overall_passed")
    if overall_passed is False:
        click.echo("Gate BLOCKED — quality threshold not met.")
        sys.exit(1)


@cli.command()
@click.option("--run-id", default=None, help="Run ID (defaults to .rageval_run_id file)")
@click.option("--config", default="rageval.yaml", show_default=True)
@click.option(
    "--fail-on-regression/--no-fail-on-regression",
    default=True,
    show_default=True,
    help="Exit non-zero if gate fails",
)
def gate(run_id, config, fail_on_regression):
    """Check the release gate for a completed evaluation run."""
    from runner.config_loader import ConfigLoader

    if not run_id:
        try:
            with open(".rageval_run_id") as f:
                run_id = f.read().strip()
        except FileNotFoundError:
            click.echo("ERROR: No run ID provided and .rageval_run_id not found.")
            sys.exit(1)

    loader = ConfigLoader()
    cfg = loader.load(config)

    with httpx.Client(base_url=_api_url(cfg), headers=_headers(cfg), timeout=15) as client:
        resp = client.get(f"/metrics/gate/{run_id}")
        resp.raise_for_status()
        decision = resp.json()

    passed = decision.get("passed")
    baseline_id = decision.get("baseline_run_id")

    if passed is True:
        click.echo("Release Gate: APPROVED")
        if baseline_id:
            click.echo(f"  Compared against baseline run {baseline_id}")
        sys.exit(0)
    elif passed is False:
        click.echo("Release Gate: BLOCKED")
        if baseline_id:
            click.echo(f"  Baseline: {baseline_id}")
        for failure in decision.get("metric_failures", []):
            actual = failure.get("actual")
            threshold = failure.get("threshold")
            lo = failure.get("ci_lower")
            hi = failure.get("ci_upper")
            p_value = failure.get("p_value")
            n = failure.get("sample_size") or 0
            parts = [f"  - {failure['metric']}: point={actual:.3f} threshold={threshold:.3f}"]
            if lo is not None and hi is not None:
                parts.append(f"CI[{lo:.3f},{hi:.3f}]")
            if p_value is not None:
                parts.append(f"p={p_value:.3f}")
            if n:
                parts.append(f"n={n}")
            click.echo(" ".join(parts))
            reason = failure.get("reason")
            if reason:
                click.echo(f"      reason: {reason}")
        for failure in decision.get("rule_failures", []):
            click.echo(f"  - Rule violation on case {failure.get('test_case_id')}")
        if fail_on_regression:
            sys.exit(1)
    else:
        click.echo(f"Gate status unknown (run may not be complete): {decision.get('status')}")
        sys.exit(1)


@cli.command()
@click.option("--run-id", default=None, help="Run ID (defaults to .rageval_run_id file)")
@click.option("--config", default="rageval.yaml", show_default=True)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["console", "json"]),
    default="console",
    show_default=True,
)
@click.option("--output", default=None, help="Write JSON output to this file path")
@click.option("--diff/--no-diff", default=True, show_default=True, help="Include regression diff")
def report(run_id, config, output_format, output, diff):
    """Print a structured evaluation report for a completed run."""
    from runner.config_loader import ConfigLoader

    if not run_id:
        try:
            with open(".rageval_run_id") as f:
                run_id = f.read().strip()
        except FileNotFoundError:
            click.echo("ERROR: No run ID provided.")
            sys.exit(1)

    loader = ConfigLoader()
    cfg = loader.load(config)

    with httpx.Client(base_url=_api_url(cfg), headers=_headers(cfg), timeout=15) as client:
        run_resp = client.get(f"/runs/{run_id}")
        run_resp.raise_for_status()
        run_data = run_resp.json()

        results_resp = client.get(f"/results", params={"run_id": run_id, "limit": 500})
        results_resp.raise_for_status()
        results_data = results_resp.json()

        summary_resp = client.get(f"/results/summary", params={"run_id": run_id})
        summary_resp.raise_for_status()
        summary_data = summary_resp.json()

        gate_resp = client.get(f"/metrics/gate/{run_id}")
        gate_resp.raise_for_status()
        gate_data = gate_resp.json()

        diff_data = None
        if diff:
            diff_resp = client.get(f"/runs/{run_id}/diff")
            if diff_resp.status_code == 200:
                diff_data = diff_resp.json()

    report_payload = {
        "run": run_data,
        "results": results_data,
        "summary": summary_data,
        "gate": gate_data,
        "diff": diff_data,
    }

    if output_format == "json":
        from runner.reporters.json_reporter import write_report
        write_report(report_payload, output_path=output)
    else:
        from runner.reporters.console_reporter import print_report
        print_report(report_payload)
        if output:
            from runner.reporters.json_reporter import write_report
            write_report(report_payload, output_path=output)
            click.echo(f"JSON report written to {output}")


@cli.command()
@click.option(
    "--gold", "gold_path", required=True,
    help="JSONL file: {id, query, answer, contexts?, human_score} per line",
)
@click.option(
    "--judge", default="llm_judge", show_default=True,
    type=click.Choice(["llm_judge", "g_eval"]),
    help="Which judge to calibrate",
)
@click.option(
    "--metric-key", default="llm_judge", show_default=True,
    help="Key on MetricScores.scores to compare against human_score",
)
@click.option("--model", default="gpt-4o", show_default=True)
@click.option("--samples", default=1, show_default=True, help="Self-consistency samples")
@click.option("--min-spearman", type=float, default=None,
              help="Fail if Spearman correlation < this (for CI gating)")
def calibrate(gold_path, judge, metric_key, model, samples, min_spearman):
    """Calibrate an LLM judge against a human-labeled gold file.

    Prints Spearman + Kendall correlation and mean absolute error. Intended
    to be re-run after model / prompt changes to detect judge drift."""
    from runner.calibration_harness import calibrate as run_calibration, load_gold

    gold = load_gold(gold_path)
    click.echo(f"Loaded {len(gold)} gold cases from {gold_path}")

    if judge == "llm_judge":
        from runner.evaluators.llm_judge_evaluator import LLMJudgeEvaluator
        evaluator = LLMJudgeEvaluator(model=model, samples=samples)
    else:
        from runner.evaluators.geval_evaluator import GEvalEvaluator
        evaluator = GEvalEvaluator(
            aspect="overall",
            description="accuracy, helpfulness, and groundedness",
            model=model,
            samples=samples,
        )
        metric_key = "g_eval:overall"

    result = run_calibration(evaluator, gold_cases=gold, metric_key=metric_key)

    click.echo(f"n                = {result.n}")
    click.echo(f"spearman         = {result.spearman:.3f}" if result.spearman is not None else "spearman         = n/a")
    click.echo(f"kendall_tau      = {result.kendall:.3f}" if result.kendall is not None else "kendall_tau      = n/a")
    click.echo(f"mean_abs_error   = {result.mean_abs_error:.3f}" if result.mean_abs_error is not None else "mean_abs_error   = n/a")

    if min_spearman is not None and result.spearman is not None and result.spearman < min_spearman:
        click.echo(f"FAIL: Spearman {result.spearman:.3f} < minimum {min_spearman:.3f}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
