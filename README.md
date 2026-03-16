# Learnscout

Learnscout is an AI agent that takes a career goal and a CV, researches real job requirements from the web, identifies skill gaps against the candidate's background, and produces a structured, personalised learning plan with validated resource links — built on OpenAI GPT-4o, ChromaDB for local RAG, and DuckDuckGo for free web search, with no agent frameworks.

---

## Agent Loop

Learnscout uses a simple explicit agent loop:

1. Generate a structured task plan from the user goal.
2. Execute tasks sequentially.
3. For each task:
   - decide whether to use a tool (`rag_search`, `web_search`, `web_fetch`)
   - run the tool if required
   - summarise results and store them in `AgentContext`
4. Continue until all tasks are complete.
5. Generate the final learning plan from the collected summaries.

Only compact task summaries are stored in the context to avoid prompt growth.

---

## Architecture — how it works

Learnscout runs a four-phase pipeline on each request:

**Phase 0 — Research (`agent/runner.py: _populate_dynamic_rag`)**
GPT-4o generates 7 targeted search queries from the career goal and any domain context extracted from the CV. DuckDuckGo fetches candidate pages; each is English-checked and indexed into a ChromaDB collection called `dynamic_kb`. The loop retries up to 3 times (widening query scope each attempt) until at least 5 sources are indexed. Job board URLs are filtered out at this stage.

**Phase 1 — Plan (`agent/planner.py`)**
GPT-4o receives the goal and generates a JSON task list of 7–9 tasks: retrieve role requirements from `dynamic_kb`, retrieve the candidate's background from `resume`, cross-reference both, identify skill gaps, then one `web_search` task per gap (Coursera, Udemy, YouTube, Medium), and a final reasoning task.

**Phase 2 — Execute (`agent/executor.py`)**
Each task runs through `execute_task`, which calls GPT-4o with the OpenAI tool-call API. Consecutive `web_search` tasks run in parallel via `ThreadPoolExecutor`. Tool results are truncated to 2000 chars; only the summary is stored in `AgentContext` (`agent/context.py`). A per-platform resource search runs after execution to ensure broad URL coverage.

**Phase 3 — Write plan (`agent/writer.py`)**
`write_plan` calls GPT-4o with all task summaries, indexed source URLs, and the collected resource URL list. The output is post-processed: placeholder rows are stripped, references are rewritten with real DuckDuckGo page titles, and citations are renumbered in order of first use. Every URL in the plan is then HEAD-checked; broken links are replaced via trusted-platform re-search or removed.

**Key files:**

```
app.py                  Streamlit UI — inputs, live agent log, plan display, run metrics
agent/runner.py         Main orchestrator — all four phases, URL validation, output saving
agent/planner.py        Calls GPT-4o to generate the JSON task plan
agent/executor.py       Executes a single task with tool-call loop and token tracking
agent/writer.py         Calls GPT-4o to write the final learning plan
agent/context.py        AgentContext dataclass — stores task summaries between phases
tools/web_search.py     DuckDuckGo search via the ddgs library
tools/web_fetch.py      HTTP fetch + BeautifulSoup text extraction
tools/rag_search.py     ChromaDB index/query wrapper (index_text, rag_search, clear_collection)
tools/file_reader.py    PDF and plain-text CV reader (pypdf)
prompts/system.py       System prompt shared across planner, executor, and writer
prompts/runner.py       Research query generation prompt
prompts/planner.py      Task plan generation prompt
prompts/executor.py     Per-task execution prompt with tool mapping rules
prompts/writer.py       Learning plan writing prompt with output format rules
```

---

## Project structure

```
learning-path-agent/
├── app.py                  Streamlit UI entry point
├── agent/
│   ├── runner.py           Four-phase pipeline orchestrator
│   ├── planner.py          Task plan generation
│   ├── executor.py         Single-task execution with tool-call loop
│   ├── writer.py           Final learning plan generation
│   └── context.py          AgentContext: stores task summaries across phases
├── tools/
│   ├── web_search.py       DuckDuckGo search
│   ├── web_fetch.py        URL fetch and text extraction
│   ├── rag_search.py       ChromaDB indexing and retrieval
│   └── file_reader.py      PDF / TXT CV reader
├── prompts/
│   ├── system.py           Shared system prompt
│   ├── runner.py           Research query prompt
│   ├── planner.py          Task plan prompt
│   ├── executor.py         Task execution prompt
│   └── writer.py           Plan writing prompt
├── outputs/                Learning plans saved here (one folder per run, timestamped)
├── chroma_store/           ChromaDB persistence directory
└── requirements.txt
```

---

## Setup

**Prerequisites:** Python 3.11+, an OpenAI API key.

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set the API key
echo OPENAI_API_KEY=sk-... > .env

