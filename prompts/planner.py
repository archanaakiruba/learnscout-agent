PLANNER_PROMPT = """You are planning a skill gap analysis and learning plan session.

The candidate has described their career goal below. Role requirements have already been researched
from the web and are indexed in a ChromaDB collection named "dynamic_kb" (job postings, skill standards, tech stacks).
The candidate's CV is indexed in a ChromaDB collection named "resume".

Career goal:
{goal}

Generate a structured task plan to analyse the candidate's readiness and produce a personalised learning plan.

Return ONLY a valid JSON array. No explanation, no markdown, just JSON.

Each task object must have:
- "id": integer starting from 1
- "task": clear, specific description of what to research or analyze
- "tool": one of "web_search", "rag_resume", "rag_dynamic", "rag_both", "reason"
  - rag_dynamic: search the "dynamic_kb" collection for role requirements, job posting details, and expected tech stack
  - rag_resume: retrieve the candidate's background, skills, and experience from the "resume" collection
  - rag_both: cross-reference the "resume" collection against the "dynamic_kb" collection to find skill matches and gaps
  - web_search: find specific learning resources, courses, or tools for a named skill gap
  - reason: analyze using already-gathered context (no tool call needed)
- "status": "pending"

Task structure rules:
1. Tasks 1-4 follow a fixed pattern:
   - Task 1: retrieve role requirements from dynamic_kb (rag_dynamic)
   - Task 2: retrieve candidate background from resume (rag_resume)
   - Task 3: cross-reference resume against dynamic_kb to find matches and gaps (rag_both)
   - Task 4: identify and rank critical vs important skill gaps (reason)
2. Tasks 5+ are one web_search task PER skill gap — do NOT bundle multiple skills into one task
   - Each web_search task must name the specific skill in the task description (e.g. "Find learning resources for LLM fine-tuning with LoRA")
   - Generate one task for each Critical gap, then one task for each Important gap
   - Base the skill names on the career goal — you will not know the exact gaps yet, but use reasonable predictions
3. Final task is always tool "reason" — no tool is called, the LLM synthesizes all accumulated findings into the learning plan
4. Aim for 7-9 tasks total (4 analysis + N resource tasks + 1 synthesis)

Example structure for goal "Transition to AI Product Manager at a tech company" (adapt skill names to the actual goal):
[
  {{"id": 1, "task": "Retrieve the required skills, tools, seniority expectations, and must-have qualifications for this role from the dynamic_kb knowledge base", "tool": "rag_dynamic", "status": "pending"}},
  {{"id": 2, "task": "Retrieve the candidate's existing skills, experience, and background from the resume knowledge base", "tool": "rag_resume", "status": "pending"}},
  {{"id": 3, "task": "Cross-reference the candidate's resume skills against the role requirements from dynamic_kb to identify what they already have and what is missing", "tool": "rag_both", "status": "pending"}},
  {{"id": 4, "task": "Identify the 3-4 critical skill gaps and 3-4 important skill gaps based on findings so far, ranked by impact on getting this role", "tool": "reason", "status": "pending"}},
  {{"id": 5, "task": "Find learning resources, courses, and tutorials for Prompt Engineering and LLM Evaluation (chain-of-thought, few-shot, system prompts)", "tool": "web_search", "status": "pending"}},
  {{"id": 6, "task": "Find learning resources, courses, and tutorials for AI Product Roadmapping and PRD writing for ML features", "tool": "web_search", "status": "pending"}},
  {{"id": 7, "task": "Find learning resources, courses, and tutorials for Responsible AI frameworks (NIST AI RMF, fairness, accountability)", "tool": "web_search", "status": "pending"}},
  {{"id": 8, "task": "Find learning resources, courses, and tutorials for ML Pipeline basics (data ingestion, model training, deployment)", "tool": "web_search", "status": "pending"}},
  {{"id": 9, "task": "Synthesize all findings into a prioritized learning plan with concrete next steps", "tool": "reason", "status": "pending"}}
]
"""
