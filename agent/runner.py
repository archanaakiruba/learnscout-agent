"""
Main agent runner — orchestrates research → plan → execute → write plan loop.
"""
import json
import os
import re
import threading
import requests
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

_TRUSTED_DOMAINS = {
    # learning platforms (matches executor site: restriction)
    "coursera.org", "udemy.com", "youtube.com", "youtu.be", "medium.com",
    # official docs / vendor sites
    "docs.python.org", "pytorch.org", "tensorflow.org",
    "huggingface.co", "fast.ai", "kaggle.com",
    "developer.mozilla.org", "aws.amazon.com",
    "cloud.google.com", "learn.microsoft.com",
}

_BAD_SUBDOMAINS = re.compile(
    r'https?://(status|music|developers?|help|support|blog|about|press)\.'
)

# job boards — transient listings that expire; not useful as knowledge sources
_JOB_BOARD_DOMAINS = {
    "localjobs.com", "nofluffjobs.com", "indeed.com", "glassdoor.com",
    "linkedin.com/jobs", "monster.com", "ziprecruiter.com", "simplyhired.com",
    "jobs.lever.co", "boards.greenhouse.io", "workable.com/jobs",
}

# trusted platforms used when searching for replacement / fallback resource URLs
_RESOURCE_SITES = "site:coursera.org OR site:udemy.com OR site:youtube.com OR site:medium.com"

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

        parsed = json.loads(raw)
        queries = parsed.get("queries", [])
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


def _is_trusted(url: str) -> bool:
    for domain in _TRUSTED_DOMAINS:
        if domain in url:
            return True
    return False


def _is_trusted_resource(url: str) -> bool:
    """Stricter check — excludes status pages, music.youtube.com, etc."""
    if _BAD_SUBDOMAINS.match(url):
        return False
    return _is_trusted(url)


# ── Phase 4 helpers — URL validation after the plan is written ───────────────

def _find_replacement_url(label: str, log_fn=print) -> str | None:
    """Search trusted platforms for a replacement URL for a broken resource."""
    try:
        results = web_search(f"{label} {_RESOURCE_SITES}", max_results=5)
        for block in results.split("\n\n"):
            lines = block.strip().split("\n")
            if len(lines) >= 2:
                url = lines[1].strip()
                if url.startswith("http") and _is_trusted(url):
                    log_fn(f"  [URL-FIX] Replaced with: {url[:70]}")
                    return url
    except Exception:
        pass
    return None


def _validate_urls(plan_text: str, log_fn=print) -> str:
    """
    Find every URL in markdown link syntax [text](url).
    - Trusted-domain URLs: pass through without checking (stable platforms).
    - All other URLs: HEAD-check. If broken, re-search trusted platforms for
      a replacement. Fall back to 'search: label' only if re-search also fails.
    """
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Learnscout/1.0)"}
    pattern = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')
    checked: dict[str, bool] = {}

    def _check(url: str) -> bool:
        if url in checked:
            return checked[url]
        if _is_trusted(url):
            log_fn(f"  [URL-CHECK] ✓ trusted: {url[:65]}")
            checked[url] = True
            return True
        log_fn(f"  [URL-CHECK] checking: {url[:65]}")
        try:
            r = requests.head(url, timeout=5, allow_redirects=True, headers=HEADERS)
            ok = r.status_code < 400
        except Exception:
            ok = False
        checked[url] = ok
        if not ok:
            log_fn(f"  [URL-CHECK] ✗ broken ({url[:65]})")
        return ok

    total = valid = replaced = fallback = trusted_count = 0

    def _replace(m: re.Match) -> str:
        nonlocal total, valid, replaced, fallback, trusted_count
        label, url = m.group(1), m.group(2)
        total += 1
        if _is_trusted(url):
            trusted_count += 1
        if _check(url):
            valid += 1
            return m.group(0)
        log_fn(f"  [URL-FIX] Broken: {url[:70]}")
        new_url = _find_replacement_url(label, log_fn=log_fn)
        if new_url:
            replaced += 1
            return f"[{label}]({new_url})"
        fallback += 1
        log_fn(f"  [URL-FIX] No replacement found for: {label} — row will be removed")
        return f"search: {label}"  # plain text marker — row stripped in next pass

    fixed = pattern.sub(_replace, plan_text)

    if total:
        log_fn(f"[URL-VALIDATE] {valid}/{total} original URLs valid, {replaced} replaced, {fallback} removed")

    url_metrics = {
        "total": total,
        "trusted": trusted_count,
        "valid": valid,
        "replaced": replaced,
        "removed_rows": fallback,
    }
    return fixed, url_metrics


