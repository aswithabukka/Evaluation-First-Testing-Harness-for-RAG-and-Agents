"""
LLM-as-Judge evaluator (stretch goal).

Uses GPT-4o (or any OpenAI-compatible model) to score open-ended responses
on a 0–1 scale along configurable criteria.
"""


class LLMJudgeEvaluator:
    SYSTEM_PROMPT = """You are an impartial evaluator for AI-generated responses.
Score the given response on the following criteria: {criteria}.

Return ONLY a JSON object with this structure:
{{
  "score": <float 0.0-1.0>,
  "reasoning": "<1-2 sentence explanation>"
}}"""

    def __init__(
        self,
        model: str = "gpt-4o",
        criteria: str = "accuracy, helpfulness, and groundedness",
        openai_api_key: str | None = None,
    ):
        self._model = model
        self._criteria = criteria
        self._openai_api_key = openai_api_key
        self._client = None

    def setup(self) -> None:
        import openai
        self._client = openai.OpenAI(api_key=self._openai_api_key)

    def evaluate(
        self,
        query: str,
        answer: str,
        ground_truth: str | None = None,
        contexts: list[str] | None = None,
    ) -> dict:
        if self._client is None:
            self.setup()

        import json

        context_block = ""
        if contexts:
            context_block = f"\n\nRetrieved Context:\n{chr(10).join(contexts[:3])}"

        ground_truth_block = ""
        if ground_truth:
            ground_truth_block = f"\n\nExpected Answer:\n{ground_truth}"

        user_message = (
            f"Question: {query}"
            f"{context_block}"
            f"{ground_truth_block}"
            f"\n\nActual Answer:\n{answer}"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": self.SYSTEM_PROMPT.format(criteria=self._criteria),
                },
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )

        try:
            result = json.loads(response.choices[0].message.content)
            return {
                "score": float(result.get("score", 0.0)),
                "reasoning": result.get("reasoning", ""),
            }
        except (json.JSONDecodeError, ValueError):
            return {"score": 0.0, "reasoning": "Failed to parse judge response"}
