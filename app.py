"""Safe Financial — Ask your database.

Claude-style light empty state: a small brand icon + a warm serif greeting
centered in the viewport, with a rounded input (small red send arrow) beneath it.

Run:  streamlit run app.py   ->   http://localhost:8501
"""
import re

import pandas as pd
import streamlit as st

import db
import llm
import store

BRAND_RED = "#e2231a"      # Safe Financial red
BRAND_ORANGE = "#f5821f"   # Safe Financial orange

st.set_page_config(page_title="Safe Financial · Ask", page_icon="✳", layout="centered")

# ---------------------------------------------------------------------------
# Styling — clean white/light look, serif greeting, red/orange accents
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
      /* Hide chrome, but KEEP the sidebar open/close control visible.
         Hiding the whole header also hid the only way to open the sidebar. */
      #MainMenu, footer {{visibility: hidden;}}
      header {{background: transparent;}}
      [data-testid="stToolbar"] {{display: none;}}
      [data-testid="stDecoration"] {{display: none;}}
      [data-testid="stHeader"] {{background: transparent;}}
      [data-testid="stSidebarCollapsedControl"] {{
        visibility: visible !important;
        display: flex !important;
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

      /* bottom-pinned chat input (shown once a conversation has started) */
      .stChatInput {{ border-radius: 12px; border: 1px solid #e3e3e0; background: #fbfbfa; }}
      .stChatInput:focus-within {{ border-color: {BRAND_RED}; }}
      .stChatInput button {{ background: {BRAND_RED}; color: #ffffff; border-radius: 10px; }}
      .stChatInput button:hover {{ background: {BRAND_ORANGE}; color: #ffffff; }}

      /* sidebar "New chat" = red */
      .stButton > button {{
        background: {BRAND_RED}; color: #ffffff; border: none; border-radius: 8px; font-weight: 600;
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
    # ```sql ... ``` or ``` ... ```
    fence = re.search(r"```(?:sql|tsql|transact-sql)?\s*([\s\S]*?)```", s, re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    # If Claude added a preamble, keep from the first SELECT/WITH onward.
    m = re.search(r"(?is)\b(select|with)\b[\s\S]*", s)
    if m:
        s = m.group(0).strip()
    return s.rstrip(";").strip()


def is_safe_select(sql: str) -> bool:
    s = clean_sql(sql)
    if not s:
        return False
    # Block stacked statements: SELECT ...; DELETE ...
    if ";" in s:
        return False
    if not re.match(r"^\s*(select|with)\b", s, re.IGNORECASE):
        return False
    # SELECT INTO creates a table — treat as write.
    if re.search(r"(?is)\bselect\b.+\binto\b", s):
        return False
    banned = (
        r"\b(insert|update|delete|drop|alter|create|truncate|merge|"
        r"grant|revoke|exec|execute|sp_|xp_)\b"
    )
    if re.search(banned, s, re.IGNORECASE):
        return False
    return True


# ---------------------------------------------------------------------------
# One-time setup per session.
# ---------------------------------------------------------------------------
@st.cache_resource
def bootstrap():
    """Prepare the demo DB (SQLite only) and make sure the schema index matches."""
    if db.DB_KIND == "sqlite":
        db.setup_database()
    return store.ensure_index()


indexed_tables = bootstrap()

if "history" not in st.session_state:
    st.session_state.history = []


def answer(question: str, explain: bool) -> dict:
    relevant = store.retrieve(question, k=6)
    schema = "\n\n".join(relevant)
    raw_sql = llm.generate_sql(schema, question)
    sql = clean_sql(raw_sql)

    result = {"question": question, "sql": sql or raw_sql, "tables": relevant,
              "columns": [], "rows": None, "error": None, "truncated": False,
              "safe": is_safe_select(raw_sql), "summary": None}

    if result["safe"]:
        try:
            result["columns"], result["rows"], result["truncated"] = db.run_query(sql)
            if explain and result["rows"]:
                result["summary"] = llm.summarize_answer(question, sql, result["rows"],
                                                         truncated=result["truncated"])
        except Exception as exc:  # noqa: BLE001
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


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"#### <span style='color:{BRAND_RED}'>Safe Financial</span>",
                unsafe_allow_html=True)
    st.caption(f"Data source: {db.DB_KIND.upper()} · {indexed_tables} tables indexed")

    if st.button("＋  New chat", use_container_width=True):
        st.session_state.history = []
        st.rerun()

    if st.button("↻  Reindex schema", use_container_width=True,
                 help="Re-read the database schema and rebuild the search index. "
                      "Do this after tables or columns change."):
        with st.spinner("Reading schema…"):
            store.index_schema(force=True)
        bootstrap.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("###### Recent")
    if st.session_state.history:
        for item in reversed(st.session_state.history[-20:]):
            st.markdown(f"<span style='opacity:0.75;font-size:0.9rem'>• {item['question']}</span>",
                        unsafe_allow_html=True)
    else:
        st.caption("No queries yet")


# ---------------------------------------------------------------------------
# Main — empty state is a centered greeting + input; once a question is asked
# the greeting gives way to the transcript (oldest first) and the input sticks
# to the bottom of the window.
# ---------------------------------------------------------------------------
empty = not st.session_state.history
pending = None

# Always visible on the main page (sidebar was hard to find when collapsed).
# Default OFF so real DB rows are not sent to Claude unless you opt in.
explain = st.toggle(
    "Explain answers in words",
    value=False,
    help="When ON, result rows are sent to Claude to phrase a sentence. "
         "Leave OFF for sensitive/financial data — you'll still get SQL + the table.",
)

if empty:
    st.markdown("<div class='spacer'></div>", unsafe_allow_html=True)
    st.markdown("<div class='hero'>Hello, boss.</div>", unsafe_allow_html=True)
    st.markdown("<div class='subtitle'>Ask anything about your data, in plain English.</div>",
                unsafe_allow_html=True)

    # Rounded input with a small red send arrow (→) at the right. Enter submits.
    with st.form("ask", clear_on_submit=True):
        c1, c2 = st.columns([12, 1])
        with c1:
            typed = st.text_input("q", placeholder="How can I help, boss?",
                                  label_visibility="collapsed")
        with c2:
            sent = st.form_submit_button("→")
        if sent and typed.strip():
            pending = typed.strip()

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

    followup = st.chat_input("Ask a follow-up…")
    if followup and followup.strip():
        pending = followup.strip()

if pending:
    # Echo the question straight away, then think under it — the answer lands
    # at the bottom of the transcript on the rerun.
    with st.chat_message("user"):
        st.write(pending)
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            result = answer(pending, explain)
    st.session_state.history.append(result)
    st.rerun()
