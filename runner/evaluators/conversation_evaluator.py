"""
Conversation Evaluator.

Computes metrics for multi-turn chatbot and dialogue systems:

* **Turn-level coherence** -- checks whether consecutive turns form a
  logically coherent exchange using n-gram overlap between the bot response
  and the preceding context.
* **Knowledge retention** -- measures whether the bot recalls facts stated
  earlier in the conversation (entity-level recall across turns).
* **Role adherence** -- checks whether the bot stays in character based on
  a set of required keywords / disallowed keywords defined for the persona.
* **Response relevance** -- n-gram overlap between the bot response and the
  user query (proxy for on-topic responses).
* **Conversation completion** -- whether the bot reached the expected
  conversation goal (final-turn exact or fuzzy match).
* **Average turn quality** -- mean of per-turn coherence + relevance scores.

Returns:
    {"coherence": float, "knowledge_retention": float,
     "role_adherence": float, "response_relevance": float,
     "conversation_completion": float, "avg_turn_quality": float}

References:
    - Mehri & Eskenazi, "USR: An Unsupervised and Reference-Free Evaluation
      Metric for Dialog" (ACL 2020)
    - Li et al., "Acute-Eval: Improved Dialogue Evaluation with Optimized
      Questions and Multi-turn Comparisons" (2019)
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ConversationResult:
    """Container for conversation evaluation scores."""

    coherence: float = 0.0
    knowledge_retention: float = 0.0
    role_adherence: float = 1.0
    response_relevance: float = 0.0
    conversation_completion: float = 0.0
    avg_turn_quality: float = 0.0


@dataclass
class Turn:
    """A single conversation turn."""

    role: str  # "user" or "assistant"
    content: str


class ConversationEvaluator:
    """Evaluate multi-turn conversations for chatbot quality.

    Args:
        required_keywords: Keywords the bot persona MUST use (role adherence).
        disallowed_keywords: Keywords the bot persona must NOT use.
        coherence_n: N-gram order for coherence overlap (default ``2``).
    """

    def __init__(
        self,
        required_keywords: list[str] | None = None,
        disallowed_keywords: list[str] | None = None,
        coherence_n: int = 2,
    ) -> None:
        self._required_keywords = [kw.lower() for kw in (required_keywords or [])]
        self._disallowed_keywords = [kw.lower() for kw in (disallowed_keywords or [])]
        self._coherence_n = coherence_n

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        turns: list[dict[str, str]],
        expected_final_response: str | None = None,
        entities_to_retain: list[str] | None = None,
    ) -> dict:
        """Evaluate a full multi-turn conversation.

        Args:
            turns: List of ``{"role": "user"|"assistant", "content": "..."}``
                dicts representing the conversation.
            expected_final_response: If provided, the last bot response is
                compared to this for conversation-completion scoring.
            entities_to_retain: Facts/entities the bot should remember
                across turns (e.g. user's name, preferences).

        Returns:
            ``{"coherence": float, "knowledge_retention": float,
              "role_adherence": float, "response_relevance": float,
              "conversation_completion": float, "avg_turn_quality": float}``
        """
        parsed = [Turn(role=t["role"], content=t["content"]) for t in turns]

        coherence = self._compute_coherence(parsed)
        retention = self._compute_knowledge_retention(parsed, entities_to_retain or [])
        role = self._compute_role_adherence(parsed)
        relevance = self._compute_response_relevance(parsed)
        completion = self._compute_completion(parsed, expected_final_response)
        avg_quality = (coherence + relevance) / 2.0

        return {
            "coherence": coherence,
            "knowledge_retention": retention,
            "role_adherence": role,
            "response_relevance": relevance,
            "conversation_completion": completion,
            "avg_turn_quality": avg_quality,
        }

    def evaluate_batch(
        self,
        conversations: list[dict],
    ) -> dict:
        """Evaluate multiple conversations and return averaged metrics.

        Args:
            conversations: List of dicts, each with keys ``"turns"``,
                optional ``"expected_final_response"``, optional
                ``"entities_to_retain"``.

        Returns:
            Averaged metric dict.
        """
        if not conversations:
            return {
                "coherence": 0.0, "knowledge_retention": 0.0,
                "role_adherence": 0.0, "response_relevance": 0.0,
                "conversation_completion": 0.0, "avg_turn_quality": 0.0,
            }

        totals: dict[str, float] = {}
        for conv in conversations:
            result = self.evaluate(
                turns=conv["turns"],
                expected_final_response=conv.get("expected_final_response"),
                entities_to_retain=conv.get("entities_to_retain"),
            )
            for k, v in result.items():
                totals[k] = totals.get(k, 0.0) + v

        n = len(conversations)
        return {k: v / n for k, v in totals.items()}

    # ------------------------------------------------------------------
    # Coherence: content-word recall from context into response
    # ------------------------------------------------------------------

    def _compute_coherence(self, turns: list[Turn]) -> float:
        """Measure whether the bot's response addresses the topics raised
        in the preceding context.

        Uses content-word recall: what fraction of the context's key
        (non-stop-word) terms appear in the bot response? This is more
        appropriate than raw n-gram F1 for chatbot evaluation, where the
        bot is *expected* to introduce new information rather than
        parrot the query.
        """
        if len(turns) < 2:
            return 1.0

        scores: list[float] = []
        context_tokens: list[str] = []

        for turn in turns:
            tokens = self._tokenize(turn.content)
            if turn.role == "assistant" and context_tokens:
                recall = self._content_word_recall(context_tokens, tokens)
                scores.append(recall)
            context_tokens.extend(tokens)

        return sum(scores) / len(scores) if scores else 1.0

    # ------------------------------------------------------------------
    # Knowledge retention: entity recall across turns
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_knowledge_retention(
        turns: list[Turn], entities: list[str]
    ) -> float:
        """Check what fraction of required entities the bot mentions."""
        if not entities:
            return 1.0

        bot_text = " ".join(
            t.content.lower() for t in turns if t.role == "assistant"
        )

        found = sum(1 for e in entities if e.lower() in bot_text)
        return found / len(entities)

    # ------------------------------------------------------------------
    # Role adherence: keyword presence/absence
    # ------------------------------------------------------------------

    def _compute_role_adherence(self, turns: list[Turn]) -> float:
        """Score based on required/disallowed keywords in bot responses."""
        bot_text = " ".join(
            t.content.lower() for t in turns if t.role == "assistant"
        )

        if not self._required_keywords and not self._disallowed_keywords:
            return 1.0

        score = 1.0
        total_checks = 0

        # Required keywords
        for kw in self._required_keywords:
            total_checks += 1
            if kw not in bot_text:
                score -= 1.0
        # Disallowed keywords
        for kw in self._disallowed_keywords:
            total_checks += 1
            if kw in bot_text:
                score -= 1.0

        if total_checks == 0:
            return 1.0
        return max(0.0, score / total_checks + (total_checks - 1) / total_checks)

    # ------------------------------------------------------------------
    # Response relevance: content-word recall from query into response
    # ------------------------------------------------------------------

    def _compute_response_relevance(self, turns: list[Turn]) -> float:
        """Measure whether the bot's response is on-topic with respect to
        the user's query.

        Uses content-word recall: what fraction of the query's key terms
        appear in the response? If the user asks about "headphones", the
        response should mention "headphones".
        """
        scores: list[float] = []
        last_user_tokens: list[str] = []

        for turn in turns:
            if turn.role == "user":
                last_user_tokens = self._tokenize(turn.content)
            elif turn.role == "assistant" and last_user_tokens:
                resp_tokens = self._tokenize(turn.content)
                recall = self._content_word_recall(last_user_tokens, resp_tokens)
                scores.append(recall)

        return sum(scores) / len(scores) if scores else 0.0

    # ------------------------------------------------------------------
    # Conversation completion
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_completion(
        turns: list[Turn], expected: str | None
    ) -> float:
        """Check if the final bot response matches the expected outcome."""
        if expected is None:
            return 1.0  # No expectation set

        # Find the last assistant turn
        bot_turns = [t for t in turns if t.role == "assistant"]
        if not bot_turns:
            return 0.0

        last_response = bot_turns[-1].content.strip().lower()
        expected_lower = expected.strip().lower()

        # Exact match
        if last_response == expected_lower:
            return 1.0

        # Fuzzy: check if expected is contained in response
        if expected_lower in last_response:
            return 0.8

        # Token overlap ratio
        resp_tokens = set(last_response.split())
        exp_tokens = set(expected_lower.split())
        if not exp_tokens:
            return 0.0
        overlap = len(resp_tokens & exp_tokens) / len(exp_tokens)
        return min(overlap, 1.0) * 0.6  # Cap at 0.6 for partial overlap

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    _STOP_WORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "must",
        "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
        "its", "they", "them", "their", "this", "that", "these", "those",
        "what", "which", "who", "whom", "when", "where", "why", "how",
        "in", "on", "at", "to", "for", "of", "with", "by", "from", "about",
        "and", "or", "but", "not", "if", "so", "no", "yes", "all", "any",
        "hi", "hello", "hey", "thanks", "thank", "please", "just", "also",
        "very", "too", "only", "more", "most", "some", "than", "then",
        "up", "out", "off", "over", "own", "same", "other", "each", "such",
    })

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())

    @staticmethod
    def _stem_match(w1: str, w2: str) -> bool:
        """Lightweight prefix-based stem matching.

        Handles common morphological variants without requiring NLTK:
        "laptop" ↔ "laptops", "return" ↔ "returning", "recommend" ↔ "recommendation".
        """
        if w1 == w2:
            return True
        if len(w1) > 3 and len(w2) > 3:
            short, long_ = (w1, w2) if len(w1) <= len(w2) else (w2, w1)
            if long_.startswith(short):
                return True
        return False

    @classmethod
    def _content_word_recall(cls, query_tokens: list[str], response_tokens: list[str]) -> float:
        """Fraction of content words in the query that appear in the response.

        This measures whether the response addresses the query's key topics.
        Uses prefix-based stem matching so that "laptop" matches "laptops",
        "return" matches "returning", etc.
        """
        query_content = [t for t in query_tokens if t not in cls._STOP_WORDS and len(t) > 1]
        if not query_content:
            return 1.0
        query_content = list(set(query_content))
        response_list = list(set(response_tokens))
        found = 0
        for w in query_content:
            if any(cls._stem_match(w, rt) for rt in response_list):
                found += 1
        return found / len(query_content)

    @staticmethod
    def _ngram_overlap(
        context_tokens: list[str], response_tokens: list[str], n: int
    ) -> float:
        """F1-based n-gram overlap between context and response."""
        if not context_tokens or not response_tokens:
            return 0.0

        def make_ngrams(tokens: list[str], order: int) -> Counter:
            return Counter(
                tuple(tokens[i: i + order])
                for i in range(len(tokens) - order + 1)
            )

        ctx_ng = make_ngrams(context_tokens, n)
        resp_ng = make_ngrams(response_tokens, n)

        if not ctx_ng or not resp_ng:
            return 0.0

        overlap = sum(
            min(resp_ng[ng], ctx_ng[ng]) for ng in resp_ng if ng in ctx_ng
        )

        precision = overlap / sum(resp_ng.values()) if resp_ng else 0.0
        recall = overlap / sum(ctx_ng.values()) if ctx_ng else 0.0

        if precision + recall == 0.0:
            return 0.0
        return 2.0 * precision * recall / (precision + recall)
