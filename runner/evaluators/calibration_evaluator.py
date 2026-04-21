"""
Calibration evaluator — Expected Calibration Error (ECE).

Measures whether a classifier's / agent's reported confidence matches its
actual accuracy. High ECE = "the model says 0.9 confident but is right 60%
of the time" — a silent production failure mode for routing decisions,
content moderation, and gating logic.

Expected input shape is a list of (confidence, correct) tuples. This is a
batch-level evaluator: it returns a single score for the whole batch rather
than per-case (calibration is not a per-case concept).

Metrics:
    ece                  : Expected Calibration Error over M equal-width bins
    max_calibration_gap  : Max bin-level |accuracy - confidence|
    overconfidence_rate  : Fraction of predictions with confidence > accuracy
                           in their bin
    bins                 : Per-bin (confidence, accuracy, count) for UI plotting

Reference:
    Guo, Pleiss, Sun, Weinberger — "On Calibration of Modern Neural Networks"
    (ICML 2017).
"""
from __future__ import annotations

from runner.evaluators.base_evaluator import BaseEvaluator, EvalError, MetricScores


class CalibrationEvaluator(BaseEvaluator):
    name = "calibration"
    version = "1"

    def __init__(self, *, num_bins: int = 10):
        if num_bins < 2:
            raise ValueError("num_bins must be >= 2")
        self._num_bins = num_bins

    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        """Expected shape per case: {"confidence": float, "correct": bool|0|1}.

        Returns one MetricScores per case with the *batch-level* calibration
        fields copied in (so existing aggregation logic keeps working), plus
        a per-case ``confidence`` / ``correct`` in metadata for drilldown.
        """
        confs: list[float] = []
        corrects: list[int] = []
        for tc in test_cases:
            c = tc.get("confidence")
            ok = tc.get("correct")
            if c is None or ok is None:
                continue
            try:
                cf = float(c)
            except (TypeError, ValueError):
                continue
            confs.append(max(0.0, min(1.0, cf)))
            corrects.append(1 if ok else 0)

        if not confs:
            err = EvalError(type="missing_input", message="no (confidence, correct) pairs", retryable=False)
            return [MetricScores(error=err, version=self.version) for _ in test_cases]

        ece, max_gap, over_rate, bin_stats = self._compute(confs, corrects)

        scores = {
            "ece": ece,
            "max_calibration_gap": max_gap,
            "overconfidence_rate": over_rate,
        }
        # Broadcast batch-level scores onto every case (with per-case detail in metadata).
        out: list[MetricScores] = []
        for tc in test_cases:
            out.append(
                MetricScores(
                    scores=scores.copy(),
                    version=self.version,
                    metadata={
                        "bins": bin_stats,
                        "confidence": tc.get("confidence"),
                        "correct": tc.get("correct"),
                    },
                )
            )
        return out

    def _compute(
        self, confs: list[float], corrects: list[int]
    ) -> tuple[float, float, float, list[dict]]:
        n = len(confs)
        bin_edges = [i / self._num_bins for i in range(self._num_bins + 1)]

        ece = 0.0
        max_gap = 0.0
        over_count = 0
        bin_stats: list[dict] = []

        for b in range(self._num_bins):
            lo, hi = bin_edges[b], bin_edges[b + 1]
            # Upper edge inclusive only on the last bin.
            in_bin = [
                i for i, c in enumerate(confs)
                if (lo <= c < hi) or (b == self._num_bins - 1 and c == hi)
            ]
            if not in_bin:
                bin_stats.append({"lo": lo, "hi": hi, "count": 0, "confidence": 0.0, "accuracy": 0.0})
                continue

            bin_conf = sum(confs[i] for i in in_bin) / len(in_bin)
            bin_acc = sum(corrects[i] for i in in_bin) / len(in_bin)
            gap = abs(bin_conf - bin_acc)

            ece += (len(in_bin) / n) * gap
            max_gap = max(max_gap, gap)
            if bin_conf > bin_acc:
                over_count += len(in_bin)

            bin_stats.append({
                "lo": lo, "hi": hi, "count": len(in_bin),
                "confidence": bin_conf, "accuracy": bin_acc,
            })

        return ece, max_gap, over_count / n, bin_stats
