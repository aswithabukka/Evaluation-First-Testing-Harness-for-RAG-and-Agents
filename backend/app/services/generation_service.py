"""
LLM-powered test case generation service.

Uses OpenAI to generate test cases for a given topic and system type.
"""
import json
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_TYPE_PROMPTS = {
    "rag": (
        "Generate {count} test cases for a RAG (Retrieval-Augmented Generation) system about: {topic}\n\n"
        "Each test case must be a JSON object with:\n"
        '- "query": a realistic user question\n'
        '- "expected_output": the expected answer\n'
        '- "ground_truth": the factual answer from the knowledge base\n'
        '- "context": a list of 1-3 relevant context passages that would be retrieved\n'
        '- "tags": a list of 1-2 relevant tags\n\n'
        "Return a JSON array of test case objects. Only output valid JSON."
    ),
    "agent": (
        "Generate {count} test cases for an AI agent system about: {topic}\n\n"
        "Each test case must be a JSON object with:\n"
        '- "query": a realistic user request that requires tool usage\n'
        '- "expected_output": the expected final answer\n'
        '- "context": an object with "expected_tool_calls" (a list of objects with "name" and optionally "arguments")\n'
        '- "failure_rules": a list like [{{\"type\": \"must_call_tool\", \"tool\": \"tool_name\"}}]\n'
        '- "tags": a list of 1-2 relevant tags\n\n'
        "Return a JSON array of test case objects. Only output valid JSON."
    ),
    "chatbot": (
        "Generate {count} test cases for a chatbot/conversational AI about: {topic}\n\n"
        "Each test case must be a JSON object with:\n"
        '- "query": the initial user message\n'
        '- "expected_output": what the bot should respond with\n'
        '- "conversation_turns": a list of {{\"role\": \"user\"|\"assistant\", \"content\": \"...\"}} objects (2-4 turns)\n'
        '- "tags": a list of 1-2 relevant tags\n\n'
        "Return a JSON array of test case objects. Only output valid JSON."
    ),
    "search": (
        "Generate {count} test cases for a search/retrieval system about: {topic}\n\n"
        "Each test case must be a JSON object with:\n"
        '- "query": a realistic search query\n'
        '- "expected_output": a description of expected top result\n'
        '- "expected_ranking": a list of document IDs (e.g. ["doc-001", "doc-002"]) in order of relevance\n'
        '- "context": a list of document strings like "[doc-001] Title: content..."\n'
        '- "tags": a list of 1-2 relevant tags\n\n'
        "Return a JSON array of test case objects. Only output valid JSON."
    ),
}


class GenerationService:
    """Generate test cases using an LLM."""

    @staticmethod
    def generate_test_cases(
        topic: str,
        count: int = 10,
        system_type: str = "rag",
    ) -> list[dict]:
        """
        Call OpenAI to generate test cases for a given topic.
        Returns a list of test case dicts ready for DB insertion.
        """
        prompt_template = SYSTEM_TYPE_PROMPTS.get(system_type, SYSTEM_TYPE_PROMPTS["rag"])
        prompt = prompt_template.format(count=count, topic=topic)

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.OPENAI_MODEL,
                        "messages": [
                            {"role": "system", "content": "You are a test case generator. Output only valid JSON arrays."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.8,
                        "max_tokens": 4000,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

                # Parse JSON from the response (strip markdown fences if present)
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()

                cases = json.loads(content)
                if not isinstance(cases, list):
                    cases = [cases]

                return cases

        except Exception as exc:
            logger.error(f"LLM test case generation failed: {exc}")
            raise
