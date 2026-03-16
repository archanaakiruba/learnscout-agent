"""
Main agent runner — orchestrates research → plan → execute → write plan loop.
"""
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from prompts.runner import RESEARCH_QUERY_PROMPT
from agent.planner import generate_plan
from agent.executor import execute_task, reset_token_usage, get_token_usage
from agent.writer import write_plan
from agent.context import AgentContext
from tools.rag_search import index_text, clear_collection, rag_search
from tools.web_search import web_search
from tools.web_fetch import web_fetch
from tools.file_reader import read_file

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────


# job boards — transient listings that expire; not useful as knowledge sources
_JOB_BOARD_DOMAINS = {
    "localjobs.com", "nofluffjobs.com", "indeed.com", "glassdoor.com",
    "linkedin.com/jobs", "monster.com", "ziprecruiter.com", "simplyhired.com",
    "jobs.lever.co", "boards.greenhouse.io", "workable.com/jobs",
}


_MIN_SOURCES = 5       # minimum indexed sources before stopping retries
_MAX_WEB_RETRIES = 3   # max open-web fetch attempts if still below threshold


def _populate_dynamic_rag(goal: str, resume_context: str = "", log_fn=print) -> tuple[int, list[str], dict]:
    """
    Phase 0: Build the dynamic knowledge base before planning starts.

    GPT-4o generates targeted search queries, then DuckDuckGo fetches and indexes
    relevant pages into dynamic_kb. Retries up to _MAX_WEB_RETRIES times if we fall
    below _MIN_SOURCES, raising temperature on each retry so queries vary and surface
    different sources.

    Returns (total_chunks, sources, research_metrics).
    """

    clear_collection("dynamic_kb")
    log_fn("[RESEARCH] Cleared previous dynamic KB.")

    # include resume context when available to make queries domain-specific
    context_block = (
        f"Candidate background (use this to make queries domain-specific — include the industry/domain in your queries):\n{resume_context}"
        if resume_context else ""
    )

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    query_prompt = RESEARCH_QUERY_PROMPT.format(goal=goal, resume_context=context_block)

    fetch_attempted = 0
    fetch_failed = 0
    total_chunks = 0
    sources: list[str] = []
    source_titles: dict[str, str] = {}  # url → page title from DuckDuckGo result
    queries: list[str] = []

    def _fetch_open_web(id_prefix: str, max_per_query: int = 3) -> int:
        """Run each query through DuckDuckGo, fetch candidate pages, and index valid English content."""
        nonlocal fetch_attempted, fetch_failed, total_chunks
        added = 0
        for i, query in enumerate(queries):
            log_fn(f"[RESEARCH] [{i+1}/{len(queries)}] {query}")

            # try 2026 first for freshness, fall back to 2025, then bare query
            candidates: list[tuple[str, str]] = []
            for suffix in [" 2026", " 2025", ""]:
                raw = web_search(query + suffix, max_results=5)
                candidates = []
                for block in raw.split("\n\n"):
                    lines = block.strip().split("\n")
                    if len(lines) >= 2:
                        title = re.sub(r'^\[\d+\]\s*', '', lines[0].strip())
                        url = lines[1].strip()
                        if url.startswith("http"):
                            candidates.append((url, title))
                    if len(candidates) >= 5:
                        break
                if len(candidates) >= 2:
                    log_fn(f"  [SEARCH] {len(candidates)} results with suffix '{suffix.strip()}'")
                    break
                log_fn(f"  [SEARCH] Only {len(candidates)} results with '{suffix.strip()}', trying next...")

            successful = 0
            for j, (url, title) in enumerate(candidates):
                if successful >= max_per_query:
                    break
                if url in sources:
                    continue
                if any(board in url for board in _JOB_BOARD_DOMAINS):
                    log_fn(f"  [SKIP] Job board URL: {url[:70]}")
                    continue
                fetch_attempted += 1
                log_fn(f"  [FETCH] {url[:70]}...")
                content = web_fetch(url)
                if content.startswith("Fetch failed"):
                    fetch_failed += 1
                    log_fn(f"  [SKIP] {content}")
                    continue
                if not _is_english(content):
                    fetch_failed += 1
                    log_fn(f"  [SKIP] Non-English page: {url[:70]}")
                    continue
                chunks = index_text(content, "dynamic_kb", f"{id_prefix}_{i}_{j}")
                if chunks == 0:
                    fetch_failed += 1
                    log_fn(f"  [SKIP] Empty content, nothing indexed.")
                    continue
                total_chunks += chunks
                sources.append(url)
                source_titles[url] = title
                added += 1
                successful += 1
                log_fn(f"  [INDEX] {chunks} chunks — {title[:60]}")
        return added

    # temp=0 on first attempt for best quality; 0.5 on retries for query variety
    attempt = 0

    while len(sources) < _MIN_SOURCES and attempt <= _MAX_WEB_RETRIES:
        temperature = 0 if attempt == 0 else 0.5
        log_fn(f"[RESEARCH] Attempt {attempt+1}/{_MAX_WEB_RETRIES+1} — generating queries (temperature={temperature})...")

        _resp = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=600,
            temperature=temperature,
            messages=[{"role": "user", "content": query_prompt}],
        )
        raw = (_resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            parsed = json.loads(raw)
            queries = parsed.get("queries", [])
        except Exception as _je:
            log_fn(f"[WARN] Failed to parse query JSON ({_je}) — retrying.")
            attempt += 1
            continue
        log_fn(f"[RESEARCH] {len(queries)} queries generated.")

        max_per_query = 3 + attempt  # widens each retry: 3 → 4 → 5 → 6
        new_count = _fetch_open_web(id_prefix=f"web{attempt}", max_per_query=max_per_query)
        log_fn(f"[RESEARCH] Attempt {attempt+1} added {new_count} sources ({len(sources)} total).")
        if len(sources) >= _MIN_SOURCES:
            break

        attempt += 1

    if len(sources) == 0:
        raise ValueError(
            "Learnscout couldn't find any information about this goal after multiple attempts. "
            "Try being more specific — include the industry, domain, or seniority level "
            "(e.g. 'AI Product Manager at a fintech startup' instead of 'product manager')."
        )
    if len(sources) < _MIN_SOURCES:
        log_fn(f"[WARN] Only {len(sources)} sources indexed — plan quality may be limited.")

    log_fn(f"[RESEARCH] Done — {len(sources)} sources / {total_chunks} chunks in knowledge base.")

    research_metrics = {
        "attempted": fetch_attempted,
        "indexed": len(sources),
        "failed": fetch_failed,
        "chunks": total_chunks,
        "source_titles": source_titles,  # url → title; used to label references
    }
    return total_chunks, sources, research_metrics


# ── Phase 0 helpers — used during research to filter fetched content ──────────

def _is_english(text: str, sample_size: int = 1200) -> bool:
    """
    Heuristic: returns True if text appears to be written in English.
    Two-stage check:
      1. Non-ASCII ratio > 20% → likely CJK / Arabic / Cyrillic → reject
      2. Fewer than 2 common English stop-word occurrences → likely non-English → reject
    """
    sample = text[:sample_size].lower()
    if not sample:
        return True  # can't tell — let it through
    non_ascii = sum(1 for c in sample if ord(c) > 127)
    if non_ascii / len(sample) > 0.20:
        return False
    stop_words = ["the ", " is ", " are ", " of ", " to ", " in ", " and ", " for "]
    hits = sum(1 for w in stop_words if w in sample)
    return hits >= 2





# ── Main entry point ─────────────────────────────────────────────────────────

def run(
    goal: str,
    resume_path: str = "",
    log_callback=print,
    on_plan=None,
    on_task_start=None,
    on_task_done=None,
) -> dict:
    """Run the full research → plan → execute → write pipeline and return a dict with 'plan' and 'output_dir'."""

    import time as _time
    reset_token_usage()
    t_total_start = _time.time()

    # buffer all log messages so they can be saved to agent_log.txt after the run
    _log_buffer: list[str] = []
    def log_fn(msg: str):
        _log_buffer.append(str(msg))
        log_callback(msg)

    log_fn(f"[SETUP] Goal: {goal}")

    # index resume first so we can enrich research queries with domain context
    resume_context = ""
    if resume_path:
        log_fn(f"\n[SETUP] Reading resume from {resume_path}...")
        resume_text = read_file(resume_path)
        if resume_text.startswith("Error"):
            log_fn(f"[WARN] {resume_text}")
        else:
            clear_collection("resume")  # wipe previous run's CV chunks
            index_text(resume_text, "resume", "resume")
            log_fn("[SETUP] Resume indexed into RAG.")
            raw_context = rag_search("industry domain background experience sector", "resume", top_k=2)
            if not raw_context.startswith("Collection") and not raw_context.startswith("No relevant"):
                resume_context = raw_context[:500]
                log_fn("[SETUP] Extracted domain context from resume for targeted research.")

    # phase 0: research role requirements from web (enriched with resume domain if available)
    log_fn("\n[RESEARCH] Phase 0: Fetching role requirements from the web...")
    t_research = _time.time()
    total_chunks, sources, research_metrics = _populate_dynamic_rag(goal, resume_context=resume_context, log_fn=log_fn)
    research_ms = int((_time.time() - t_research) * 1000)
    log_fn(f"[RESEARCH] Done — {total_chunks} chunks indexed from {len(sources)} sources.")

    log_fn("\n[PLAN] Generating task plan...")
    plan = generate_plan(goal)

    if on_plan:
        on_plan(plan)

    log_fn(f"[PLAN] {len(plan)} tasks generated:")
    for t in plan:
        log_fn(f"  ○ [{t['id']}] {t['task']} → {t['tool']}")

    # consecutive web_search tasks run in parallel via ThreadPoolExecutor
    context = AgentContext(goal=goal)
    t_exec = _time.time()
    tasks_done = tasks_failed = 0

    _task_log_lock = threading.Lock()

    def _run_task(task, task_log_fn=None):
        nonlocal tasks_done, tasks_failed
        _log = task_log_fn if task_log_fn is not None else log_fn
        _log(f"\n[TASK {task['id']}/{len(plan)}] {task['task']}")
        _log(f"  Tool hint: {task['tool']}")
        try:
            summary = execute_task(task, context, log_fn=_log)
            task["status"] = "done"
            tasks_done += 1
            _log(f"  [DONE] Summary: {summary[:200]}...")
            return task, summary, None
        except Exception as e:
            task["status"] = "failed"
            tasks_failed += 1
            _log(f"  [FAILED] {e}")
            return task, f"Failed: {e}", e

    i = 0
    while i < len(plan):
        task = plan[i]
        # collect ALL consecutive web_search tasks and run them concurrently
        if task["tool"] == "web_search":
            batch = []
            while i < len(plan) and plan[i]["tool"] == "web_search":
                batch.append(plan[i])
                i += 1
            for t in batch:
                t["status"] = "in_progress"
                if on_task_start:
                    on_task_start(t)
            ids = " & ".join(str(t["id"]) for t in batch)
            log_fn(f"\n[PARALLEL] Running tasks {ids} concurrently...")

            # buffer logs from worker threads — Streamlit session context is thread-local
            parallel_buffer: list[str] = []
            buf_lock = threading.Lock()

            def _buffered_log(msg, _buf=parallel_buffer, _lock=buf_lock):
                with _lock:
                    _buf.append(msg)

            with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                futures = {pool.submit(_run_task, t, _buffered_log): t for t in batch}
                _completed = [f.result() for f in as_completed(futures)]
                results = {r[0]["id"]: r for r in _completed}

            # flush buffered logs to the real log_fn on the main thread
            for msg in parallel_buffer:
                log_fn(msg)
            # write results to context in ID order so the plan writer sees them consistently
            for t in sorted(batch, key=lambda x: x["id"]):
                done_task, summary, _ = results[t["id"]]
                context.add_result(done_task["id"], done_task["task"], summary)
                if on_task_done:
                    on_task_done(done_task, summary)
        else:
            task["status"] = "in_progress"
            if on_task_start:
                on_task_start(task)
            done_task, summary, _ = _run_task(task)
            context.add_result(done_task["id"], done_task["task"], summary)
            if on_task_done:
                on_task_done(done_task, summary)
            i += 1

    exec_ms = int((_time.time() - t_exec) * 1000)

    log_fn("\n[WRITE PLAN] Generating learning plan...")
    t_synth = _time.time()
    learning_plan = write_plan(goal, context, sources=sources)
    learning_plan = re.sub(r'\[Task\s+\d+\]', '', learning_plan)
    # enforce skill name + mock URL on every resource table row:
    # scan for **Skill: X** headings and replace all links in the table below with [X](MOCK_URL)
    _MOCK_URL = "https://learn.microsoft.com/en-us/training/career-paths/"
    _current_skill = None
    _fixed_lines = []
    _in_refs = False
    for _line in learning_plan.split('\n'):
        if _line.startswith('## References'):
            _in_refs = True
        _skill_heading = re.match(r'\*\*Skill:\s*(.+?)\*\*', _line)
        if _skill_heading:
            _current_skill = _skill_heading.group(1).strip()
        if not _in_refs and _current_skill and _line.strip().startswith('|'):
            _line = re.sub(r'\[([^\]]+)\]\([^)]+\)', f'[{_current_skill}]({_MOCK_URL})', _line)
        _fixed_lines.append(_line)
    learning_plan = '\n'.join(_fixed_lines)
    # strip table rows that contain prompt placeholder URLs
    learning_plan = re.sub(
        r'^\|[^\n]*(?:EXAMPLE_URL|INSERT REAL URL|RESOURCE URL FROM VERIFIED LIST)[^\n]*\|[ \t]*$',
        '', learning_plan, flags=re.MULTILINE,
    )
    # inject real source URLs into the References section;
    # source_map must use the same list and numbering passed to write_plan(),
    # otherwise the LLM's [n] citations won't align with the right URLs
    from urllib.parse import urlparse as _urlparse

    def _has_meaningful_path(url: str) -> bool:
        # reject root-domain URLs (https://coursera.org/) and locale-only paths (/en-us/, /en/)
        path = _urlparse(url).path.rstrip("/")
        if not path:
            return False
        if re.fullmatch(r'/[a-z]{2}(-[a-zA-Z]{2,4})?', path):
            return False
        return True

    source_titles = research_metrics.pop("source_titles", {})
    source_map = {i + 1: url for i, url in enumerate(sources)}
    # position number → real page title from DuckDuckGo, fallback to "Source N"
    source_title_map = {
        i + 1: source_titles.get(url, f"Source {i + 1}")
        for i, url in enumerate(sources)
    }

    def _fix_ref(m):
        # inject real source URL and title for any reference entry — markdown or plain text
        n = int(m.group(1))
        url = source_map.get(n)
        if not url or not _has_meaningful_path(url):
            return m.group(0)
        title = source_title_map.get(n, f"Source {n}")
        return f"- [{n}] [{title}]({url})"

    # pass 1: fix references that already have markdown link syntax
    learning_plan = re.sub(r'- \[(\d+)\] \[([^\]]+)\]\([^)]*\)', _fix_ref, learning_plan)
    # pass 2: fix plain-text references (no markdown link) — catches "search: …" entries too
    learning_plan = re.sub(r'^- \[(\d+)\] (?!\[)([^\n]+)', _fix_ref, learning_plan, flags=re.MULTILINE)
    # ensure blank line before **Skill:** or any ## heading after a table row
    learning_plan = re.sub(r'(\|[ \t]*)\n(\*\*Skill:)', r'\1\n\n\2', learning_plan)
    learning_plan = re.sub(r'(\|[ \t]*)(\*\*Skill:)', r'\1\n\n\2', learning_plan)
    learning_plan = re.sub(r'(\|[ \t]*)\n(#{1,3}\s)', r'\1\n\n\2', learning_plan)
    # ensure blank lines between Skill/Why/Resources so markdown renders them as separate blocks
    learning_plan = re.sub(r'(\*\*Skill:[^\n]*)\n(\*\*Why:)', r'\1\n\n\2', learning_plan)
    learning_plan = re.sub(r'(\*\*Why:[^\n]*)\n(\*\*Resources:)', r'\1\n\n\2', learning_plan)

    # renumber citations in ascending order of first use in the text
    # e.g. if the LLM cited [3] first, [1] second, [5] third → remap to [1], [2], [3]
    _old_nums = list(dict.fromkeys(int(m) for m in re.findall(r'\[(\d+)\]', learning_plan)))
    if _old_nums != list(range(1, len(_old_nums) + 1)):
        _remap = {old: new for new, old in enumerate(_old_nums, 1)}
        # placeholder prevents double-substitution (e.g. [1]→[2] then [2]→[3])
        def _sub_inline(m):
            return f"[§{_remap.get(int(m.group(1)), int(m.group(1)))}§]"
        learning_plan = re.sub(r'\[(\d+)\]', _sub_inline, learning_plan)
        learning_plan = learning_plan.replace('[§', '[').replace('§]', ']')
        log_fn(f"[QA] Citations renumbered: {_old_nums} → {list(range(1, len(_old_nums)+1))}")

    synth_ms = int((_time.time() - t_synth) * 1000)
    log_fn("[DONE] Learning plan ready.")

    # resources come from curated library — no live URL validation needed
    t_val = _time.time()
    url_metrics = {"total": 0, "trusted": 0, "valid": 0, "replaced": 0,
                   "removed_rows": 0, "resolved": 0, "final_valid": 0, "total_rows": 0}
    val_ms = int((_time.time() - t_val) * 1000)

    # count inline citations in the final plan text
    citation_count = len(re.findall(r'\[\d+\]', learning_plan))
    total_ms = int((_time.time() - t_total_start) * 1000)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "outputs", timestamp))
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "learning_plan.md"), "w", encoding="utf-8") as f:
        f.write(f"# Learning Plan\n**Goal:** {goal}\n\n{learning_plan}")

    with open(os.path.join(out_dir, "agent_log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(_log_buffer))

    log_fn(f"\n[SAVED] Output written to: outputs/{timestamp}/")

    # gpt-4o pricing: $2.50/1M input, $10.00/1M output
    usage = get_token_usage()
    cost = (usage["prompt"] / 1_000_000 * 2.50) + (usage["completion"] / 1_000_000 * 10.00)
    log_fn(
        f"\n[COST] Tokens — input: {usage['prompt']:,} | output: {usage['completion']:,} | "
        f"total: {usage['prompt'] + usage['completion']:,} | est. cost: ${cost:.4f}"
    )
    log_fn(
        f"[LATENCY] Research: {research_ms/1000:.1f}s | Execution: {exec_ms/1000:.1f}s | "
        f"Write plan: {synth_ms/1000:.1f}s | Validation: {val_ms/1000:.1f}s | Total: {total_ms/1000:.1f}s"
    )

    metrics = {
        "research": research_metrics,
        "urls": url_metrics,
        "tasks": {"total": len(plan), "done": tasks_done, "failed": tasks_failed},
        "citations": citation_count,
        "latency_ms": {
            "research": research_ms,
            "execution": exec_ms,
            "synthesis": synth_ms,
            "validation": val_ms,
            "total": total_ms,
        },
    }

    return {
        "plan": learning_plan,
        "goal": goal,
        "output_dir": out_dir,
        "usage": {**usage, "total": usage["prompt"] + usage["completion"], "cost_usd": cost},
        "metrics": metrics,
    }
