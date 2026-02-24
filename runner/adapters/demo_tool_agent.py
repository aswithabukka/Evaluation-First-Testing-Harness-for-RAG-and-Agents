"""
DemoToolAgentAdapter — a self-contained tool-use AI agent for demo and testing.

Architecture:
  - Tools:      calculator, get_weather, unit_converter (local), web_search (Google via Serper)
  - Agent:      OpenAI GPT-4o-mini with function calling
  - Flow:       Query → tool calls → tool results → final answer

Local tools work without external services. web_search requires SERPER_API_KEY.
"""
from __future__ import annotations

import json
import math
import os
from typing import Optional

from runner.adapters.base import PipelineOutput, RAGAdapter, ToolCall

# ---------------------------------------------------------------------------
# Tool definitions for OpenAI function calling
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a mathematical expression. Supports basic arithmetic, exponents, sqrt, and common math functions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate, e.g. '2 + 3 * 4' or 'sqrt(144)' or '2**10'",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather conditions for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, e.g. 'London' or 'New York'",
                    },
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unit_converter",
            "description": "Convert a value between measurement units (length, weight, temperature).",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "description": "The numeric value to convert",
                    },
                    "from_unit": {
                        "type": "string",
                        "description": "Source unit, e.g. 'km', 'miles', 'kg', 'lbs', 'celsius', 'fahrenheit'",
                    },
                    "to_unit": {
                        "type": "string",
                        "description": "Target unit, e.g. 'km', 'miles', 'kg', 'lbs', 'celsius', 'fahrenheit'",
                    },
                },
                "required": ["value", "from_unit", "to_unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search Google for real-time information. Use this for current events, news, facts, sports scores, stock prices, or any question that needs up-to-date information from the internet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query, e.g. 'latest news on AI' or 'population of France 2024'",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Local tool implementations
# ---------------------------------------------------------------------------
WEATHER_DATA = {
    "london": {"temp_c": 12, "condition": "Cloudy", "humidity": 78, "wind_kph": 15},
    "new york": {"temp_c": 22, "condition": "Sunny", "humidity": 55, "wind_kph": 10},
    "tokyo": {"temp_c": 28, "condition": "Partly cloudy", "humidity": 65, "wind_kph": 8},
    "paris": {"temp_c": 18, "condition": "Rainy", "humidity": 82, "wind_kph": 20},
    "sydney": {"temp_c": 25, "condition": "Sunny", "humidity": 60, "wind_kph": 12},
    "mumbai": {"temp_c": 33, "condition": "Humid", "humidity": 90, "wind_kph": 5},
    "berlin": {"temp_c": 15, "condition": "Overcast", "humidity": 70, "wind_kph": 18},
    "san francisco": {"temp_c": 16, "condition": "Foggy", "humidity": 85, "wind_kph": 22},
}

UNIT_CONVERSIONS = {
    ("km", "miles"): lambda v: v * 0.621371,
    ("miles", "km"): lambda v: v * 1.60934,
    ("kg", "lbs"): lambda v: v * 2.20462,
    ("lbs", "kg"): lambda v: v / 2.20462,
    ("celsius", "fahrenheit"): lambda v: v * 9 / 5 + 32,
    ("fahrenheit", "celsius"): lambda v: (v - 32) * 5 / 9,
    ("meters", "feet"): lambda v: v * 3.28084,
    ("feet", "meters"): lambda v: v / 3.28084,
    ("cm", "inches"): lambda v: v / 2.54,
    ("inches", "cm"): lambda v: v * 2.54,
    ("liters", "gallons"): lambda v: v * 0.264172,
    ("gallons", "liters"): lambda v: v / 0.264172,
}


def _execute_calculator(args: dict) -> str:
    expression = args.get("expression", "")
    safe_ns = {
        "sqrt": math.sqrt, "abs": abs, "round": round,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "log10": math.log10, "pi": math.pi, "e": math.e,
        "pow": pow, "ceil": math.ceil, "floor": math.floor,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, safe_ns)  # noqa: S307
        return json.dumps({"expression": expression, "result": result})
    except Exception as exc:
        return json.dumps({"expression": expression, "error": str(exc)})


def _execute_get_weather(args: dict) -> str:
    city = args.get("city", "").lower().strip()
    data = WEATHER_DATA.get(city)
    if data:
        return json.dumps({"city": city.title(), **data})

    # Fallback: live web search via Serper API for cities not in the hardcoded list
    api_key = os.environ.get("SERPER_API_KEY", "").strip()
    if api_key:
        try:
            import httpx
            resp = httpx.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": f"current weather in {city}", "num": 3},
                timeout=10.0,
            )
            resp.raise_for_status()
            search_data = resp.json()

            # Extract answer box if available (Google often has weather directly)
            answer_box = search_data.get("answerBox", {})
            if answer_box:
                return json.dumps({
                    "city": city.title(),
                    "source": "web",
                    "weather": answer_box.get("answer", answer_box.get("snippet", "")),
                    "title": answer_box.get("title", ""),
                })

            # Fall back to top snippet
            snippets = []
            for item in search_data.get("organic", [])[:3]:
                snippets.append(item.get("snippet", ""))
            if snippets:
                return json.dumps({
                    "city": city.title(),
                    "source": "web",
                    "weather": " ".join(snippets),
                })
        except Exception:
            pass  # Fall through to error

    return json.dumps({"city": city.title(), "error": f"Weather data not available for '{city}'"})