def _resolve_link_fallbacks(plan_text: str, log_fn=print) -> tuple[str, int, int]:
    """
    Find every resource table row where the Link column is not a real URL:
    - 'search: name'  — plan writer/validator fallback
    - plain text      — LLM wrote resource name instead of URL
    Tries to resolve each with web_search. Removes row if nothing found.
    Returns (fixed_text, resolved_count, removed_count).
    """
    # match 4-column data rows (skip separator rows with ---)
    pattern = re.compile(
        r'^\|(?![\s\-:]+\|)([^|\n]*)\|([^|\n]*)\|\s*([^|\n]+?)\s*\|([^|\n]*)\|\s*$',
        re.MULTILINE,
    )

    resolved = 0
    removed = 0

    def _replace_row(m: re.Match) -> str:
        nonlocal resolved, removed
        col1, col2, link_cell, col4 = (
            m.group(1), m.group(2), m.group(3).strip(), m.group(4)
        )
        # already a real URL or markdown link — nothing to fix
        if link_cell.startswith("http") or link_cell.startswith("["):
            return m.group(0)
        # header row — skip it
        if link_cell.lower() in ("link", "url"):
            return m.group(0)
        # strip 'search: ' prefix if present, use remainder as search term
        search_term = re.sub(r'^search:\s*', '', link_cell).strip()
        if not search_term:
            return m.group(0)
        log_fn(f"  [RESOLVE] Searching for: {search_term[:60]}")
        try:
            results = web_search(f"{search_term} {_RESOURCE_SITES}", max_results=5)
            for block in results.split("\n\n"):
                lines = block.strip().split("\n")
                if len(lines) >= 2:
                    url = lines[1].strip()
                    if url.startswith("http") and _is_trusted(url):
                        log_fn(f"  [RESOLVE] ✓ {url[:70]}")
                        resolved += 1
                        name = col1.strip()
                        return f"|{col1}|{col2}| [{name}]({url}) |{col4}|"
        except Exception:
            pass
        log_fn(f"  [RESOLVE] ✗ No URL found — row removed")
        removed += 1
        return ""

    cleaned = pattern.sub(_replace_row, plan_text)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    if resolved or removed:
        log_fn(f"[RESOLVE] {resolved} resolved with real URL, {removed} row(s) removed")
    return cleaned, resolved, removed


# ── Main entry point ─────────────────────────────────────────────────────────

