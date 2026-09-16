# justdata

Ask your database in plain English. The app retrieves relevant table schemas,
has Claude write a read-only SQL query, runs it, and shows the result.

## What it does

justdata lets people who don't write SQL query a database safely. You type a
question like "how many funded loans are there", and the app:

1. **Retrieves** the most relevant table schemas from a ChromaDB vector index
   (so it works on databases with hundreds of tables without blowing the
   context window).
2. **Generates** one read-only SQL query with Claude, in the right dialect
   (SQLite or T-SQL).
3. **Runs** it and shows the rows, with an optional plain-English summary of
   the answer.

Safety is layered in: only `SELECT`/`WITH` statements pass the guard, results
are row-capped (`MAX_ROWS`), SQL Server queries get a timeout, and the
recommended setup is a read-only database user.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # add ANTHROPIC_API_KEY
.\run.ps1
```

Open http://localhost:8501

## Config

| Env var | Purpose |
|---------|---------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `CLAUDE_MODEL` | Model id (default `claude-sonnet-5`) |
| `DB_KIND` | `sqlite` (demo) or `mssql` |
| `SQLITE_FILE` | Demo DB path (default `demo.db`) |
| `MSSQL_CONN_STR` | Read-only SQL Server connection string |
| `MAX_ROWS` | Row cap per answer (default `500`) |
| `QUERY_TIMEOUT` | SQL Server timeout seconds (default `30`) |

## Layout

- **Left rail** — brand, New chat, Recents (SQLite-backed), Reindex
- **Main** — empty-state greeting or chat transcript
- **Chat bar** — `→` to send; `■` to stop while generating

## Project map

| File | Role |
|------|------|
| `app.py` | Streamlit UI |
| `db.py` | SQLite / SQL Server access + demo seed |
| `llm.py` | Claude SQL generation + optional summarize |
| `store.py` | ChromaDB schema embeddings / retrieval |
| `recents.py` | Local frequent-query store (`recents.db`) |
| `run.ps1` | Kill port 8501 and start Streamlit |

## Notes

- Only `SELECT` / `WITH` queries are allowed through the UI.
- `chroma_db/`, `recents.db`, `demo.db`, `.env`, and `.venv/` are local artifacts and are gitignored.
- After schema changes on a live DB, use **Reindex schema** in the left rail.
