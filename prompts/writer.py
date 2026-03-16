PLAN_WRITER_PROMPT = """You are writing a personalized learning plan for a candidate based on their career goal.

Goal: {goal}

All research and analysis completed:
{context}

Sources used during research (use these for inline citations):
{sources}

Verified learning resources found during research (use these for the Link column in resource tables):
Each entry is either "Display Name → URL" or a bare URL.
{resource_urls}

═══════════════════════════════════════════════
OUTPUT FORMAT — follow every rule exactly
═══════════════════════════════════════════════

CITATIONS
- Every bullet in Role Requirements Summary MUST end with [n] citing the source it came from
- Each bullet must be grounded in at least one source — do not include requirements you cannot cite
- References section must list every source you cited inline — use the same [n] number
- Only list a source in References if you actually cited it inline — no extras

SPACING
- Put a blank line between the last table row and the next **Skill:** heading or ## heading
- No blank lines between bullets within the same group

SKILL NAMING (Skill Gaps + Learning Plan)
- Skill names MUST be specific and concrete — name the actual technology, framework, method, or concept
- BAD (too vague): "Broaden AI model expertise", "Develop leadership skills", "Enhance business acumen"
- GOOD (specific): "LLM fine-tuning with LoRA / PEFT", "Writing AI product PRDs", "OKR goal-setting for AI teams", "Transformer architecture fundamentals", "A/B testing for ML features"
- Each skill name should be searchable on Coursera or YouTube and return a relevant result
- Aim for 3–4 Critical skills and 3–4 Important skills — no more, no fewer

LEARNING PLAN COVERAGE
- The ## Prioritized Learning Plan section MUST include a **Skill:** block with a resource table for EVERY skill listed under both **Critical** AND **Important** in ## Skill Gaps
- Do NOT skip Important skills — they must each have their own **Skill:** / **Why:** / **Resources:** block with a populated table
- Critical skills come first, then Important skills, in the same section

HYPERLINKS (resource tables)
- Link column in every table MUST use `[Display Name](url)` — NEVER a bare URL
- Prefer resources from the "Verified learning resources" list above — use the Name as display text and the URL as the link
- For "Name → URL" entries, use the Name as the display text: `[Name](URL)`
- For bare URL entries, derive a short display name from the URL path: `[Short Name](URL)`
- You may include 2–4 resources per skill; aim for variety (Coursera course, YouTube video, Medium article)
- Do NOT invent or hallucinate URLs that are not in the verified list

WHAT YOU ALREADY HAVE
- Write 3–5 bullets covering the candidate's existing strengths relevant to this goal
- Each bullet names a specific skill or experience area, followed by a one-line honest assessment
- Use the format: "Skill or experience area — assessment (e.g. already solid / needs updating / transferable)"
- Base every bullet on evidence from the resume — do not invent strengths

NEXT STEPS
- Quick Wins: 3 concrete actions the candidate can take THIS WEEK — specific to their goal and background
  - Each must be actionable in under 1 hour (e.g. enrol in a free module, join a community, update a profile)
- Portfolio Project Ideas: 2 projects specific to this candidate's goal and existing skills
  - Each project must name the technology or method it demonstrates, and explain why it signals readiness for the target role
  - Format: **Project Name:** one-sentence description — why it matters to hiring managers for this role

REFERENCES (the ## References section at the bottom)
- Each entry MUST use the URL from the matching [n] entry in the "Sources used during research" list above
- Format exactly: `- [n] [Source N](url-from-sources-list)` — e.g. `- [1] [Source 1](https://...)`
- Use "Source N" as the link text — do NOT invent article titles you cannot verify
- The URL comes from the Sources list — NOT from the Verified learning resource URLs list
- Do NOT write "← INSERT REAL URL" or any placeholder in References — use the actual URL from Sources

EST. TIME
- Always give a realistic estimate — e.g. "~4 hrs", "2 weeks"
- Never write "n/a"

═══════════════════════════════════════════════
EXAMPLE OUTPUT (follow this structure exactly)
═══════════════════════════════════════════════

## Role Requirements Summary
- AI product strategy and roadmap ownership [2]
- Cross-functional stakeholder alignment [1]
- Prompt engineering and LLM evaluation [3]

## What You Already Have
- Data analysis and SQL — already solid; directly transferable to evaluating model outputs
- Stakeholder communication — present but needs updating for executive-level AI audiences
- Python scripting — basic level; enough to prototype but not to build production pipelines

## Skill Gaps

**Critical** (blockers — must learn)
- Prompt engineering and LLM evaluation (chain-of-thought, few-shot, system prompts)
- AI product roadmapping (PRD writing for ML features, milestone planning with model uncertainty)

**Important** (differentiators — good to have)
- Responsible AI frameworks (fairness, accountability, NIST AI RMF)
- ML pipeline basics (data ingestion, model training, deployment with CI/CD)

## Prioritized Learning Plan

**Skill:** Prompt Engineering and LLM Evaluation
**Why:** Core skill for AI PMs to prototype features and judge model output quality without engineering support.
**Resources:**

| Resource | Description | Link | Est. Time |
|----------|-------------|------|-----------|
| Prompt Engineering for Developers | DeepLearning.AI short course on chain-of-thought, few-shot, and system prompt design. | [Prompt Engineering for Developers](← RESOURCE URL FROM VERIFIED LIST) | ~4 hrs |
| ChatGPT Prompt Engineering Guide | Medium article with real product use-case examples for prompt patterns. | [ChatGPT Prompt Engineering Guide](← RESOURCE URL FROM VERIFIED LIST) | ~1 hr |

**Skill:** AI Product PRD Writing and Roadmapping
**Why:** AI PMs must write PRDs that account for model uncertainty and translate capabilities into concrete milestones.
**Resources:**

| Resource | Description | Link | Est. Time |
|----------|-------------|------|-----------|
| AI Product Management Specialization | Coursera course covering PRD writing, roadmapping, and cross-functional alignment for AI products. | [AI Product Management Specialization](← RESOURCE URL FROM VERIFIED LIST) | ~3 weeks |

**Skill:** Responsible AI Frameworks (NIST AI RMF, Fairness)
**Why:** Fairness and accountability knowledge is increasingly required at senior AI PM levels and in regulated industries.
**Resources:**

| Resource | Description | Link | Est. Time |
|----------|-------------|------|-----------|
| Responsible AI Practices | Google's practical guide to fairness, accountability, and transparency in AI systems. | [Responsible AI Practices](← RESOURCE URL FROM VERIFIED LIST) | ~2 hrs |

**Skill:** ML Pipeline Basics (Training, Evaluation, Deployment)
**Why:** Enables informed conversations with engineers about model training, evaluation metrics, and deployment trade-offs.
**Resources:**

| Resource | Description | Link | Est. Time |
|----------|-------------|------|-----------|
| Machine Learning for Everyone | Beginner-friendly course on how ML models are built, evaluated, and deployed — no coding required. | [Machine Learning for Everyone](← RESOURCE URL FROM VERIFIED LIST) | ~6 hrs |

## Next Steps

### Quick Wins
- Enrol in the free Prompt Engineering for Developers module on DeepLearning.AI (30 min)
- Read "What does an AI PM actually do?" on Lenny's Newsletter and bookmark 3 key frameworks
- Update your LinkedIn headline to include "AI" and message 2 AI PMs for a 15-min informational chat

### Portfolio Project Ideas
- **LLM Output Evaluator:** Build a Python script using the OpenAI API that scores model responses across quality dimensions (accuracy, tone, safety) — demonstrates prompt engineering fluency and evaluation thinking that hiring managers expect from AI PMs
- **AI Feature PRD:** Write a full product requirements document for an AI-powered feature in an app you use, including model uncertainty handling and success metrics — signals you can bridge business requirements and ML constraints

## References
- [1] [Source 1](← URL IS FROM SOURCES[1] ABOVE)
- [2] [Source 2](← URL IS FROM SOURCES[2] ABOVE)
- [3] [Source 3](← URL IS FROM SOURCES[3] ABOVE)

═══════════════════════════════════════════════
END OF EXAMPLE — now write the real plan below
═══════════════════════════════════════════════

Keep it honest, specific, and actionable. Tailor every section to the candidate's actual goal and background — do not copy from the example. Do NOT reproduce any instructions or rules in your output — write only the plan content.
"""
