"""
Translation Evaluator.

Computes standard machine-translation metrics:

* **SacreBLEU** -- detokenized BLEU using the ``sacrebleu`` library when
  available; falls back to a stdlib implementation.
* **chrF++** -- character n-gram F-score with word n-grams (Popović, 2017).
  Implemented in pure Python following the original paper.
* **COMET** -- neural MT evaluation metric (Rei et al., 2020).  Requires
  ``comet`` and a downloaded model; returns ``None`` when unavailable.
* **TER** -- Translation Edit Rate (Snover et al., 2006).  Minimum edit
  distance normalised by reference length.

Returns:
    {"sacrebleu": float, "chrf_plus_plus": float, "comet": float | None,
     "ter": float}

References:
    - Popović, "chrF++: words helping character n-grams" (WMT 2017)
    - Rei et al., "COMET: A Neural Framework for MT Evaluation" (EMNLP 2020)
    - Snover et al., "A Study of Translation Edit Rate" (AMTA 2006)
    - Post, "A Call for Clarity in Reporting BLEU Scores" (WMT 2018) — SacreBLEU
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranslationResult:
    """Container for translation evaluation scores."""

    sacrebleu: float = 0.0
    chrf_plus_plus: float = 0.0
    comet: float | None = None
    ter: float = 1.0


class TranslationEvaluator:
    """Evaluate machine-translation output against reference translations.

    Args:
        bleu_max_n: Maximum n-gram order for BLEU (default ``4``).
        chrf_char_n: Maximum character n-gram order for chrF++ (default ``6``).
        chrf_word_n: Maximum word n-gram order for chrF++ (default ``2``).
        chrf_beta: Beta parameter for chrF F-score (default ``2.0``).
        comet_model: COMET model name.  Only used when ``comet`` is installed.
    """

    def __init__(
        self,
        bleu_max_n: int = 4,
        chrf_char_n: int = 6,
        chrf_word_n: int = 2,
        chrf_beta: float = 2.0,
        comet_model: str = "Unbabel/wmt22-comet-da",
    ) -> None:
        self._bleu_max_n = bleu_max_n
        self._chrf_char_n = chrf_char_n
        self._chrf_word_n = chrf_word_n
        self._chrf_beta = chrf_beta
        self._comet_model_name = comet_model
        self._comet_model: object | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        hypothesis: str,
        reference: str,
        source: str | None = None,
    ) -> dict:
        """Score a single translation.

        Args:
            hypothesis: System-generated translation.
            reference: Ground-truth reference translation.
            source: Original source text (required for COMET, optional otherwise).

        Returns:
            ``{"sacrebleu": float, "chrf_plus_plus": float,
              "comet": float | None, "ter": float}``
        """
        bleu = self._compute_sacrebleu(hypothesis, reference)
        chrf = self._compute_chrf_plus_plus(hypothesis, reference)
        comet = self._compute_comet(hypothesis, reference, source)
        ter = self._compute_ter(hypothesis, reference)

        return {
            "sacrebleu": bleu,
            "chrf_plus_plus": chrf,
            "comet": comet,
            "ter": ter,
        }

    def evaluate_batch(
        self,
        hypotheses: list[str],
        references: list[str],
        sources: list[str] | None = None,
    ) -> dict:
        """Score a batch and return averaged metrics.

        Args:
            hypotheses: One translation per sample.
            references: One reference per sample (same length).
            sources: Optional source texts (same length).

        Returns:
            ``{"sacrebleu": float, "chrf_plus_plus": float,
              "comet": float | None, "ter": float}``
        """
        if len(hypotheses) != len(references):
            raise ValueError(
                "hypotheses and references must have the same length "
                f"({len(hypotheses)} != {len(references)})"
            )

        if not hypotheses:
            return {"sacrebleu": 0.0, "chrf_plus_plus": 0.0, "comet": None, "ter": 1.0}

        src_list = sources or [None] * len(hypotheses)

        total_bleu = 0.0
        total_chrf = 0.0
        total_ter = 0.0
        comet_scores: list[float] = []

        for hyp, ref, src in zip(hypotheses, references, src_list):
            result = self.evaluate(hyp, ref, src)
            total_bleu += result["sacrebleu"]
            total_chrf += result["chrf_plus_plus"]
            total_ter += result["ter"]
            if result["comet"] is not None:
                comet_scores.append(result["comet"])

        n = len(hypotheses)
        avg_comet: float | None = None
        if comet_scores:
            avg_comet = sum(comet_scores) / len(comet_scores)

        return {
            "sacrebleu": total_bleu / n,
            "chrf_plus_plus": total_chrf / n,
            "comet": avg_comet,
            "ter": total_ter / n,
        }

    # ------------------------------------------------------------------
    # SacreBLEU
    # ------------------------------------------------------------------

    def _compute_sacrebleu(self, hypothesis: str, reference: str) -> float:
        """Use ``sacrebleu`` if available, else fall back to stdlib BLEU."""
        try:
            import sacrebleu

            score = sacrebleu.sentence_bleu(hypothesis, [reference])
            return score.score / 100.0  # Normalise to [0, 1]
        except ImportError:
            return self._stdlib_bleu(hypothesis, reference)

    def _stdlib_bleu(self, hypothesis: str, reference: str) -> float:
        """Pure-Python sentence-level BLEU (no smoothing)."""
        hyp_tokens = hypothesis.lower().split()
        ref_tokens = reference.lower().split()

        if not hyp_tokens or not ref_tokens:
            return 0.0

        precisions: list[float] = []
        for n in range(1, self._bleu_max_n + 1):
            hyp_ngrams = self._make_ngrams(hyp_tokens, n)
            ref_ngrams = self._make_ngrams(ref_tokens, n)
            if not hyp_ngrams:
                precisions.append(0.0)
                continue
            clipped = sum(
                min(count, ref_ngrams.get(ng, 0))
                for ng, count in hyp_ngrams.items()
            )
            precisions.append(clipped / max(sum(hyp_ngrams.values()), 1))

        if any(p == 0.0 for p in precisions):
            return 0.0

        log_avg = sum(math.log(p) for p in precisions) / len(precisions)
        bp = 1.0
        if len(hyp_tokens) < len(ref_tokens):
            bp = math.exp(1.0 - len(ref_tokens) / len(hyp_tokens))

        return bp * math.exp(log_avg)

    # ------------------------------------------------------------------
    # chrF++ (character + word n-gram F-score)
    # ------------------------------------------------------------------

    def _compute_chrf_plus_plus(self, hypothesis: str, reference: str) -> float:
        """chrF++ score: character n-gram F-score augmented with word n-grams.

        Follows Popović (2017).  Beta defaults to 2 (recall-weighted).
        """
        if not hypothesis and not reference:
            return 1.0
        if not hypothesis or not reference:
            return 0.0

        total_precision_num = 0
        total_precision_den = 0
        total_recall_num = 0
        total_recall_den = 0

        # Character n-grams
        for n in range(1, self._chrf_char_n + 1):
            hyp_ng = self._char_ngrams(hypothesis, n)
            ref_ng = self._char_ngrams(reference, n)
            overlap = sum(
                min(hyp_ng[ng], ref_ng[ng]) for ng in hyp_ng if ng in ref_ng
            )
            total_precision_num += overlap
            total_precision_den += max(sum(hyp_ng.values()), 1)
            total_recall_num += overlap
            total_recall_den += max(sum(ref_ng.values()), 1)

        # Word n-grams (the "++" part)
        for n in range(1, self._chrf_word_n + 1):
            hyp_ng = self._make_ngrams(hypothesis.lower().split(), n)
            ref_ng = self._make_ngrams(reference.lower().split(), n)
            overlap = sum(
                min(hyp_ng[ng], ref_ng[ng]) for ng in hyp_ng if ng in ref_ng
            )
            total_precision_num += overlap
            total_precision_den += max(sum(hyp_ng.values()), 1)
            total_recall_num += overlap
            total_recall_den += max(sum(ref_ng.values()), 1)

        precision = total_precision_num / total_precision_den if total_precision_den else 0.0
        recall = total_recall_num / total_recall_den if total_recall_den else 0.0

        beta_sq = self._chrf_beta ** 2
        if precision + recall == 0.0:
            return 0.0
        return (1.0 + beta_sq) * precision * recall / (beta_sq * precision + recall)

    @staticmethod
    def _char_ngrams(text: str, n: int) -> Counter:
        """Extract character n-grams (whitespace is preserved)."""
        return Counter(text[i: i + n] for i in range(len(text) - n + 1))

    @staticmethod
    def _make_ngrams(tokens: list[str], n: int) -> Counter:
        return Counter(tuple(tokens[i: i + n]) for i in range(len(tokens) - n + 1))

    # ------------------------------------------------------------------
    # COMET (neural MT metric)
    # ------------------------------------------------------------------

    def _compute_comet(
        self,
        hypothesis: str,
        reference: str,
        source: str | None,
    ) -> float | None:
        """Compute COMET score.  Returns ``None`` if the library is unavailable."""
        if source is None:
            return None  # COMET requires source text
        try:
            from comet import download_model, load_from_checkpoint

            if self._comet_model is None:
                model_path = download_model(self._comet_model_name)
                self._comet_model = load_from_checkpoint(model_path)

            data = [{"src": source, "mt": hypothesis, "ref": reference}]
            output = self._comet_model.predict(data, batch_size=1, gpus=0)  # type: ignore[union-attr]
            return float(output.scores[0])
        except Exception:
            return None

    # ------------------------------------------------------------------
    # TER (Translation Edit Rate)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_ter(hypothesis: str, reference: str) -> float:
        """Translation Edit Rate: minimum edit distance / reference length.

        Uses word-level Levenshtein distance.  Lower is better (0.0 = perfect).
        """
        hyp_tokens = hypothesis.lower().split()
        ref_tokens = reference.lower().split()

        if not ref_tokens:
            return 0.0 if not hyp_tokens else 1.0

        # Word-level Levenshtein distance
        m, n = len(hyp_tokens), len(ref_tokens)
        dp = list(range(n + 1))
        for i in range(1, m + 1):
            prev = dp[0]
            dp[0] = i
            for j in range(1, n + 1):
                temp = dp[j]
                if hyp_tokens[i - 1] == ref_tokens[j - 1]:
                    dp[j] = prev
                else:
                    dp[j] = 1 + min(prev, dp[j], dp[j - 1])
                prev = temp

        return dp[n] / len(ref_tokens)
