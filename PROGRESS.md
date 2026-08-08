# Project Progress & Handoff

A living log of what this project is, what's done, and exactly where to resume.
If you're a new chat/session: **read this top to bottom, then start at "Next step".**

---

## What we're building

A **natural-language → SQL tool** (a from-scratch version of what Vanna AI does),
using the **Claude API** as the LLM. You ask a question in English → Claude writes
SQL → we run it on a database → return the answer. The end goal uses **RAG** so it
works on a large database (hundreds of tables).

## Stack

- **Python 3.12** (installed), virtual env at `.venv`
- **anthropic** — Claude API (writes the SQL)
- **chromadb** — vector database + local embeddings (for RAG retrieval)
- **sqlite3** — practice database (built into Python)
- **pyodbc** — for real SQL Server later
- **python-dotenv** — loads the API key from `.env`

## Important environment facts

- Project folder: `C:\Learn stuff\nlp2sql`
- Activate env each session: `.\.venv\Scripts\Activate.ps1` (prompt shows `(.venv)`)
- API key lives in `.env` as `ANTHROPIC_API_KEY=...` (git-ignored, never committed)
- **Model name:** use `claude-sonnet-5`. The old `claude-3-5-sonnet-*` names DO NOT
  exist on this account. List valid models with `client.models.list()`.
  Available: claude-opus-5, claude-sonnet-5, claude-haiku-4-5-20251001, etc.

---

## Files and what they do

| File | Status | Purpose |
|---|---|---|
| `.env` | done | Holds the real `ANTHROPIC_API_KEY` (git-ignored) |
| `.env.example` | done | Template for the key |
| `requirements.txt` | done | Dependency list |
| `hello.py` | done | First test: proves the Claude API works |
| `db.py` | done | Creates `demo.db` (6 tables), `run_sql()` (SELECT-only guard), `get_table_schemas()`, `get_schema()` |
| `llm.py` | done | `generate_sql()` → SQL; `summarize_answer()` → human sentence |
| `embed_lab.py` | done | Embeddings demo: 384-dim vectors + cosine similarity |
| `store.py` | done | ChromaDB index + `retrieve(question, k)` for relevant schemas |
| `main.py` | done | End-to-end with RAG: retrieve → Claude → SQL → run |
| `demo.db` | generated | The SQLite data file (rebuild with `python db.py`) |
| `chroma_db/` | generated | Persistent ChromaDB store (rebuild with `python store.py`) |

## What works right now (Phase 2 COMPLETE — RAG retrieval wired)

- Phase 1 still works (hello / db / llm / embed_lab). ✅
- `python store.py` → indexes `customers` + `loans`, retrieves loans first for
  "how many funded loans are there". ✅
- `python main.py how many funded loans are there` → retrieves schema →
  `SELECT COUNT(*) FROM loans WHERE status = 3;` → `[(2,)]`. ✅

## Concepts learned (interview-ready)

- LLM API basics: `max_tokens` is required; model names aren't guessable; `stop_reason` & `usage`.
- **RAG** = Retrieve relevant context → Augment the prompt → Generate. (Open-book exam analogy.)
- **Embedding** = text → fixed-length vector (384 numbers here) capturing *meaning*.
- **Not a classifier** — an embedding model outputs a *position*, not a label.
- We **don't train** — we use a pre-trained model (inference). "Training the store" = indexing.
- **Cosine similarity** = angle between vectors = relevance score (0..1).
- **Vector database** (ChromaDB) = stores vectors, does fast nearest-neighbor search.
- **Context window** limit is *why* we retrieve instead of pasting the whole schema.
- Two databases in this project: `demo.db` (the data) + ChromaDB (the meaning-map).
- **PersistentClient** = vectors saved on disk under `chroma_db/`.
- **Collection** ≈ one named bucket of documents+vectors; `upsert` by id = insert-or-replace.
- **`sqlite_master`** = SQLite's catalog; we pull each table's `CREATE TABLE` from it.

---

## Next step (RESUME HERE) — Phase 5: real SQL Server

Phase 4 polish is DONE (Jul 29, 2026):

1. ✅ Answer summarization — `llm.summarize_answer(question, sql, rows)`,
   second Claude call; `main.py` now prints e.g. "There are 3 funded loans."
2. ✅ SELECT-only safety — `db.assert_select_only()` runs inside `run_sql()`:
   single statement only, must start with SELECT/WITH, forbidden-keyword check
   with word boundaries (so `created_at` doesn't trip `create`).
   Verified: `db.run_sql('DROP TABLE loans')` raises ValueError.
3. ⬜ Point at the real SQL Server DB via `pyodbc` + a connection string
   (also use a read-only login there — the keyword guard is defense-in-depth,
   not a real security boundary).

Also done earlier today: demo DB expanded to 6 tables (customers, branches,
employees, loan_products, loans, payments); `llm.py` handles Sonnet 5
ThinkingBlock responses via `_response_text()`.

Known rough edge: retrieval with k=3 sometimes misses the `customers` table for
customer questions (answer says "Customer 4" instead of a name). Fix ideas:
raise k, or enrich indexed documents with table descriptions.

Optional stretch: stop re-indexing on every `main.py` run; index only when schema changes.

## Handoff blurb (paste into a new chat if needed)

> I'm building a NL→SQL RAG tool with the Claude API in `C:\Learn stuff\nlp2sql`.
> Done: Phase 1 (hello/db/llm/main/embed_lab) + Phase 2 (`store.py` ChromaDB
> retrieval; `main.py` uses `retrieve()` instead of full `get_schema()`).
> Model: `claude-sonnet-5`. Working style: YOU write the code, I guide/explain
> step-by-step (I'm newer to Python). Next: Phase 4 polish — answer summarization,
> SELECT-only safety, then real SQL Server via pyodbc.
