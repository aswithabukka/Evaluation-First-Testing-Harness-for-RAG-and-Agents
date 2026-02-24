"""
Ranking Evaluator.

Computes standard information-retrieval metrics for search and retrieval
systems: NDCG@k, MAP@k, Mean Reciprocal Rank (MRR), Precision@k, and Recall@k.

The evaluator compares a *predicted* ranking of document identifiers against
an *expected* ranking (relevance ordering).

Metrics follow BEIR (Thakur et al., 2021) and TREC conventions:

* **NDCG@k** — Normalised Discounted Cumulative Gain using position-based
  graded relevance.
* **MAP@k** — Mean Average Precision at *k* (binary relevance).
* **MRR** — Reciprocal rank of the first relevant result.
* **Precision@k** — Fraction of top-*k* results that are relevant.
* **Recall@k** — Fraction of relevant documents that appear in top-*k*.

Returns:
    {"ndcg_at_k": float, "map_at_k": float, "mrr": float,
     "precision_at_k": float, "recall_at_k": float}

References:
    - Thakur et al., "BEIR: A Heterogeneous Benchmark for Zero-shot
      Evaluation of Information Retrieval Models" (NeurIPS 2021)
    - Voorhees, "The TREC-8 Question Answering Track Report" (TREC 1999)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class RankingResult:
    """Container for ranking evaluation scores."""

    ndcg_at_k: float = 0.0
    map_at_k: float = 0.0
    mrr: float = 0.0
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0


class RankingEvaluator:
    """Evaluate a predicted document ranking against an expected ranking.

    Args:
        k: Cut-off depth for NDCG@k and Recall@k.  Defaults to ``10``.
    """

    def __init__(self, k: int = 10) -> None:
        self._k = k

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        predicted_ranking: list[str],
        expected_ranking: list[str],
    ) -> dict:
        """Score a single query's result list.

        Args:
            predicted_ranking: Ordered list of document IDs as returned by the
                system (most relevant first).
            expected_ranking: Ordered list of *relevant* document IDs.  Items
                earlier in this list are assumed to have higher relevance
                grades (position-based graded relevance).

        Returns:
            ``{"ndcg_at_k": float, "map_at_k": float, "mrr": float,
              "precision_at_k": float, "recall_at_k": float}``
        """
        relevance_map = self._build_relevance_map(expected_ranking)
        relevant_set = set(expected_ranking)

        ndcg = self._ndcg_at_k(predicted_ranking, relevance_map, self._k)
        map_k = self._average_precision_at_k(predicted_ranking, relevant_set, self._k)
        mrr = self._mrr(predicted_ranking, relevance_map)
        precision = self._precision_at_k(predicted_ranking, relevant_set, self._k)
        recall = self._recall_at_k(predicted_ranking, expected_ranking, self._k)

        return {
            "ndcg_at_k": ndcg,
            "map_at_k": map_k,
            "mrr": mrr,
            "precision_at_k": precision,
            "recall_at_k": recall,
        }

    def evaluate_batch(
        self,
        predicted_rankings: list[list[str]],
        expected_rankings: list[list[str]],
    ) -> dict:
        """Score multiple queries and return macro-averaged metrics.

        Args:
            predicted_rankings: One predicted ranking per query.
            expected_rankings: One expected ranking per query (same length).

        Returns:
            ``{"ndcg_at_k": float, "map_at_k": float, "mrr": float,
              "precision_at_k": float, "recall_at_k": float}``
        """
        if len(predicted_rankings) != len(expected_rankings):
            raise ValueError(
                "predicted_rankings and expected_rankings must have the same "
                f"length ({len(predicted_rankings)} != {len(expected_rankings)})"
            )

        if not predicted_rankings:
            return {
                "ndcg_at_k": 0.0, "map_at_k": 0.0, "mrr": 0.0,
                "precision_at_k": 0.0, "recall_at_k": 0.0,
            }

        total_ndcg = 0.0
        total_map = 0.0
        total_mrr = 0.0
        total_precision = 0.0
        total_recall = 0.0

        for predicted, expected in zip(predicted_rankings, expected_rankings):
            result = self.evaluate(predicted, expected)
            total_ndcg += result["ndcg_at_k"]
            total_map += result["map_at_k"]
            total_mrr += result["mrr"]
            total_precision += result["precision_at_k"]
            total_recall += result["recall_at_k"]

        n = len(predicted_rankings)
        return {
            "ndcg_at_k": total_ndcg / n,
            "map_at_k": total_map / n,
            "mrr": total_mrr / n,
            "precision_at_k": total_precision / n,
            "recall_at_k": total_recall / n,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_relevance_map(expected_ranking: list[str]) -> dict[str, int]:
        """Assign graded relevance scores from position in the expected list.

        The first item receives the highest relevance score (equal to the
        length of the list), the second gets length-1, and so on.  Items not
        present in the expected list have relevance 0.
        """
        n = len(expected_ranking)
        return {doc_id: n - idx for idx, doc_id in enumerate(expected_ranking)}

    @staticmethod
    def _dcg(relevances: list[float], k: int) -> float:
        """Discounted Cumulative Gain at position *k*."""
        total = 0.0
        for i, rel in enumerate(relevances[:k]):
            total += rel / math.log2(i + 2)  # i+2 because rank is 1-indexed
        return total

    def _ndcg_at_k(
        self,
        predicted: list[str],
        relevance_map: dict[str, int],
        k: int,
    ) -> float:
        """Normalised Discounted Cumulative Gain at *k*."""
        predicted_rels = [relevance_map.get(doc, 0) for doc in predicted[:k]]
        ideal_rels = sorted(relevance_map.values(), reverse=True)[:k]

        dcg = self._dcg(predicted_rels, k)
        idcg = self._dcg(ideal_rels, k)

        if idcg == 0.0:
            return 0.0
        return dcg / idcg

    @staticmethod
    def _mrr(predicted: list[str], relevance_map: dict[str, int]) -> float:
        """Mean Reciprocal Rank — reciprocal of the rank of the first relevant
        document in the predicted list."""
        for rank, doc_id in enumerate(predicted, start=1):
            if doc_id in relevance_map:
                return 1.0 / rank
        return 0.0

    @staticmethod
    def _precision_at_k(
        predicted: list[str],
        relevant_set: set[str],
        k: int,
    ) -> float:
        """Fraction of top-*k* results that are relevant."""
        if k == 0:
            return 0.0
        retrieved_at_k = predicted[:k]
        relevant_count = sum(1 for doc in retrieved_at_k if doc in relevant_set)
        return relevant_count / min(k, len(retrieved_at_k)) if retrieved_at_k else 0.0

    @staticmethod
    def _recall_at_k(
        predicted: list[str],
        expected: list[str],
        k: int,
    ) -> float:
        """Fraction of relevant documents that appear in the top-*k* results."""
        if not expected:
            return 0.0
        relevant_set = set(expected)
        retrieved_at_k = set(predicted[:k])
        return len(relevant_set & retrieved_at_k) / len(relevant_set)

    @staticmethod
    def _average_precision_at_k(
        predicted: list[str],
        relevant_set: set[str],
        k: int,
    ) -> float:
        """Average Precision at *k* (binary relevance).

        AP@k = (1 / min(|R|, k)) * sum_{i=1}^{k} P(i) * rel(i)

        where P(i) is precision at cut-off i and rel(i) is 1 if the i-th
        result is relevant.  This follows the TREC convention.
        """
        if not relevant_set:
            return 0.0

        hits = 0
        sum_precisions = 0.0
        for i, doc_id in enumerate(predicted[:k], start=1):
            if doc_id in relevant_set:
                hits += 1
                sum_precisions += hits / i

        denominator = min(len(relevant_set), k)
        return sum_precisions / denominator if denominator > 0 else 0.0
