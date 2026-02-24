"""
Similarity Evaluator.

Computes text-similarity metrics for summarization and translation systems:

* **BLEU** -- n-gram precision with brevity penalty (stdlib only).
* **ROUGE-1** -- unigram overlap F1 (Lin, 2004).
* **ROUGE-2** -- bigram overlap F1 (Lin, 2004).
* **ROUGE-L** -- F1 based on the Longest Common Subsequence (LCS).
* **BERTScore** -- token-level cosine similarity using contextual embeddings
  (Zhang et al., 2020).  Requires ``transformers`` and ``torch``; returns
  ``None`` when unavailable.
* **Semantic similarity** -- cosine similarity of OpenAI embeddings when an
  API key is available; ``None`` otherwise.

Returns:
    {"bleu": float, "rouge_1": float, "rouge_2": float, "rouge_l": float,
     "bert_score": float | None, "semantic_similarity": float | None}

References:
    - Lin, "ROUGE: A Package for Automatic Evaluation of Summaries" (2004)
    - Zhang et al., "BERTScore: Evaluating Text Generation with BERT"
      (ICLR 2020, arXiv:1904.09675)
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SimilarityResult:
    """Container for text-similarity scores."""

    bleu: float = 0.0
    rouge_1: float = 0.0
    rouge_2: float = 0.0
    rouge_l: float = 0.0
    bert_score: float | None = None
    semantic_similarity: float | None = None


class SimilarityEvaluator:
    """Evaluate generated text against a reference using surface-level and
    (optionally) semantic similarity metrics.

    Args:
        openai_api_key: If supplied, semantic similarity will be computed
            using the OpenAI Embeddings API.  Otherwise the field is ``None``.
        embedding_model: OpenAI model name for embeddings.
        bleu_max_n: Maximum n-gram order for BLEU (default ``4``).
    """

    def __init__(
        self,
        openai_api_key: str | None = None,
        embedding_model: str = "text-embedding-3-small",
        bleu_max_n: int = 4,
    ) -> None:
        self._openai_api_key = openai_api_key
        self._embedding_model = embedding_model
        self._bleu_max_n = bleu_max_n
        self._client: object | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        predicted: str,
        reference: str,
    ) -> dict:
        """Score *predicted* text against a *reference*.

        Args:
            predicted: System-generated text (hypothesis).
            reference: Ground-truth text.

        Returns:
            ``{"bleu": float, "rouge_1": float, "rouge_2": float,
              "rouge_l": float, "bert_score": float | None,
              "semantic_similarity": float | None}``
        """
        bleu = self._compute_bleu(predicted, reference, self._bleu_max_n)
        rouge_1 = self._compute_rouge_n(predicted, reference, n=1)
        rouge_2 = self._compute_rouge_n(predicted, reference, n=2)
        rouge_l = self._compute_rouge_l(predicted, reference)
        bert = self._compute_bert_score(predicted, reference)
        semantic = self._compute_semantic_similarity(predicted, reference)

        return {
            "bleu": bleu,
            "rouge_1": rouge_1,
            "rouge_2": rouge_2,
            "rouge_l": rouge_l,
            "bert_score": bert,
            "semantic_similarity": semantic,
        }

    def evaluate_batch(
        self,
        predicted_list: list[str],
        reference_list: list[str],
    ) -> dict:
        """Score a batch and return averaged metrics.

        Args:
            predicted_list: One predicted text per sample.
            reference_list: One reference text per sample (same length).

        Returns:
            ``{"bleu": float, "rouge_1": float, "rouge_2": float,
              "rouge_l": float, "bert_score": float | None,
              "semantic_similarity": float | None}``
        """
        if len(predicted_list) != len(reference_list):
            raise ValueError(
                "predicted_list and reference_list must have the same length "
                f"({len(predicted_list)} != {len(reference_list)})"
            )

        if not predicted_list:
            return {
                "bleu": 0.0, "rouge_1": 0.0, "rouge_2": 0.0, "rouge_l": 0.0,
                "bert_score": None, "semantic_similarity": None,
            }

        total_bleu = 0.0
        total_rouge_1 = 0.0
        total_rouge_2 = 0.0
        total_rouge_l = 0.0
        bert_scores: list[float] = []
        semantic_scores: list[float] = []

        for predicted, reference in zip(predicted_list, reference_list):
            result = self.evaluate(predicted, reference)
            total_bleu += result["bleu"]
            total_rouge_1 += result["rouge_1"]
            total_rouge_2 += result["rouge_2"]
            total_rouge_l += result["rouge_l"]
            if result["bert_score"] is not None:
                bert_scores.append(result["bert_score"])
            if result["semantic_similarity"] is not None:
                semantic_scores.append(result["semantic_similarity"])

        n = len(predicted_list)
        avg_bert: float | None = None
        if bert_scores:
            avg_bert = sum(bert_scores) / len(bert_scores)
        avg_semantic: float | None = None
        if semantic_scores:
            avg_semantic = sum(semantic_scores) / len(semantic_scores)

        return {
            "bleu": total_bleu / n,
            "rouge_1": total_rouge_1 / n,
            "rouge_2": total_rouge_2 / n,
            "rouge_l": total_rouge_l / n,
            "bert_score": avg_bert,
            "semantic_similarity": avg_semantic,
        }

    # ------------------------------------------------------------------
    # BLEU (n-gram precision with brevity penalty)
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + lowercasing tokenizer."""
        return text.lower().split()

    @classmethod
    def _ngrams(cls, tokens: list[str], n: int) -> Counter:
        return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))

    @classmethod
    def _compute_bleu(cls, hypothesis: str, reference: str, max_n: int = 4) -> float:
        """Compute a sentence-level BLEU score (no smoothing).

        Implements the original BLEU formula: geometric mean of modified
        n-gram precisions multiplied by a brevity penalty.
        """
        hyp_tokens = cls._tokenize(hypothesis)
        ref_tokens = cls._tokenize(reference)

        if not hyp_tokens or not ref_tokens:
            return 0.0

        # Clipped n-gram precisions
        precisions: list[float] = []
        for n in range(1, max_n + 1):
            hyp_ngrams = cls._ngrams(hyp_tokens, n)
            ref_ngrams = cls._ngrams(ref_tokens, n)
            if not hyp_ngrams:
                precisions.append(0.0)
                continue
            clipped = sum(
                min(count, ref_ngrams.get(ng, 0)) for ng, count in hyp_ngrams.items()
            )
            precisions.append(clipped / max(sum(hyp_ngrams.values()), 1))

        # If any precision is zero, BLEU is zero (log would be -inf)
        if any(p == 0.0 for p in precisions):
            return 0.0

        # Geometric mean of precisions
        log_avg = sum(math.log(p) for p in precisions) / len(precisions)

        # Brevity penalty
        bp = 1.0
        if len(hyp_tokens) < len(ref_tokens):
            bp = math.exp(1.0 - len(ref_tokens) / len(hyp_tokens))

        return bp * math.exp(log_avg)

    # ------------------------------------------------------------------
    # ROUGE-N (n-gram overlap F1)
    # ------------------------------------------------------------------

    @classmethod
    def _compute_rouge_n(cls, hypothesis: str, reference: str, n: int = 1) -> float:
        """Compute ROUGE-N F1 score (unigram for n=1, bigram for n=2, etc.).

        ROUGE-N = F1 of n-gram overlap between hypothesis and reference.
        """
        hyp_tokens = cls._tokenize(hypothesis)
        ref_tokens = cls._tokenize(reference)

        if not hyp_tokens or not ref_tokens:
            return 0.0

        hyp_ngrams = cls._ngrams(hyp_tokens, n)
        ref_ngrams = cls._ngrams(ref_tokens, n)

        if not hyp_ngrams or not ref_ngrams:
            return 0.0

        # Count overlapping n-grams (clipped)
        overlap = 0
        for ng, count in hyp_ngrams.items():
            overlap += min(count, ref_ngrams.get(ng, 0))

        precision = overlap / sum(hyp_ngrams.values())
        recall = overlap / sum(ref_ngrams.values())

        if precision + recall == 0.0:
            return 0.0
        return 2.0 * precision * recall / (precision + recall)

    # ------------------------------------------------------------------
    # ROUGE-L (Longest Common Subsequence)
    # ------------------------------------------------------------------

    @classmethod
    def _lcs_length(cls, seq_a: list[str], seq_b: list[str]) -> int:
        """Length of the Longest Common Subsequence via dynamic programming."""
        m, n = len(seq_a), len(seq_b)
        # Use a space-optimised two-row DP table
        prev = [0] * (n + 1)
        curr = [0] * (n + 1)
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq_a[i - 1] == seq_b[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, [0] * (n + 1)
        return prev[n]

    @classmethod
    def _compute_rouge_l(cls, hypothesis: str, reference: str) -> float:
        """Compute ROUGE-L F1 score based on LCS."""
        hyp_tokens = cls._tokenize(hypothesis)
        ref_tokens = cls._tokenize(reference)

        if not hyp_tokens or not ref_tokens:
            return 0.0

        lcs_len = cls._lcs_length(hyp_tokens, ref_tokens)

        precision = lcs_len / len(hyp_tokens) if hyp_tokens else 0.0
        recall = lcs_len / len(ref_tokens) if ref_tokens else 0.0

        if precision + recall == 0.0:
            return 0.0
        return 2.0 * precision * recall / (precision + recall)

    # ------------------------------------------------------------------
    # Semantic similarity (OpenAI embeddings, optional)
    # ------------------------------------------------------------------

    def _get_client(self) -> object | None:
        """Lazily initialise the OpenAI client."""
        if self._client is not None:
            return self._client
        if self._openai_api_key is None:
            return None
        try:
            import openai

            self._client = openai.OpenAI(api_key=self._openai_api_key)
            return self._client
        except Exception:
            return None

    def _embed(self, text: str) -> list[float] | None:
        """Return the embedding vector for *text*, or ``None`` on failure."""
        client = self._get_client()
        if client is None:
            return None
        try:
            response = client.embeddings.create(  # type: ignore[union-attr]
                model=self._embedding_model,
                input=text,
            )
            return response.data[0].embedding
        except Exception:
            return None

    def _compute_semantic_similarity(
        self, hypothesis: str, reference: str
    ) -> float | None:
        """Cosine similarity between embedding vectors, or ``None``."""
        vec_a = self._embed(hypothesis)
        vec_b = self._embed(reference)
        if vec_a is None or vec_b is None:
            return None
        return self._cosine_similarity(vec_a, vec_b)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ------------------------------------------------------------------
    # BERTScore (Zhang et al., 2020)
    # ------------------------------------------------------------------

    def _compute_bert_score(
        self, hypothesis: str, reference: str
    ) -> float | None:
        """Compute BERTScore F1 using the ``bert_score`` library.

        Returns ``None`` if ``bert_score`` is not installed.  The model is
        loaded lazily on first call.
        """
        try:
            from bert_score import score as bert_score_fn
        except ImportError:
            return None

        try:
            _p, _r, f1 = bert_score_fn(
                [hypothesis],
                [reference],
                lang="en",
                verbose=False,
            )
            return float(f1[0])
        except Exception:
            return None
