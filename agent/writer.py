import os
from openai import OpenAI
from prompts.system import SYSTEM_PROMPT
from prompts.writer import PLAN_WRITER_PROMPT
from agent.context import AgentContext
from agent.executor import _chat_with_retry, _track


def write_plan(
    goal: str,
    context: AgentContext,
    sources: list[str] | None = None,
    resource_urls: list[str] | None = None,
) -> str:
    """Generate the final learning plan from all gathered context."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    numbered_sources = ""
    if sources:
        numbered_sources = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(sources))

    resource_url_block = ""
    if resource_urls:
        resource_url_block = "\n".join(f"- {url}" for url in resource_urls)
    else:
        resource_url_block = "None found — omit all resource rows."

    prompt = PLAN_WRITER_PROMPT.format(
        goal=goal,
        context=context.build_context_string(max_summaries=20),
        sources=numbered_sources if numbered_sources else "No web sources recorded.",
        resource_urls=resource_url_block,
    )

    response = _track(_chat_with_retry(
        client,
        model="gpt-4o",
        max_tokens=8000,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    ))

    return response.choices[0].message.content.strip()
