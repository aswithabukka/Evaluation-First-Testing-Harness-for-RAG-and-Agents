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
    if passed is True:
        click.echo(f"Release Gate: APPROVED ✓")
        sys.exit(0)
    elif passed is False:
        click.echo(f"Release Gate: BLOCKED ✗")
        for failure in decision.get("metric_failures", []):
            click.echo(
                f"  - {failure['metric']}: {failure['actual']:.3f} < {failure['threshold']:.3f}"
            )
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


if __name__ == "__main__":
    cli()
