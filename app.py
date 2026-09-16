"""justdata — Ask your database.

Claude-style light empty state: a warm serif greeting centered in the viewport,
with a rounded input (small red send arrow) beneath it. Left sidebar holds
New chat, Recents and settings. Stop (■) replaces send (→) while running.

Run:  .\\run.ps1   ->   http://localhost:8501
"""
import re
import threading
import time

import pandas as pd
import streamlit as st

import db
import llm
import recents
import store

BRAND_RED = "#e2231a"      # justdata brand red
BRAND_ORANGE = "#f5821f"   # justdata brand orange

st.set_page_config(
    page_title="justdata · Ask",
    page_icon="✳",
    layout="centered",
    initial_sidebar_state="expanded",
)

# Background job state survives Streamlit reruns (module is cached).
_job = {
    "thread": None,
    "cancel": None,
    "result": None,
    "error": None,
    "done": False,
    "question": None,
}

# ---------------------------------------------------------------------------
# Styling — clean white/light look, serif greeting, red/orange accents
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
      #MainMenu, footer {{visibility: hidden;}}
      [data-testid="stDecoration"] {{display: none;}}

      /* Keep a slim header so the sidebar open/close control always works.
         Do NOT display:none the toolbar — the sidebar reopen arrow
         (stExpandSidebarButton) lives there in newer Streamlit. */
      header {{background: transparent !important; height: 2.75rem !important;}}
      [data-testid="stHeader"] {{background: transparent !important; height: 2.75rem !important;}}
      [data-testid="stToolbar"] {{visibility: hidden;}}

      /* Sidebar reopen arrow (collapsed state) — always visible, all versions */
      [data-testid="stExpandSidebarButton"],
      [data-testid="stSidebarCollapsedControl"],
      [data-testid="collapsedControl"] {{
        visibility: visible !important;
        display: flex !important;
        opacity: 1 !important;
      }}
      [data-testid="stExpandSidebarButton"] button,
      [data-testid="stSidebarCollapsedControl"] button {{
        visibility: visible !important;
        background: #ffffff !important;
        border: 1px solid #e3e3e0 !important;
        border-radius: 8px !important;
        color: #1a1a1a !important;
      }}
      /* Collapse arrow inside the sidebar — always visible, no hover needed */
      [data-testid="stSidebarCollapseButton"] {{
        visibility: visible !important;
        display: flex !important;
        opacity: 1 !important;
      }}
      [data-testid="stSidebarCollapseButton"] button {{
        visibility: visible !important;
      }}

      [data-testid="stSidebar"] {{
        background: #f7f7f5 !important;
        border-right: 1px solid #e8e8e4 !important;
      }}

      .block-container {{padding-top: 2rem; max-width: 720px;}}

      .spacer {{ height: 15vh; }}

      .hero {{
        font-family: Georgia, 'Iowan Old Style', 'Times New Roman', serif;
        font-size: 2.9rem; font-weight: 500; text-align: center;
        color: #1f1f1f; letter-spacing: -0.5px; margin-bottom: 0.25rem;
      }}
      .subtitle {{
        text-align: center; color: #8a8a8a; font-size: 0.98rem; margin-bottom: 1.6rem;
      }}
      .examples {{ text-align: center; margin-top: 1.3rem; }}
      .examples .ex {{ color: #a2a2a2; font-size: 0.9rem; margin: 0.35rem 0; }}
      .answer {{ font-size: 1.08rem; font-weight: 600; color: #1a1a1a; margin: 0.2rem 0 0.6rem; }}

      /* rounded input box */
      .stTextInput input {{
        border-radius: 12px; border: 1px solid #e3e3e0; padding: 0.75rem 0.95rem;
        font-size: 1rem; background: #fbfbfa;
      }}
      .stTextInput input:focus {{ border-color: {BRAND_RED}; box-shadow: none; }}

      /* hide the "Press Enter to submit form" hint */
      [data-testid="InputInstructions"] {{ display: none; }}

      /* send arrow = small red square button */
      .stFormSubmitButton > button {{
        background: {BRAND_RED}; color: #ffffff; border: none; border-radius: 12px;
        font-size: 1.2rem; font-weight: 700; height: 2.9rem;
      }}
      .stFormSubmitButton > button:hover {{ background: {BRAND_ORANGE}; color: #ffffff; }}

      /* stop = dark square in the same slot */
      .st-key-stop_chat_btn button {{
        background: #1a1a1a !important; color: #ffffff !important;
        border-radius: 12px !important; height: 2.9rem !important; min-width: 2.9rem !important;
      }}
      .st-key-stop_chat_btn button:hover {{ background: #333333 !important; }}

      /* sidebar "New chat" = red; other sidebar buttons stay quiet */
      [data-testid="stSidebar"] .st-key-new_chat button {{
        background: {BRAND_RED} !important; color: #ffffff !important;
        border: none !important; border-radius: 8px !important; font-weight: 600 !important;
      }}
      [data-testid="stSidebar"] .st-key-new_chat button:hover {{
        background: {BRAND_ORANGE} !important;
      }}
      [data-testid="stSidebar"] .st-key-reindex button {{
        background: transparent !important; color: #666 !important;
        border: 1px solid #e3e3e0 !important; border-radius: 8px !important;
        font-weight: 400 !important;
      }}
      [data-testid="stSidebar"] div[class*="st-key-recent_"] button {{
        background: transparent !important; color: #444 !important;
        border: none !important; border-radius: 6px !important;
        font-weight: 400 !important; text-align: left !important;
        justify-content: flex-start !important; padding-left: 0.4rem !important;
      }}
      [data-testid="stSidebar"] div[class*="st-key-recent_"] button:hover {{
        background: #ebebe8 !important;
      }}

      .stCode {{ border-left: 3px solid {BRAND_RED}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Safety guard: only allow read-only SELECT queries.
# ---------------------------------------------------------------------------
def clean_sql(sql: str) -> str:
    """Strip markdown fences / chatter so we inspect the real statement."""
    s = (sql or "").strip()
    fence = re.search(r"```(?:sql|tsql|transact-sql)?\s*([\s\S]*?)```", s, re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    m = re.search(r"(?is)\b(select|with)\b[\s\S]*", s)
    if m:
        s = m.group(0).strip()
    return s.rstrip(";").strip()


def is_safe_select(sql: str) -> bool:
    s = clean_sql(sql)
    if not s or ";" in s:
        return False
    if not re.match(r"^\s*(select|with)\b", s, re.IGNORECASE):
        return False
    if re.search(r"(?is)\bselect\b.+\binto\b", s):
        return False
    banned = (
        r"\b(insert|update|delete|drop|alter|create|truncate|merge|"
        r"grant|revoke|exec|execute|sp_|xp_)\b"
    )
    return not re.search(banned, s, re.IGNORECASE)


# ---------------------------------------------------------------------------
# One-time setup per session.
# ---------------------------------------------------------------------------
@st.cache_resource
def bootstrap():
    """Prepare the demo DB (SQLite only) and make sure the schema index matches."""
    if db.DB_KIND == "sqlite":
        db.setup_database()
    recents.init()
    return store.ensure_index()


indexed_tables = bootstrap()

for key, default in (
    ("history", []),
    ("processing", False),
    ("pending_question", None),
    ("pending_explain", False),
):
    if key not in st.session_state:
        st.session_state[key] = default


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise llm.CancelledError("Stopped.")


def answer(question: str, explain: bool, cancel_event=None) -> dict:
    _check_cancel(cancel_event)
    relevant = store.retrieve(question, k=6)
    schema = "\n\n".join(relevant)

    _check_cancel(cancel_event)
    raw_sql = llm.generate_sql(schema, question, cancel_event=cancel_event)
    sql = clean_sql(raw_sql)

    result = {"question": question, "sql": sql or raw_sql, "tables": relevant,
              "columns": [], "rows": None, "error": None, "truncated": False,
              "safe": is_safe_select(raw_sql), "summary": None}

    if result["safe"]:
        _check_cancel(cancel_event)
        try:
            result["columns"], result["rows"], result["truncated"] = db.run_query(
                sql, cancel_event=cancel_event,
            )
            if explain and result["rows"]:
                _check_cancel(cancel_event)
                result["summary"] = llm.summarize_answer(
                    question, sql, result["rows"],
                    truncated=result["truncated"],
                    cancel_event=cancel_event,
                )
        except llm.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            if cancel_event is not None and cancel_event.is_set():
                raise llm.CancelledError("Stopped.") from exc
            result["error"] = str(exc)
    return result


def render(item: dict) -> None:
    with st.chat_message("user"):
        st.write(item["question"])
    with st.chat_message("assistant"):
        if not item["safe"]:
            st.error(
                "Blocked: only read-only SELECT queries are allowed. "
                "Open “SQL & tables used” below to see what was generated."
            )
        elif item["error"]:
            st.error(item["error"])
        else:
            if item["summary"]:
                st.markdown(f"<div class='answer'>{item['summary']}</div>", unsafe_allow_html=True)
            if item["rows"]:
                df = pd.DataFrame(item["rows"], columns=item["columns"] or None)
                st.dataframe(df, use_container_width=True, hide_index=True)
                if item.get("truncated"):
                    st.caption(f"Showing the first {db.MAX_ROWS} rows — there are more.")
            else:
                st.info("No rows returned.")
        with st.expander("SQL & tables used", expanded=not item["safe"]):
            st.code(item["sql"], language="sql")
            for doc in item["tables"]:
                st.code(doc, language="sql")


def _start_job(question: str, explain: bool) -> None:
    """Kick off answer() on a daemon thread so Stop can interrupt it."""
    alive = _job["thread"] is not None and _job["thread"].is_alive()
    if alive and _job["question"] == question and not _job["done"]:
        return

    cancel = threading.Event()
    _job.update(cancel=cancel, result=None, error=None, done=False, question=question)

    def work():
        try:
            _job["result"] = answer(question, explain, cancel)
        except llm.CancelledError:
            _job["error"] = "cancelled"
        except Exception as exc:  # noqa: BLE001
            _job["error"] = str(exc)
        finally:
            _job["done"] = True

    thread = threading.Thread(target=work, daemon=True)
    _job["thread"] = thread
    thread.start()


def _reset_job() -> None:
    _job.update(
        thread=None, cancel=None, result=None, error=None, done=False, question=None,
    )


def queue_question(question: str, explain: bool) -> None:
    st.session_state.pending_question = question
    st.session_state.pending_explain = explain
    st.session_state.processing = True
    _reset_job()


def request_stop() -> None:
    if _job["cancel"] is not None:
        _job["cancel"].set()
    db.cancel_active_query()


def chat_bar(placeholder: str, *, stop_mode: bool = False, form_key: str = "chat_send"):
    """Input row like Claude/Cursor: → to send, ■ to stop while generating."""
    if stop_mode:
        c1, c2 = st.columns([12, 1])
        with c1:
            st.text_input("q", placeholder=placeholder, label_visibility="collapsed",
                          disabled=True, key="chat_bar_busy")
        with c2:
            stopped = st.button("■", type="primary", key="stop_chat_btn",
                                help="Stop generating")
        return None, stopped

    with st.form(form_key, clear_on_submit=True):
        c1, c2 = st.columns([12, 1])
        with c1:
            typed = st.text_input("q", placeholder=placeholder, label_visibility="collapsed")
        with c2:
            sent = st.form_submit_button("→")
        return (typed or "").strip(), sent


# ---------------------------------------------------------------------------
# Sidebar — New chat, settings + persistent Recents
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"#### <span style='color:{BRAND_RED}'>justdata</span>",
                unsafe_allow_html=True)
    st.caption(f"Data source: {db.DB_KIND.upper()} · {indexed_tables} tables indexed")

    if st.button("＋  New chat", key="new_chat", use_container_width=True):
        st.session_state.history = []
        st.session_state.processing = False
        st.session_state.pending_question = None
        _reset_job()
        st.rerun()

    if st.button("↻  Reindex schema", key="reindex", use_container_width=True,
                 help="Re-read the database schema and rebuild the search index. "
                      "Do this after tables or columns change."):
        with st.spinner("Reading schema…"):
            store.index_schema(force=True)
        bootstrap.clear()
        st.rerun()

    # Default OFF so real DB rows are not sent to Claude unless you opt in.
    explain = st.toggle(
        "Explain answers in words",
        value=False,
        key="explain",
        help="When ON, result rows are sent to Claude to phrase a sentence. "
             "Leave OFF for sensitive/financial data — you'll still get SQL + the table.",
        disabled=st.session_state.processing,
    )

    st.markdown("---")
    st.markdown("###### Recents")
    saved = recents.list_recent(20)
    if saved:
        for item in saved:
            label = item["question"]
            if len(label) > 42:
                label = label[:41] + "…"
            if st.button(label, key=f"recent_{item['id']}", use_container_width=True,
                         disabled=st.session_state.processing):
                queue_question(item["question"], st.session_state.get("explain", False))
                st.rerun()
    else:
        st.caption("No queries yet")


# ---------------------------------------------------------------------------
# Main — empty state is a centered greeting + input; once a question is asked
# the greeting gives way to the transcript and the input follows it.
# ---------------------------------------------------------------------------
empty = not st.session_state.history and not st.session_state.processing

if empty:
    st.markdown("<div class='spacer'></div>", unsafe_allow_html=True)
    st.markdown("<div class='hero'>Hello, boss.</div>", unsafe_allow_html=True)
    st.markdown("<div class='subtitle'>Ask anything about your data, in plain English.</div>",
                unsafe_allow_html=True)

    typed, sent = chat_bar("How can I help, boss?", form_key="chat_send_empty")
    if sent and typed:
        queue_question(typed, explain)
        st.rerun()

    st.markdown(
        "<div class='examples'>"
        "<div class='ex'>How many funded loans are there</div>"
        "<div class='ex'>List all customers</div>"
        "<div class='ex'>Which loans are still pending</div>"
        "</div>",
        unsafe_allow_html=True,
    )
else:
    for item in st.session_state.history:
        render(item)

# ---------------------------------------------------------------------------
# Background processing — ■ sits in the chat bar where → normally is
# ---------------------------------------------------------------------------
if st.session_state.processing and st.session_state.pending_question:
    question = st.session_state.pending_question
    _start_job(question, st.session_state.pending_explain)

    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        status = st.empty()
        status.markdown("Thinking…")

    _, stopped = chat_bar("Generating…", stop_mode=True)
    if stopped:
        request_stop()
        status.warning("Stopping…")

    if _job["done"]:
        if _job["error"] == "cancelled":
            status.info("Stopped.")
            st.session_state.processing = False
            st.session_state.pending_question = None
            _reset_job()
            time.sleep(0.35)
            st.rerun()
        elif _job["error"]:
            status.error(_job["error"])
            st.session_state.processing = False
            st.session_state.pending_question = None
            _reset_job()
            time.sleep(1.0)
            st.rerun()
        elif _job["result"] is not None:
            result = _job["result"]
            st.session_state.history.append(result)
            recents.record(result["question"])
            st.session_state.processing = False
            st.session_state.pending_question = None
            _reset_job()
            st.rerun()
    else:
        time.sleep(0.35)
        st.rerun()
elif not empty:
    typed, sent = chat_bar("Ask a follow-up…", form_key="chat_send_followup")
    if sent and typed:
        queue_question(typed, explain)
        st.rerun()
