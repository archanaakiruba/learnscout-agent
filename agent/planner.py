import json
import os
from openai import OpenAI
from prompts.system import SYSTEM_PROMPT
from prompts.planner import PLANNER_PROMPT


def generate_plan(goal: str) -> list[dict]:
    """Call OpenAI to generate a structured JSON task plan from the user's goal."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = PLANNER_PROMPT.format(goal=goal)

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Planner returned invalid JSON: {e}\nRaw output: {raw[:300]}") from e
    return plan