def _execute_unit_converter(args: dict) -> str:
    value = args.get("value", 0)
    from_unit = args.get("from_unit", "").lower().strip()
    to_unit = args.get("to_unit", "").lower().strip()
    converter = UNIT_CONVERSIONS.get((from_unit, to_unit))
    if converter:
        result = converter(value)
        return json.dumps({
            "input": value, "from": from_unit, "to": to_unit,
            "result": round(result, 4),
        })
    if from_unit == to_unit:
        return json.dumps({"input": value, "from": from_unit, "to": to_unit, "result": value})
    return json.dumps({"error": f"Cannot convert from '{from_unit}' to '{to_unit}'"})


def _execute_web_search(args: dict) -> str:
    query = args.get("query", "").strip()
    if not query:
        return json.dumps({"error": "No search query provided"})

    api_key = os.environ.get("SERPER_API_KEY", "").strip()
    if not api_key:
        return json.dumps({"error": "Web search is not configured (SERPER_API_KEY not set)"})

    try:
        import httpx
        resp = httpx.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 5},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []

        # Include answer box if present
        answer_box = data.get("answerBox", {})
        if answer_box:
            results.append({
                "type": "answer",
                "title": answer_box.get("title", ""),
                "answer": answer_box.get("answer", answer_box.get("snippet", "")),
            })

        # Include knowledge graph if present
        kg = data.get("knowledgeGraph", {})
        if kg:
            results.append({
                "type": "knowledge_graph",
                "title": kg.get("title", ""),
                "description": kg.get("description", ""),
                "attributes": {k: v for k, v in kg.get("attributes", {}).items()},
            })

        # Top organic results
        for item in data.get("organic", [])[:5]:
            results.append({
                "type": "result",
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })

        return json.dumps({"query": query, "results": results})
    except Exception as exc:
        return json.dumps({"query": query, "error": f"Search failed: {exc}"})


TOOL_EXECUTORS = {
    "calculator": _execute_calculator,
    "get_weather": _execute_get_weather,
    "unit_converter": _execute_unit_converter,
    "web_search": _execute_web_search,
}


class DemoToolAgentAdapter(RAGAdapter):
    """
    Self-contained tool-use AI agent for demo / CI evaluation.

    setup() initialises the OpenAI client.
    run()   sends the query with tool definitions, executes any tool calls
            locally, then returns the final answer with tool call records.
    """

    def __init__(self, model: str = "gpt-4o-mini", max_tool_rounds: int = 3):
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self._client = None

    def setup(self) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def run(self, query: str, context: dict) -> PipelineOutput:
        if self._client is None:
            raise RuntimeError("DemoToolAgentAdapter.setup() must be called before run()")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant with access to tools. "
                    "Use the provided tools when the user's question requires "
                    "calculation, weather information, unit conversion, or any "
                    "real-time / factual information from the internet. "
                    "Always use tools rather than guessing when a tool is available. "
                    "Use web_search for current events, news, facts, or anything "
                    "you're not certain about. "
                    "After receiving tool results, provide a clear final answer."
                ),
            },
            {"role": "user", "content": query},
        ]

        all_tool_calls: list[ToolCall] = []
        tool_result_texts: list[str] = []

        for _ in range(self.max_tool_rounds):
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0,
            )
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
                messages.append(choice.message)

                for tc in choice.message.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)

                    executor = TOOL_EXECUTORS.get(fn_name)
                    if executor:
                        result_str = executor(fn_args)
                    else:
                        result_str = json.dumps({"error": f"Unknown tool: {fn_name}"})

                    result_data = json.loads(result_str)
                    all_tool_calls.append(ToolCall(
                        tool=fn_name,
                        args=fn_args,
                        result=result_data,
                    ))
                    tool_result_texts.append(f"[{fn_name}] {result_str}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })
            else:
                # No more tool calls — we have the final answer
                break

        # Extract final answer
        final_response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
        ) if choice.message.content is None else choice
        answer = (
            final_response.choices[0].message.content
            if hasattr(final_response, "choices")
            else choice.message.content
        ) or ""

        return PipelineOutput(
            answer=answer,
            retrieved_contexts=tool_result_texts,
            tool_calls=all_tool_calls,
            metadata={
                "model": self.model,
                "tools_called": [tc.tool for tc in all_tool_calls],
                "tool_call_count": len(all_tool_calls),
            },
        )

    def teardown(self) -> None:
        self._client = None
