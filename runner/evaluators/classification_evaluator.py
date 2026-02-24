"""
Classification Evaluator.

Computes standard classification metrics for classification and
content-moderation systems.  Supports both single-label and multi-label
classification.

Metrics:

* **Precision / Recall / F1** -- per-sample set overlap, macro-averaged.
* **Accuracy** -- exact-match accuracy.
* **Macro / Micro / Weighted F1** -- batch-level F1 variants following
  scikit-learn conventions.
* **AUC-ROC** -- Area Under the ROC Curve for binary or per-class scores
  (requires probability outputs).
* **PR-AUC** -- Area Under the Precision-Recall Curve.
* **Cohen's Kappa** -- inter-rater agreement correcting for chance.

Returns (single sample):
    {"precision": float, "recall": float, "f1": float, "accuracy": float}

Returns (batch):
    {"precision": float, "recall": float, "f1": float, "accuracy": float,
     "macro_f1": float, "micro_f1": float, "weighted_f1": float,
     "cohens_kappa": float,
     "auc_roc": float | None, "pr_auc": float | None}

References:
    - Sokolova & Lapalme, "A systematic analysis of performance measures for
      classification tasks" (IPM 2009)
    - Cohen, "A Coefficient of Agreement for Nominal Scales" (1960)
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClassificationResult:
    """Container for classification evaluation scores."""

    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    accuracy: float = 0.0


class ClassificationEvaluator:
    """Evaluate predicted labels against expected labels.

    Each call to :meth:`evaluate` handles **one** sample.  For batch
    evaluation, call :meth:`evaluate_batch` with parallel lists.

    Labels may be single strings or lists of strings (multi-label).
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        predicted_labels: str | list[str],
        expected_labels: str | list[str],
    ) -> dict:
        """Score a single prediction against the ground truth.

        Args:
            predicted_labels: Predicted label(s).  A bare string is treated as
                a single-element set.
            expected_labels: Ground-truth label(s).

        Returns:
            ``{"precision": float, "recall": float, "f1": float, "accuracy": float}``
        """
        pred_set = self._to_label_set(predicted_labels)
        true_set = self._to_label_set(expected_labels)

        precision = self._precision(pred_set, true_set)
        recall = self._recall(pred_set, true_set)
        f1 = self._f1(precision, recall)
        accuracy = self._exact_match(pred_set, true_set)

        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "accuracy": accuracy,
        }

    def evaluate_batch(
        self,
        predicted_labels_list: list[str | list[str]],
        expected_labels_list: list[str | list[str]],
        predicted_probs: list[float] | None = None,
        true_binary: list[int] | None = None,
    ) -> dict:
        """Score a batch of predictions with comprehensive metrics.

        Args:
            predicted_labels_list: One entry per sample.
            expected_labels_list: One entry per sample (must be same length).
            predicted_probs: Optional probability scores for AUC-ROC / PR-AUC
                (binary classification).  One float per sample.
            true_binary: Optional ground-truth binary labels (0 or 1) for
                AUC-ROC / PR-AUC.  One int per sample.

        Returns:
            ``{"precision": float, "recall": float, "f1": float,
              "accuracy": float, "macro_f1": float, "micro_f1": float,
              "weighted_f1": float, "cohens_kappa": float,
              "auc_roc": float | None, "pr_auc": float | None}``
        """
        if len(predicted_labels_list) != len(expected_labels_list):
            raise ValueError(
                "predicted_labels_list and expected_labels_list must have the "
                f"same length ({len(predicted_labels_list)} != {len(expected_labels_list)})"
            )

        if not predicted_labels_list:
            return {
                "precision": 0.0, "recall": 0.0, "f1": 0.0, "accuracy": 0.0,
                "macro_f1": 0.0, "micro_f1": 0.0, "weighted_f1": 0.0,
                "cohens_kappa": 0.0, "auc_roc": None, "pr_auc": None,
            }

        total_precision = 0.0
        total_recall = 0.0
        total_f1 = 0.0
        total_accuracy = 0.0

        # Collect flattened labels for micro/macro/weighted F1
        all_pred_sets: list[set[str]] = []
        all_true_sets: list[set[str]] = []

        for predicted, expected in zip(predicted_labels_list, expected_labels_list):
            pred_set = self._to_label_set(predicted)
            true_set = self._to_label_set(expected)
            all_pred_sets.append(pred_set)
            all_true_sets.append(true_set)

            p = self._precision(pred_set, true_set)
            r = self._recall(pred_set, true_set)
            f = self._f1(p, r)
            a = self._exact_match(pred_set, true_set)

            total_precision += p
            total_recall += r
            total_f1 += f
            total_accuracy += a

        n = len(predicted_labels_list)
        macro_f1 = self._macro_f1(all_pred_sets, all_true_sets)
        micro_f1 = self._micro_f1(all_pred_sets, all_true_sets)
        weighted_f1 = self._weighted_f1(all_pred_sets, all_true_sets)
        kappa = self._cohens_kappa(all_pred_sets, all_true_sets)

        auc_roc: float | None = None
        pr_auc: float | None = None
        if predicted_probs is not None and true_binary is not None:
            auc_roc = self._auc_roc(predicted_probs, true_binary)
            pr_auc = self._pr_auc(predicted_probs, true_binary)

        return {
            "precision": total_precision / n,
            "recall": total_recall / n,
            "f1": total_f1 / n,
            "accuracy": total_accuracy / n,
            "macro_f1": macro_f1,
            "micro_f1": micro_f1,
            "weighted_f1": weighted_f1,
            "cohens_kappa": kappa,
            "auc_roc": auc_roc,
            "pr_auc": pr_auc,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_label_set(labels: str | list[str]) -> set[str]:
        """Normalise labels into a lowercase set."""
        if isinstance(labels, str):
            return {labels.strip().lower()}
        return {label.strip().lower() for label in labels if label.strip()}

    @staticmethod
    def _precision(predicted: set[str], expected: set[str]) -> float:
        if not predicted:
            return 0.0
        return len(predicted & expected) / len(predicted)

    @staticmethod
    def _recall(predicted: set[str], expected: set[str]) -> float:
        if not expected:
            return 0.0
        return len(predicted & expected) / len(expected)

    @staticmethod
    def _f1(precision: float, recall: float) -> float:
        if precision + recall == 0.0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    @staticmethod
    def _exact_match(predicted: set[str], expected: set[str]) -> float:
        """Return 1.0 when the sets are identical, else 0.0."""
        return 1.0 if predicted == expected else 0.0

    # ------------------------------------------------------------------
    # Macro / Micro / Weighted F1
    # ------------------------------------------------------------------

    @classmethod
    def _macro_f1(
        cls, pred_sets: list[set[str]], true_sets: list[set[str]]
    ) -> float:
        """Macro F1: per-class F1 averaged equally over all classes."""
        all_labels = set()
        for ps, ts in zip(pred_sets, true_sets):
            all_labels |= ps | ts

        if not all_labels:
            return 0.0

        f1_sum = 0.0
        for label in all_labels:
            tp = sum(1 for p, t in zip(pred_sets, true_sets) if label in p and label in t)
            fp = sum(1 for p, t in zip(pred_sets, true_sets) if label in p and label not in t)
            fn = sum(1 for p, t in zip(pred_sets, true_sets) if label not in p and label in t)
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1_sum += cls._f1(prec, rec)

        return f1_sum / len(all_labels)

    @classmethod
    def _micro_f1(
        cls, pred_sets: list[set[str]], true_sets: list[set[str]]
    ) -> float:
        """Micro F1: globally aggregate TP/FP/FN then compute F1."""
        total_tp = 0
        total_fp = 0
        total_fn = 0

        for pred, true in zip(pred_sets, true_sets):
            total_tp += len(pred & true)
            total_fp += len(pred - true)
            total_fn += len(true - pred)

        prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
        return cls._f1(prec, rec)

    @classmethod
    def _weighted_f1(
        cls, pred_sets: list[set[str]], true_sets: list[set[str]]
    ) -> float:
        """Weighted F1: per-class F1 weighted by class support."""
        all_labels = set()
        for ps, ts in zip(pred_sets, true_sets):
            all_labels |= ps | ts

        if not all_labels:
            return 0.0

        total_support = 0
        weighted_sum = 0.0
        for label in all_labels:
            tp = sum(1 for p, t in zip(pred_sets, true_sets) if label in p and label in t)
            fp = sum(1 for p, t in zip(pred_sets, true_sets) if label in p and label not in t)
            fn = sum(1 for p, t in zip(pred_sets, true_sets) if label not in p and label in t)
            support = tp + fn  # number of true instances of this label
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            weighted_sum += cls._f1(prec, rec) * support
            total_support += support

        return weighted_sum / total_support if total_support > 0 else 0.0

    # ------------------------------------------------------------------
    # Cohen's Kappa
    # ------------------------------------------------------------------

    @staticmethod
    def _cohens_kappa(
        pred_sets: list[set[str]], true_sets: list[set[str]]
    ) -> float:
        """Cohen's Kappa for single-label classification.

        For multi-label samples, uses the first label from each set.
        """
        if not pred_sets:
            return 0.0

        # Flatten to single labels for kappa computation
        pred_labels = [sorted(p)[0] if p else "" for p in pred_sets]
        true_labels = [sorted(t)[0] if t else "" for t in true_sets]

        n = len(pred_labels)
        if n == 0:
            return 0.0

        # Observed agreement
        po = sum(1 for p, t in zip(pred_labels, true_labels) if p == t) / n

        # Expected agreement by chance
        all_labels = set(pred_labels) | set(true_labels)
        pe = 0.0
        for label in all_labels:
            p_freq = sum(1 for p in pred_labels if p == label) / n
            t_freq = sum(1 for t in true_labels if t == label) / n
            pe += p_freq * t_freq

        if pe == 1.0:
            return 1.0
        return (po - pe) / (1.0 - pe)

    # ------------------------------------------------------------------
    # AUC-ROC and PR-AUC (binary classification)
    # ------------------------------------------------------------------

    @staticmethod
    def _auc_roc(
        predicted_probs: list[float], true_labels: list[int]
    ) -> float | None:
        """Area Under the ROC Curve using the trapezoidal rule.

        Pure-Python implementation for binary classification.
        """
        if not predicted_probs or not true_labels:
            return None
        if len(predicted_probs) != len(true_labels):
            return None

        # Sort by predicted probability descending
        pairs = sorted(zip(predicted_probs, true_labels), key=lambda x: -x[0])
        total_pos = sum(true_labels)
        total_neg = len(true_labels) - total_pos

        if total_pos == 0 or total_neg == 0:
            return None

        tp = 0
        fp = 0
        prev_fpr = 0.0
        prev_tpr = 0.0
        auc = 0.0

        for _prob, label in pairs:
            if label == 1:
                tp += 1
            else:
                fp += 1
            tpr = tp / total_pos
            fpr = fp / total_neg
            # Trapezoidal rule
            auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2.0
            prev_fpr = fpr
            prev_tpr = tpr

        return auc

    @staticmethod
    def _pr_auc(
        predicted_probs: list[float], true_labels: list[int]
    ) -> float | None:
        """Area Under the Precision-Recall Curve.

        Pure-Python implementation for binary classification.
        """
        if not predicted_probs or not true_labels:
            return None
        if len(predicted_probs) != len(true_labels):
            return None

        total_pos = sum(true_labels)
        if total_pos == 0:
            return None

        # Sort by predicted probability descending
        pairs = sorted(zip(predicted_probs, true_labels), key=lambda x: -x[0])

        tp = 0
        fp = 0
        prev_recall = 0.0
        auc = 0.0

        for _prob, label in pairs:
            if label == 1:
                tp += 1
            else:
                fp += 1
            precision = tp / (tp + fp)
            recall = tp / total_pos
            # Trapezoidal rule
            auc += (recall - prev_recall) * precision
            prev_recall = recall

        return auc
