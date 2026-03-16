import html as _html
import streamlit as st
import tempfile
import os
import markdown as md
from dotenv import load_dotenv
from agent.runner import run

load_dotenv()

st.set_page_config(page_title="Learnscout — Career Learning Plan", page_icon=None, layout="wide")

st.markdown("""
<style>
    /* ── Global ── */
    [data-testid="stAppViewContainer"] { background: #f5f6fa; }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stMainBlockContainer"] { padding-top: 2rem; }

    /* ── Hero ── */
    .hero-wrap {
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
        border-radius: 16px;
        padding: 2.2rem 2.5rem;
        margin-bottom: 1.8rem;
        display: flex;
        align-items: center;
        gap: 1.4rem;
    }
    .hero-title { font-size: 2.2rem; font-weight: 800; color: #fff; margin: 0; letter-spacing: -0.5px; }
    .hero-sub { font-size: 0.97rem; color: rgba(255,255,255,0.82); margin: 0.3rem 0 0 0; }

    /* ── Input card ── */
    .input-card {
        background: #ffffff;
        border: 1px solid #e0e3ea;
        border-radius: 14px;
        padding: 1.8rem 2rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .field-label {
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #555;
        margin-bottom: 0.4rem;
    }
    .field-label span { color: #e05252; margin-left: 3px; }

    /* ── Primary button ── */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1a73e8, #0d47a1) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.55rem 1.8rem !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.01em !important;
        box-shadow: 0 2px 8px rgba(26,115,232,0.35) !important;
        transition: opacity 0.15s ease !important;
    }
    .stButton > button[kind="primary"]:hover { opacity: 0.9 !important; }

    /* ── Log box ── */
    .log-card {
        background: #fff;
        border: 1px solid #e0e3ea;
        border-radius: 14px;
        padding: 1.2rem 1.5rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .log-box {
        background: #0d1117;
        color: #c9d1d9;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 0.76rem;
        line-height: 1.55;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        height: 560px;
        overflow-y: auto;
        white-space: pre-wrap;
        margin-top: 0.6rem;
    }
    .section-label {
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #888;
        margin-bottom: 0.5rem;
    }

    /* ── Plan scroll box ── */
    .plan-scroll-box {
        background: #ffffff;
        border: 1px solid #e0e3ea;
        border-radius: 14px;
        padding: 1.4rem 1.8rem;
        height: 560px;
        overflow-y: auto;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        font-size: 0.9rem;
        line-height: 1.65;
        color: #1a1a2e;
    }
    .plan-scroll-box h2 {
        font-size: 1.1rem;
        font-weight: 700;
        color: #0d47a1;
        margin-top: 1.4rem;
        margin-bottom: 0.4rem;
        border-bottom: 1px solid #e8f0fe;
        padding-bottom: 0.3rem;
    }
    .plan-scroll-box h3 {
        font-size: 0.97rem;
        font-weight: 700;
        color: #1a73e8;
        margin-top: 1rem;
        margin-bottom: 0.3rem;
    }
    .plan-scroll-box table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.82rem;
        margin: 0.6rem 0 1rem 0;
    }
    .plan-scroll-box th {
        background: #e8f0fe;
        color: #0d47a1;
        font-weight: 700;
        padding: 0.45rem 0.7rem;
        text-align: left;
        border: 1px solid #c5d8fb;
    }
    .plan-scroll-box td {
        padding: 0.4rem 0.7rem;
        border: 1px solid #e0e3ea;
        vertical-align: top;
    }
    .plan-scroll-box tr:nth-child(even) td { background: #f8faff; }
    .plan-scroll-box a { color: #1a73e8; text-decoration: underline; cursor: pointer; }
    .plan-scroll-box a:hover { color: #0d47a1; }
    .plan-scroll-box ul, .plan-scroll-box ol {
        padding-left: 1.3rem;
        margin: 0.3rem 0 0.7rem 0;
    }
    .plan-scroll-box strong { color: #1a1a2e; }

    /* ── File chip ── */
    .file-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: #f0f4ff;
        border: 1px solid #c5d8fb;
        border-radius: 6px;
        padding: 0.35rem 0.75rem;
        font-size: 0.82rem;
        font-weight: 500;
        color: #1a73e8;
        margin-top: 0.5rem;
    }

    /* ── Download button ── */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        letter-spacing: 0.02em !important;
        padding: 0.6rem 1.4rem !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.18) !important;
        transition: opacity 0.15s ease !important;
        width: 100%;
        margin-top: 1rem;
    }
    .stDownloadButton > button:hover {
        opacity: 0.88 !important;
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%) !important;
    }

    /* ── Latency bar ── */
    .latency-bar {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
        background: #f8faff;
        border: 1px solid #e0e3ea;
        border-radius: 8px;
        padding: 0.6rem 1rem;
        margin-top: 0.75rem;
        font-size: 0.8rem;
        color: #555;
    }
    .lat-item { color: #333; }
    .lat-sep { color: #aaa; }
    .lat-total { color: #0d47a1; font-weight: 700; margin-left: 0.3rem; }

    /* ── Group label (sub-heading inside eval/cost panels) ── */
    .group-label {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #aaa;
        margin-top: 0.75rem;
        margin-bottom: 0.25rem;
    }
    .group-label:first-child { margin-top: 0.3rem; }

    /* ── Usage bar ── */
    .usage-bar {
        display: flex;
        gap: 0.75rem;
        background: #fff;
        border: 1px solid #e0e3ea;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
        margin-top: 0.5rem;
    }
    .usage-stat {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        padding: 0.5rem;
        border-radius: 8px;
        background: #f8faff;
    }
    .usage-stat.highlight {
        background: #e8f0fe;
        border: 1px solid #c5d8fb;
    }
    .usage-val {
        font-size: 1.25rem;
        font-weight: 700;
        color: #0d47a1;
    }
    .usage-lbl {
        font-size: 0.72rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.2rem;
    }

    /* ── Task expanders ── */
    div[data-testid="stExpander"] {
        background: #fff !important;
        border: 1px solid #e0e3ea !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
        margin-bottom: 0.5rem;
    }
    div[data-testid="stExpander"] summary {
        font-size: 0.86rem !important;
        font-weight: 600 !important;
        color: #1a1a2e !important;
        padding: 0.75rem 1rem !important;
    }
    div[data-testid="stExpander"] summary:hover {
        background: #f8faff !important;
        border-radius: 10px;
    }
    div[data-testid="stExpander"] > div[data-testid="stExpanderDetails"] {
        padding: 0 1rem 0.9rem 1rem !important;
        font-size: 0.82rem;
        color: #444;
        line-height: 1.6;
    }
</style>
""", unsafe_allow_html=True)

