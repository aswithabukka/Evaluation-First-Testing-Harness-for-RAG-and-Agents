"""
Run reproducibility manifest.

Collects everything needed to replay a run's evaluator decisions:

* Evaluator identities + versions (``name``/``version`` class attrs).
* Library versions for the judge stack (openai, ragas, deepeval, transformers).
* Model IDs + parameters used by each LLM-based evaluator.
* Prompt hashes — so a prompt change is detectable even if the model ID is
  unchanged.
* Seeds — both per-sample seeds (used by LLMClient) and bootstrap seeds (used
  by the gate).
* Env capture — python version, OS, git commit (if available).

The manifest is written into the run's snapshot JSONB field and surfaced in
the UI. When someone debates whether a regression is real or a prompt
change, the manifest tells them.

Usage:
    mf = Manifest()
    mf.record_evaluator(ev)
    mf.record_prompt(model="gpt-4o", system=..., user=..., params=...)
    mf.seal(commit_sha=os.getenv("GITHUB_SHA"))
    run.snapshot["manifest"] = mf.to_dict()
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from dataclasses import dataclass, field

from runner.evaluators._llm import prompt_hash


_TRACKED_LIBS = [
    "openai", "ragas", "deepeval", "datasets", "transformers",
    "presidio_analyzer", "langchain", "llama_index", "jsonschema",
]


@dataclass
class Manifest:
    evaluators: list[dict] = field(default_factory=list)
    prompts: dict[str, dict] = field(default_factory=dict)     # hash -> {model, params, system_sha, user_sha}
    libraries: dict[str, str] = field(default_factory=dict)    # lib_name -> version | "<not-installed>"
    env: dict = field(default_factory=dict)
    seeds: dict = field(default_factory=dict)
    sealed_at: float | None = None
    commit_sha: str | None = None

    # ------------------------------------------------------------------ recording

    def record_evaluator(self, evaluator) -> None:
        name = getattr(evaluator, "name", evaluator.__class__.__name__)
        version = getattr(evaluator, "version", "unknown")
        entry = {"name": name, "version": version, "class": evaluator.__class__.__name__}
        if entry not in self.evaluators:
            self.evaluators.append(entry)

    def record_prompt(
        self, *, model: str, system: str, user: str, params: dict
    ) -> str:
        h = prompt_hash(model, system, user, params)
        if h in self.prompts:
            return h
        self.prompts[h] = {
            "model": model,
            "params": dict(params),
            "system_sha256_16": _sha16(system),
            "user_sha256_16": _sha16(user),
            "system_preview": system[:80],
        }
        return h

    def record_seed(self, name: str, value: int) -> None:
        self.seeds[name] = value

    # ------------------------------------------------------------------ seal

    def seal(self, *, commit_sha: str | None = None) -> None:
        self.libraries = _library_versions()
        self.env = _env_snapshot()
        self.commit_sha = commit_sha or os.getenv("GITHUB_SHA") or os.getenv("GIT_COMMIT")
        self.sealed_at = time.time()

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "sealed_at": self.sealed_at,
            "commit_sha": self.commit_sha,
            "evaluators": self.evaluators,
            "prompts": self.prompts,
            "libraries": self.libraries,
            "env": self.env,
            "seeds": self.seeds,
        }

    def fingerprint(self) -> str:
        """Deterministic hash of the manifest — two runs with the same
        fingerprint should produce the same gate decisions up to LLM
        non-determinism (which seeds + cache should further reduce)."""
        payload = json.dumps(
            {k: v for k, v in self.to_dict().items() if k not in ("sealed_at",)},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- helpers


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _library_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in _TRACKED_LIBS:
        try:
            mod = __import__(name)
            out[name] = getattr(mod, "__version__", "unknown")
        except ImportError:
            out[name] = "<not-installed>"
    return out


def _env_snapshot() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
