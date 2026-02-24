"""
Code Evaluator.

Evaluates outputs from code-generation systems using industry-standard metrics:

* **pass@k** -- the HumanEval gold standard (Chen et al., 2021).  Uses the
  unbiased estimator: generate *n* samples, count *c* correct, then
  ``pass@k = 1 - C(n-c, k) / C(n, k)``.
* **Syntax validation** -- checks whether generated Python code compiles
  without errors using the built-in ``compile()`` function.
* **Code-block detection** -- verifies whether the output contains fenced
  code blocks (triple backtick markers).
* **Security scan** -- flags dangerous patterns such as ``eval()``,
  ``exec()``, ``subprocess``, and ``os.system``.

Returns:
    {
        "pass_at_k": float | None,  # None when no test results provided
        "syntax_valid": bool,
        "has_code_block": bool,
        "security_issues": list[str],
        "security_score": float   # 1.0 = clean, 0.0 = many issues
    }

References:
    - Chen et al., "Evaluating Large Language Models Trained on Code"
      (arXiv:2107.03374) — HumanEval, pass@k
    - Liu et al., EvalPlus / HumanEval+ — extended test suites
    - SWE-bench — resolved rate for real GitHub issues
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


# ------------------------------------------------------------------
# Dangerous code patterns
# ------------------------------------------------------------------

@dataclass
class _SecurityPattern:
    """A pattern to look for when scanning generated code."""

    name: str
    pattern: re.Pattern[str]
    description: str


_SECURITY_PATTERNS: list[_SecurityPattern] = [
    _SecurityPattern(
        name="eval",
        pattern=re.compile(r"\beval\s*\("),
        description="Use of eval() can execute arbitrary code",
    ),
    _SecurityPattern(
        name="exec",
        pattern=re.compile(r"\bexec\s*\("),
        description="Use of exec() can execute arbitrary code",
    ),
    _SecurityPattern(
        name="subprocess",
        pattern=re.compile(r"\bsubprocess\b"),
        description="subprocess module can run arbitrary shell commands",
    ),
    _SecurityPattern(
        name="os.system",
        pattern=re.compile(r"\bos\s*\.\s*system\s*\("),
        description="os.system() can run arbitrary shell commands",
    ),
    _SecurityPattern(
        name="os.popen",
        pattern=re.compile(r"\bos\s*\.\s*popen\s*\("),
        description="os.popen() can run arbitrary shell commands",
    ),
    _SecurityPattern(
        name="os.exec",
        pattern=re.compile(r"\bos\s*\.\s*exec[a-z]*\s*\("),
        description="os.exec*() can replace the current process",
    ),
    _SecurityPattern(
        name="__import__",
        pattern=re.compile(r"\b__import__\s*\("),
        description="__import__() can dynamically import arbitrary modules",
    ),
    _SecurityPattern(
        name="compile",
        pattern=re.compile(r"\bcompile\s*\(.*,\s*['\"]exec['\"]"),
        description="compile() with 'exec' mode can prepare arbitrary code",
    ),
    _SecurityPattern(
        name="pickle.loads",
        pattern=re.compile(r"\bpickle\s*\.\s*loads?\s*\("),
        description="Unpickling untrusted data can execute arbitrary code",
    ),
    _SecurityPattern(
        name="marshal.loads",
        pattern=re.compile(r"\bmarshal\s*\.\s*loads?\s*\("),
        description="Unmarshalling untrusted data is unsafe",
    ),
    _SecurityPattern(
        name="ctypes",
        pattern=re.compile(r"\bctypes\b"),
        description="ctypes provides low-level memory access",
    ),
    _SecurityPattern(
        name="shutil.rmtree",
        pattern=re.compile(r"\bshutil\s*\.\s*rmtree\s*\("),
        description="shutil.rmtree() can recursively delete directories",
    ),
    _SecurityPattern(
        name="open_write",
        pattern=re.compile(r"\bopen\s*\(.*['\"]w['\"]"),
        description="Writing to files may overwrite important data",
    ),
]


# Regex to detect fenced code blocks (```...```)
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")

# Regex to extract Python code from fenced code blocks
_PYTHON_BLOCK_RE = re.compile(r"```(?:python|py)?\s*\n([\s\S]*?)```")


@dataclass
class CodeResult:
    """Container for code evaluation scores."""

    pass_at_k: float | None = None
    syntax_valid: bool = False
    has_code_block: bool = False
    security_issues: list[str] = field(default_factory=list)
    security_score: float = 1.0


class CodeEvaluator:
    """Evaluate generated code for syntactic validity, presence of code
    blocks, and security concerns.

    All checks use Python stdlib only.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, output: str, test_results: list[bool] | None = None) -> dict:
        """Analyse a single code-generation output.

        Args:
            output: The full output text from the code-generation system.
                May contain markdown-fenced code blocks.
            test_results: Optional list of boolean test outcomes for this sample.
                When provided alongside ``n`` and ``k``, enables pass@k.

        Returns:
            ``{"pass_at_k": float | None, "syntax_valid": bool,
              "has_code_block": bool, "security_issues": list[str],
              "security_score": float}``
        """
        has_code_block = self._has_code_block(output)
        code = self._extract_code(output)
        syntax_valid = self._check_syntax(code)
        security_issues = self._scan_security(code)
        security_score = self._compute_security_score(security_issues)

        pass_at_k: float | None = None
        if test_results is not None:
            n = len(test_results)
            c = sum(1 for t in test_results if t)
            pass_at_k = self._pass_at_k(n, c, k=1)

        return {
            "pass_at_k": pass_at_k,
            "syntax_valid": syntax_valid,
            "has_code_block": has_code_block,
            "security_issues": security_issues,
            "security_score": security_score,
        }

    def evaluate_pass_at_k(
        self,
        test_results: list[bool],
        k: int = 1,
    ) -> float:
        """Compute pass@k from a flat list of test outcomes.

        This is the main entry-point when you have *n* generated samples for a
        single problem and know which ones pass all unit tests.

        Args:
            test_results: One bool per generated sample (``True`` = all tests pass).
            k: The *k* in pass@k (default ``1``).

        Returns:
            Unbiased pass@k estimate in ``[0.0, 1.0]``.
        """
        n = len(test_results)
        c = sum(1 for t in test_results if t)
        return self._pass_at_k(n, c, k)

    def evaluate_batch(self, outputs: list[str]) -> list[dict]:
        """Evaluate multiple outputs. Returns one result dict per output."""
        return [self.evaluate(output) for output in outputs]

    def evaluate_batch_pass_at_k(
        self,
        problems: list[list[bool]],
        k: int = 1,
    ) -> dict:
        """Compute pass@k averaged over multiple problems (HumanEval-style).

        Args:
            problems: A list where each element is a list of bool test outcomes
                for one problem's *n* generated samples.
            k: The *k* in pass@k.

        Returns:
            ``{"pass_at_k": float, "num_problems": int, "k": int}``
        """
        if not problems:
            return {"pass_at_k": 0.0, "num_problems": 0, "k": k}

        scores = [
            self._pass_at_k(len(results), sum(1 for t in results if t), k)
            for results in problems
        ]
        return {
            "pass_at_k": sum(scores) / len(scores),
            "num_problems": len(problems),
            "k": k,
        }

    # ------------------------------------------------------------------
    # Code-block detection and extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _has_code_block(text: str) -> bool:
        """Return ``True`` if *text* contains at least one fenced code block."""
        return bool(_CODE_BLOCK_RE.search(text))

    @staticmethod
    def _extract_code(text: str) -> str:
        """Extract Python source from fenced code blocks.

        If the text contains fenced blocks, their contents are concatenated.
        Otherwise the entire text is treated as raw code.
        """
        blocks = _PYTHON_BLOCK_RE.findall(text)
        if blocks:
            return "\n\n".join(blocks)
        # Fall back: try generic fenced blocks
        generic_blocks = re.findall(r"```\s*\n([\s\S]*?)```", text)
        if generic_blocks:
            return "\n\n".join(generic_blocks)
        # No fenced blocks -- treat the whole output as code
        return text

    # ------------------------------------------------------------------
    # Syntax validation
    # ------------------------------------------------------------------

    @staticmethod
    def _check_syntax(code: str) -> bool:
        """Return ``True`` if *code* parses as valid Python."""
        try:
            compile(code, "<generated>", "exec")
            return True
        except SyntaxError:
            return False

    # ------------------------------------------------------------------
    # Security scan
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_security(code: str) -> list[str]:
        """Return human-readable descriptions of dangerous patterns found."""
        issues: list[str] = []
        for sp in _SECURITY_PATTERNS:
            if sp.pattern.search(code):
                issues.append(f"{sp.name}: {sp.description}")
        return issues

    @staticmethod
    def _compute_security_score(issues: list[str]) -> float:
        """Map the number of security issues to a 0.0 -- 1.0 score.

        * 0 issues  -> 1.0 (clean)
        * 1 issue   -> 0.7
        * 2 issues  -> 0.4
        * 3 issues  -> 0.2
        * 4+ issues -> 0.0
        """
        scores = {0: 1.0, 1: 0.7, 2: 0.4, 3: 0.2}
        return scores.get(len(issues), 0.0)

    # ------------------------------------------------------------------
    # pass@k — unbiased estimator (Chen et al., 2021)
    # ------------------------------------------------------------------

    @staticmethod
    def _pass_at_k(n: int, c: int, k: int = 1) -> float:
        """Unbiased estimator of pass@k.

        ``pass@k = 1 - C(n-c, k) / C(n, k)``

        where *n* = total samples, *c* = number that pass all tests, *k* = the
        number of attempts allowed.  Uses ``math.comb`` for exact integer
        arithmetic (no floating-point overflow for reasonable n, k).

        Args:
            n: Total number of generated code samples for one problem.
            c: Number of samples that pass all unit tests.
            k: Number of allowed attempts (typically 1, 10, or 100).

        Returns:
            Estimated probability in ``[0.0, 1.0]``.
        """
        if n < k:
            return 0.0
        if c == 0:
            return 0.0
        if c >= n:
            return 1.0
        # 1 - C(n-c, k) / C(n, k)
        return 1.0 - math.comb(n - c, k) / math.comb(n, k)
