RESEARCH_QUERY_PROMPT = """Generate research queries for the following career goal.

Goal: {goal}

{resume_context}

Return a single JSON object with one key:

"queries" — 7 targeted web search queries covering ALL of these angles:
   - Role definition and day-to-day responsibilities
   - Required hard skills (tools, frameworks, technical knowledge, domain expertise)
   - Required soft skills (leadership, communication, stakeholder management)
   - Seniority expectations — what separates junior from senior in this role
   - How people typically break into this role (backgrounds, transition paths)
   - What employers look for in job postings for this role (hiring criteria, must-haves)
   - Interview preparation and what hiring managers actually test for in this role

Rules for queries:
   - Each query must be specific and distinct — no 5 variations of the same question
   - Do NOT mention specific tools or frameworks — let search results surface those
   - Do NOT add site: restrictions
   - Do NOT include years — freshness is handled separately in the search layer

Return ONLY valid JSON. No explanation, no markdown.

Example format:
{{
  "queries": [
    "<role> job responsibilities day-to-day",
    "<role> required hard skills technical knowledge",
    "<role> soft skills leadership expectations",
    "how to break into <role> career transition backgrounds",
    "senior vs junior <role> seniority expectations",
    "<role> job description requirements what employers look for",
    "<role> interview questions what hiring managers look for"
  ]
}}
"""