# ── Hero ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-wrap">
    <div>
        <div class="hero-title">Learnscout</div>
        <div class="hero-sub">Share your career goal and CV — Learnscout researches real job requirements, identifies your skill gaps, and builds a personalised learning plan to get you there.</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Input card ───────────────────────────────────────────────────────────────
with st.container(border=True):
    col_goal, col_cv = st.columns([3, 2], gap="large")

with col_goal:
    st.markdown('<div class="field-label">Career Goal</div>', unsafe_allow_html=True)
    goal_text = st.text_area(
        label="goal",
        label_visibility="collapsed",
        placeholder="e.g. I want to become a Senior ML Engineer at a top AI company",
        height=120,
    )

with col_cv:
    st.markdown('<div class="field-label">CV / Resume <span>*</span></div>', unsafe_allow_html=True)
    resume_file = st.file_uploader(
        label="cv",
        label_visibility="collapsed",
        type=["pdf", "txt"],
        help="PDF or plain text. Required for a personalised gap analysis.",
    )
    if resume_file:
        st.markdown(
            f'<div class="file-chip">📄 {resume_file.name}</div>',
            unsafe_allow_html=True,
        )

run_btn = st.button("Generate Learning Plan", type="primary")

# ── Output columns ────────────────────────────────────────────────────────────
col_log, col_plan = st.columns([4, 6], gap="large")

with col_log:
    st.markdown('<div class="section-label">Agent Log</div>', unsafe_allow_html=True)
    log_placeholder = st.empty()

with col_plan:
    st.markdown('<div class="section-label">Your Learning Plan</div>', unsafe_allow_html=True)
    plan_placeholder = st.empty()

