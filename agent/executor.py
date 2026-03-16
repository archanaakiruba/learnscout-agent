import json
import os
import re
import time
import threading
from openai import OpenAI, RateLimitError, APIStatusError
from prompts.system import SYSTEM_PROMPT
from prompts.executor import EXECUTOR_PROMPT
from tools.web_search import web_search
from tools.rag_search import rag_search
from agent.context import AgentContext

# global token counter — accumulated across all calls in a run
_token_lock = threading.Lock()
_token_usage = {"prompt": 0, "completion": 0}


def reset_token_usage():
    """Reset accumulated token counters to zero (call at the start of each run)."""
    with _token_lock:
        _token_usage["prompt"] = 0
        _token_usage["completion"] = 0


def get_token_usage() -> dict:
    """Return a snapshot of accumulated token counts for the current run."""
    with _token_lock:
        return dict(_token_usage)


def _track(response):
    """Record token usage from an OpenAI response and return the response unchanged."""
    if response.usage:
        with _token_lock:
            _token_usage["prompt"] += response.usage.prompt_tokens
            _token_usage["completion"] += response.usage.completion_tokens
    return response


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information about roles, skill requirements, learning resources, and market expectations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Retrieve relevant chunks from a local knowledge base. "
                "Use collection='resume' for the candidate's background and experience. "
                "Use collection='dynamic_kb' for role/company knowledge fetched from the web before this run."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"},
                    "collection": {
                        "type": "string",
                        "enum": ["resume", "dynamic_kb"],
                        "description": "Which knowledge base to search",
                    },
                },
                "required": ["query", "collection"],
            },
        },
    },
]


def _chat_with_retry(client: OpenAI, max_retries: int = 3, **kwargs):
    """Call client.chat.completions.create with exponential backoff on rate-limit / server errors."""
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except (RateLimitError, APIStatusError) as e:
            if attempt == max_retries - 1:
                raise
            if isinstance(e, APIStatusError) and e.status_code < 500:
                raise  # 4xx errors won't fix themselves — don't retry
            wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
            time.sleep(wait)
    raise RuntimeError("Unreachable")


def _dispatch_tool(name: str, inputs: dict) -> str:
    if name == "web_search":
        return web_search(inputs["query"])
    if name == "rag_search":
        return rag_search(inputs["query"], inputs["collection"])
    return f"Unknown tool: {name}"


def _extract_summary(text: str, max_chars: int = 3000) -> str:
    # preferred: explicit SUMMARY: marker
    match = re.search(r"SUMMARY:\s*(.+)", text, re.DOTALL)
    if match:
        return match.group(1).strip()[:max_chars]
    # fallback: last non-empty paragraph (avoids cutting mid-sentence)
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    if paragraphs:
        return paragraphs[-1][:max_chars]
    return text.strip()[:max_chars]


def execute_task(task: dict, context: AgentContext, log_fn=print) -> str:
    """Execute a single task, calling tools as needed, return summary."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    tool_hint = task.get("tool", "reason")
    context_str = context.build_context_string()

    prompt = EXECUTOR_PROMPT.format(
        task=task["task"],
        tool=tool_hint,
        context=context_str if context_str else "No prior context yet.",
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    max_tokens = 3000 if tool_hint == "web_search" else 2000
    max_iterations = 6
    for _ in range(max_iterations):
        response = _track(_chat_with_retry(
            client,
            model="gpt-4o",
            max_tokens=max_tokens,
            temperature=0,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        ))

        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "stop" or not message.tool_calls:
            return _extract_summary(message.content or "")

        messages.append(message)

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            inputs = json.loads(tool_call.function.arguments)
            log_fn(f"  [TOOL] {name}({inputs})")
            result = _dispatch_tool(name, inputs)
            truncated = result[:2000]
            log_fn(f"  [RESULT] {truncated[:200]}...")
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": truncated,
            })

    # iteration limit reached — return whatever the last message contained
    last_content = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""
    return _extract_summary(last_content or "Max tool iterations reached — no summary produced.")