def run(
    goal: str,
    resume_path: str = "",
    log_fn=print,
    on_plan=None,
    on_task_start=None,
    on_task_done=None,
) -> dict:
    """Run the full research → plan → execute → write pipeline and return a dict with 'plan' and 'output_dir'."""

    import time as _time
    reset_token_usage()
    t_total_start = _time.time()
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
        # batch consecutive web_search tasks to run them concurrently
        if (
            task["tool"] == "web_search"
            and i + 1 < len(plan)
            and plan[i + 1]["tool"] == "web_search"
        ):
            pair = [task, plan[i + 1]]
            for t in pair:
                t["status"] = "in_progress"
                if on_task_start:
                    on_task_start(t)
            log_fn(f"\n[PARALLEL] Running tasks {pair[0]['id']} & {pair[1]['id']} concurrently...")

            # buffer logs from worker threads — Streamlit session context is thread-local
            parallel_buffer: list[str] = []
            buf_lock = threading.Lock()

            def _buffered_log(msg, _buf=parallel_buffer, _lock=buf_lock):
                with _lock:
                    _buf.append(msg)

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {pool.submit(_run_task, t, _buffered_log): t for t in pair}
                _completed = [f.result() for f in as_completed(futures)]
                results = {r[0]["id"]: r for r in _completed}

            # flush buffered logs to the real log_fn on the main thread
            for msg in parallel_buffer:
                log_fn(msg)
            # write results to context in ID order so the plan writer sees them consistently
            for t in sorted(pair, key=lambda x: x["id"]):
                done_task, summary, _ = results[t["id"]]
                context.add_result(done_task["id"], done_task["task"], summary)
                if on_task_done:
                    on_task_done(done_task, summary)
            i += 2
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

    # build structured resource items: {name, url} pairs so the plan writer gets
    # display names, not just bare URLs it can't map to resources
    _resource_item_pattern = re.compile(r'[•\-]\s*([^|\n]{3,80}?)\s*\|\s*(https?://[^\s|,)]+)')
    _url_pattern = re.compile(r'https?://\S+')
    _seen_urls: set[str] = set()
    resource_items: list[dict] = []

    def _add_item(name: str, url: str):
        url = url.rstrip('.,)')
        if _is_trusted_resource(url) and url not in _seen_urls:
            resource_items.append({"name": name.strip(), "url": url})
            _seen_urls.add(url)

    # extract structured name|url pairs; executor formats them as "• Name | URL | desc"
    for result in context.summaries:
        for m in _resource_item_pattern.finditer(result.summary):
            _add_item(m.group(1), m.group(2))
        # also capture bare URLs that didn't match the structured pattern
        for _url in _url_pattern.findall(result.summary):
            _add_item("", _url)
    log_fn(f"[WRITE PLAN] {len(resource_items)} resource items after executor summaries.")

    # always run per-platform search — ensures Coursera/Udemy/YouTube coverage for all skills
    log_fn("[WRITE PLAN] Running per-platform resource search...")
    _platforms = [
        ("coursera.org", f"{goal} course"),
        ("coursera.org", f"{goal} skills specialization"),
        ("udemy.com",    f"{goal} course tutorial"),
        ("udemy.com",    f"{goal} beginner complete course"),
        ("youtube.com",  f"{goal} tutorial learn"),
        ("youtube.com",  f"{goal} skills explained"),
        ("medium.com",   f"{goal} guide article"),
        ("medium.com",   f"{goal} skills how to"),
    ]
    for _domain, _q in _platforms:
        _results = web_search(f"{_q} site:{_domain}", max_results=4, include_domains=[_domain])
        for _block in _results.split("\n\n"):
            _lines = _block.strip().split("\n")
            if len(_lines) >= 2:
                _title = _lines[0].strip()
                _url = _lines[1].strip()
                if _url.startswith("http") and _domain in _url and _url not in _seen_urls:
                    _add_item(_title, _url)
                    log_fn(f"  [RESOURCE] {_domain}: {_title[:45]}")
    log_fn(f"[WRITE PLAN] Final: {len(resource_items)} resource items.")

    # format resource items for the plan writer prompt: "Name → URL" or bare URL
    resource_urls = [
        f"{item['name']} → {item['url']}" if item['name'] else item['url']
        for item in resource_items
    ]

    log_fn("\n[WRITE PLAN] Generating learning plan...")
    t_synth = _time.time()
    learning_plan = write_plan(goal, context, sources=sources, resource_urls=resource_urls)
    learning_plan = re.sub(r'\[Task\s+\d+\]', '', learning_plan)
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
        # replace both the URL and the title in `- [n] [any-title](any-url)`
        # with the real indexed source URL and its actual page title
        n = int(m.group(1))
        url = source_map.get(n)
        if not url or not _has_meaningful_path(url):
            return m.group(0)
        title = source_title_map.get(n, f"Source {n}")
        return f"- [{n}] [{title}]({url})"

    def _fix_plain_ref(m):
        # convert `- [n] plain text` into a proper markdown link using real title
        n = int(m.group(1))
        url = source_map.get(n)
        if not url or not _has_meaningful_path(url):
            return m.group(0)
        title = source_title_map.get(n, f"Source {n}")
        return f"- [{n}] [{title}]({url})"

    # pass 1: fix references that already have markdown link syntax
    learning_plan = re.sub(r'- \[(\d+)\] \[([^\]]+)\]\([^)]*\)', _fix_ref, learning_plan)
    # pass 2: fix plain-text references (no markdown link) — catches "search: …" entries too
    learning_plan = re.sub(r'^- \[(\d+)\] (?!\[)([^\n]+)', _fix_plain_ref, learning_plan, flags=re.MULTILINE)
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

    # validate all URLs — replace broken ones, resolve any non-URL link cells
    log_fn("[URL-VALIDATE] Checking resource links...")
    t_val = _time.time()
    learning_plan, url_metrics = _validate_urls(learning_plan, log_fn=log_fn)
    log_fn("[URL-VALIDATE] Resolving missing/fallback links...")
    learning_plan, resolved, removed = _resolve_link_fallbacks(learning_plan, log_fn=log_fn)
    url_metrics["resolved"] = resolved
    url_metrics["removed_rows"] = url_metrics.get("removed_rows", 0) + removed
    # total rows seen across both passes; final rows with a valid URL
    url_metrics["total_rows"] = url_metrics["valid"] + resolved + url_metrics["removed_rows"]
    url_metrics["final_valid"] = url_metrics["valid"] + resolved
    val_ms = int((_time.time() - t_val) * 1000)

    # count inline citations in the final plan text
    citation_count = len(re.findall(r'\[\d+\]', learning_plan))
    total_ms = int((_time.time() - t_total_start) * 1000)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "outputs", timestamp))
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "learning_plan.md"), "w", encoding="utf-8") as f:
        f.write(f"# Learning Plan\n**Goal:** {goal}\n\n{learning_plan}")

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