# 4. Run the app
streamlit run app.py
```

**Environment variables** (`.env` file in the project root):

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Used for GPT-4o (chat), text-embedding-3-small (ChromaDB), and all token tracking |

---

## Usage

Open the Streamlit UI at `http://localhost:8501`.

- **Career Goal** (text area): describe the target role, e.g. "I want to become a Senior ML Engineer at a top AI company". Good to be specific — include seniority, domain, or industry for better research queries.
- **CV / Resume** (file upload): PDF or plain text. Required for personalised gap analysis. The CV is indexed into the `resume` ChromaDB collection and used to enrich research queries with domain context.

Click **Generate Learning Plan**. The agent log updates in real time. When complete, the plan appears on the right and can be downloaded as PDF (via xhtml2pdf) or Markdown as a fallback (markdown files are also saved)

After each run, the **Run Evaluation** panel shows:
- Sources indexed and fetch failures
- Task completion counts
- URL validation results (valid / replaced / removed)
- Token usage and estimated cost (GPT-4o pricing)
- Phase-by-phase latency

Output is also saved to `outputs/<timestamp>/learning_plan.md`.

---

## Evaluation Strategy

| Dimension | Success Signals |
|---|---|
| **Planning Quality** | Tasks logically ordered; role requirements and resume both retrieved; skill gaps mapped to resource tasks; no duplicate or irrelevant tasks |
| **Research Quality** | ≥5 relevant sources indexed; minimal job-board noise; retry logic improves coverage; sources reflect role requirements |
| **Gap Analysis Quality** | Skill gaps grounded in retrieved evidence; concrete skills instead of vague statements; strong CV results in fewer gaps |
| **Resource Recommendation Quality** | Links resolve successfully; resources match the identified gap; appropriate difficulty level; no duplicates or placeholders |
| **Final Plan Usefulness** | Strengths vs gaps clearly separated; actionable learning path; prioritised steps; claims supported by citations |

---

## Metrics

### Quantitative

| Metric | Purpose |
|---|---|
| Sources indexed per run | Measures research coverage and whether the research phase retrieved enough usable content |
| Search retry count | Indicates whether query generation was strong or required fallback retries |
| Task completion rate | Confirms the execution loop successfully runs all planned tasks |
| Broken-link rate after validation | Measures reliability of recommended learning resources |
| Latency per phase | Helps identify bottlenecks across research, planning, execution, and writing |
| Token usage / cost per run | Tracks efficiency and cost of the system |

### Qualitative

| Dimension | Evaluation |
|---|---|
| Research relevance | Are retrieved sources relevant to the target role and domain? |
| Correctness of skill gaps | Do identified gaps reflect real role requirements rather than generic advice? |
| CV personalisation | Are recommendations grounded in evidence from the candidate's CV? |
| Usefulness of resources | Do recommended links meaningfully help close the skill gap? |
| Clarity of learning plan | Is the final plan structured, prioritised, and actionable? |

---

## Test Strategy

| Test Level | Coverage | Goal |
|---|---|---|
| **Unit Tests** | CV parsing (PDF/TXT), job board filtering, query generation format, URL validation and replacement, citation renumbering | Ensure individual utilities behave correctly |
| **Integration Tests** | search → fetch → index pipeline, planner → executor task handoff, resume + dynamic RAG retrieval, context summary storage, writer formatting and validation | Verify components interact correctly |
| **End-to-End Tests** | career transition scenario, niche domain role, strong CV / low gap case, vague goal case, research failure case | Validate full pipeline behaviour under realistic inputs |

---

## Key design decisions

- **ChromaDB for local RAG**: two persistent collections (`resume`, `dynamic_kb`) are cleared and rebuilt on every run to prevent cross-run contamination. No external vector store needed.
- **DuckDuckGo for free search**: no API key required. The research phase tries year-suffixed queries (2026, 2025) for freshness before falling back to the base query.
- **Job board filtering**: URLs from job boards (Indeed, LinkedIn Jobs, Glassdoor, etc.) are blocked during research — listings may expire.
- **Parallel task execution**: consecutive `web_search` tasks run in a `ThreadPoolExecutor(max_workers=2)`. Logs from worker threads are buffered and flushed to the main thread so Streamlit's session state is not touched from a worker.
- **Source title tracking**: DuckDuckGo result titles are stored alongside URLs during research and used as display text in the References section — so citations read as real page titles, not "Source 1".
- **Three-layer URL reliability**: executor restricts searches to four trusted platforms; the plan writer is instructed to use only verified URLs; post-generation validation HEAD-checks all remaining links and replaces or removes broken ones.
- **No agent framework**: the pipeline is plain Python with the OpenAI SDK. Context management, task routing, parallelism, and retry logic are all explicit — no LangChain or similar abstraction overhead.