# ── Run ───────────────────────────────────────────────────────────────────────
if run_btn:
    if not goal_text.strip():
        st.error("Please describe your career goal before generating.")
        st.stop()

    if not resume_file:
        st.error("Please upload your CV — it's required for a personalised gap analysis.")
        st.stop()

    if not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY not set. Add it to your .env file.")
        st.stop()

    suffix = ".pdf" if resume_file.type == "application/pdf" else ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(resume_file.read())
        resume_path = tmp.name

    log_lines = []
    task_states = {}
    plan_state = {}

    def log_fn(msg: str):
        # escape HTML, then collapse any embedded newlines to a single space
        safe = _html.escape(str(msg)).replace('\n', ' ').replace('\r', '')
        log_lines.append(safe)
        log_placeholder.markdown(
            f'<div class="log-box">{"<br>".join(log_lines)}</div>',
            unsafe_allow_html=True,
        )

    def on_plan(plan):
        plan_state["plan"] = plan
        for t in plan:
            task_states[t["id"]] = {"task": t["task"], "status": "pending", "summary": ""}

    def on_task_start(task):
        task_states[task["id"]]["status"] = "in_progress"

    def on_task_done(task, summary):
        task_states[task["id"]]["status"] = task["status"]
        task_states[task["id"]]["summary"] = summary

    try:
        with st.spinner("Learnscout is researching and building your plan..."):
            result = run(
                goal=goal_text,
                resume_path=resume_path,
                log_callback=log_fn,
                on_plan=on_plan,
                on_task_start=on_task_start,
                on_task_done=on_task_done,
            )
    except ValueError as e:
        st.error(str(e))
        st.stop()
    finally:
        if resume_path and os.path.exists(resume_path):
            os.unlink(resume_path)

    learning_plan = result["plan"]
    goal = result.get("goal", "")
    output_dir = result.get("output_dir", "")
    usage = result.get("usage", {})
    metrics = result.get("metrics", {})

    with col_plan:
        plan_html = md.markdown(learning_plan, extensions=["tables"])
        plan_placeholder.markdown(
            f'<div class="plan-scroll-box">'
            f'<div style="font-size:0.78rem;color:#888;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:1rem;">Goal: {_html.escape(goal)}</div>'
            f'{plan_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # build PDF download (xhtml2pdf) with markdown fallback if unavailable
        _pdf_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{font-family:Arial,sans-serif;font-size:12px;line-height:1.65;color:#1a1a2e;margin:48px 56px;}}
h1{{font-size:20px;color:#0d47a1;margin-bottom:4px;}}
h2{{font-size:15px;color:#0d47a1;border-bottom:1px solid #e8f0fe;padding-bottom:4px;margin-top:28px;}}
h3{{font-size:13px;color:#1a73e8;margin-top:18px;}}
p{{margin:6px 0;}}
table{{width:100%;border-collapse:collapse;margin:8px 0 18px 0;font-size:11px;}}
th{{background:#e8f0fe;color:#0d47a1;font-weight:bold;padding:6px 10px;text-align:left;border:1px solid #c5d8fb;}}
td{{padding:5px 10px;border:1px solid #e0e3ea;vertical-align:top;}}
tr:nth-child(even) td{{background:#f8faff;}}
a{{color:#1a73e8;text-decoration:underline;}}
strong{{color:#1a1a2e;}}
ul,ol{{padding-left:20px;margin:4px 0 10px 0;}}
li{{margin-bottom:3px;}}
</style></head><body>
<h1>Learning Plan</h1>
<p style="color:#666;font-size:11px;margin-bottom:24px;">Goal: {_html.escape(goal)}</p>
{plan_html}
</body></html>"""

        try:
            from xhtml2pdf import pisa as _pisa
            import io as _io
            _buf = _io.BytesIO()
            _result = _pisa.CreatePDF(_pdf_html, dest=_buf)
            if not _result.err:
                st.download_button(
                    label="Download Learning Plan  (PDF)",
                    data=_buf.getvalue(),
                    file_name="learning_plan.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                raise RuntimeError("xhtml2pdf error")
        except Exception:
            st.download_button(
                label="Download Learning Plan  (Markdown)",
                data=learning_plan,
                file_name="learning_plan.md",
                mime="text/markdown",
                use_container_width=True,
            )

    if output_dir:
        st.caption(f"Saved to `{output_dir}`")

    if plan_state.get("plan"):
        st.divider()
        st.markdown('<div class="section-label">Task Execution Summary</div>', unsafe_allow_html=True)

        status_icon = {"done": "✅", "failed": "❌", "in_progress": "⏳", "pending": "○"}
        status_color = {"done": "#1e7e34", "failed": "#721c24", "in_progress": "#856404", "pending": "#6c757d"}

        cols = st.columns(2)
        for i, (tid, state) in enumerate(task_states.items()):
            icon = status_icon.get(state["status"], "?")
            color = status_color.get(state["status"], "#6c757d")
            label = state["status"].replace("_", " ").title()
            header = (
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.3rem;">'
                f'<span style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;'
                f'background:#f0f4ff;color:#1a73e8;border:1px solid #c5d8fb;border-radius:20px;padding:0.18rem 0.55rem;">'
                f'Task {tid}</span>'
                f'<span style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:{color};">'
                f'{icon} {label}</span>'
                f'</div>'
            )
            with cols[i % 2].expander(f"Task {tid}: {state['task']}", expanded=False):
                st.markdown(header, unsafe_allow_html=True)
                st.markdown(state["summary"] or "No summary.")

    if usage or metrics:
        st.divider()
        r = metrics.get("research", {})
        u = metrics.get("urls", {})
        t = metrics.get("tasks", {})
        lat = metrics.get("latency_ms", {})
        total_lat = lat.get("total", 0)

        def _stat(val, lbl, highlight=False):
            cls = "usage-stat highlight" if highlight else "usage-stat"
            return f'<div class="{cls}"><div class="usage-val">{val}</div><div class="usage-lbl">{lbl}</div></div>'

        st.markdown('<div class="section-label">Run Evaluation</div>', unsafe_allow_html=True)

        inp = usage.get("prompt", 0)
        out = usage.get("completion", 0)
        tok_total = usage.get("total", 0)
        cost = usage.get("cost_usd", 0.0)

        # row 1: research | cost & tokens
        ev_row1_left, ev_row1_right = st.columns(2, gap="large")

        with ev_row1_left:
            st.markdown('<div class="group-label">Research</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="usage-bar">'
                + _stat(r.get("indexed", "—"), "Sources indexed")
                + _stat(r.get("chunks", "—"), "Chunks indexed")
                + _stat(r.get("failed", "—"), "Fetch failures")
                + _stat(f'{t.get("done","—")}/{t.get("total","—")}', "Tasks done", highlight=True)
                + f'</div>',
                unsafe_allow_html=True,
            )

        with ev_row1_right:
            st.markdown('<div class="group-label">Cost &amp; Tokens</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="usage-bar">'
                + _stat(f"{inp:,}", "Input tokens")
                + _stat(f"{out:,}", "Output tokens")
                + _stat(f"{tok_total:,}", "Total tokens")
                + _stat(f"${cost:.4f}", "Est. cost (GPT-4o)", highlight=True)
                + f'</div>',
                unsafe_allow_html=True,
            )

        # row 2: resource links | latency
        ev_row2_left, ev_row2_right = st.columns(2, gap="large")

        with ev_row2_left:
            st.markdown('<div class="group-label">Resource Links</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="usage-bar">'
                + _stat(f'{u.get("final_valid","—")}/{u.get("total_rows","—")}', "Valid")
                + _stat(u.get("replaced", "—"), "Replaced")
                + _stat(u.get("resolved", "—"), "Resolved")
                + _stat(u.get("removed_rows", "—"), "Rows removed", highlight=True)
                + f'</div>',
                unsafe_allow_html=True,
            )

        with ev_row2_right:
            if lat:
                st.markdown('<div class="group-label">Latency</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="usage-bar">'
                    + _stat(f'{lat.get("research",0)/1000:.1f}s', "Research")
                    + _stat(f'{lat.get("execution",0)/1000:.1f}s', "Execution")
                    + _stat(f'{lat.get("synthesis",0)/1000:.1f}s', "Synthesis")
                    + _stat(f'{lat.get("validation",0)/1000:.1f}s', "Validation")
                    + _stat(f'{total_lat/1000:.1f}s', "Total", highlight=True)
                    + f'</div>',
                    unsafe_allow_html=True,
                )
