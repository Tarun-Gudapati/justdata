from dotenv import load_dotenv
import os
import anthropic

import db

load_dotenv()
client = anthropic.Anthropic()

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
# Anthropic requires max_tokens; don't artificially pin it low.
MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "8192"))

# Running totals across all API calls this run (both SQL gen + summarize).
usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}


def _track_usage(response):
    usage["input_tokens"] += response.usage.input_tokens
    usage["output_tokens"] += response.usage.output_tokens
    usage["calls"] += 1


def _response_text(response):
    """Pull the text block out of a Claude response.

    Sonnet 5 can emit a ThinkingBlock first (or *only* a ThinkingBlock if
    the reply is truncated). We only want the final text.
    """
    text_blocks = [b for b in response.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        kinds = [getattr(b, "type", type(b).__name__) for b in response.content]
        raise RuntimeError(
            f"No text in response (blocks={kinds}, stop_reason={response.stop_reason}). "
            "The model used its token budget on thinking and never wrote an answer."
        )
    return text_blocks[0].text.strip()


def _ask(prompt, retries=1):
    """Call Claude and return text. Retries once if thinking ate the whole reply."""
    last_err = None
    for _ in range(retries + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            # NL→SQL doesn't need extended thinking — it burns tokens and
            # sometimes returns *only* a ThinkingBlock (no SQL text).
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}],
        )
        _track_usage(response)
        try:
            return _response_text(response)
        except RuntimeError as err:
            last_err = err
    raise last_err


def generate_sql(schema, question, dialect=None):
    dialect = dialect or db.get_dialect()
    prompt = f"""You are an expert at writing {dialect} SQL queries.
Given the database schema below, write ONE {dialect} SQL query that answers the question.

Schema:
{schema}

Question: {question}

Rules:
- Return ONLY the raw SQL query.
- Use valid {dialect} syntax (for SQL Server use TOP, not LIMIT).
- Write a read-only SELECT query only.
- No explanation, no comments, no markdown code fences.
"""
    return _ask(prompt)


def summarize_answer(question, sql, rows, truncated=False):
    """Turn raw result rows into a one-sentence human answer.

    Second LLM call: give Claude the question + SQL + rows, ask for
    a plain-English sentence instead of showing the user [(3,)].

    `truncated` means the row cap cut the result short, so the answer must not
    be phrased as a complete total.
    """
    limit_note = (
        "\nThese are only the first rows of a larger result. Say the list is "
        "partial; do not state a total or a count.\n" if truncated else ""
    )
    prompt = f"""A user asked a question about a database. A SQL query was run
and returned these rows. Answer the user's question in ONE short, friendly
sentence using only this data. Do not mention SQL or tables.
{limit_note}
Question: {question}
SQL that ran: {sql}
Rows returned: {rows}
"""
    return _ask(prompt)


if __name__ == "__main__":
    schema = """
    CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, created_at TEXT);
    CREATE TABLE loans (id INTEGER PRIMARY KEY, customer_id INTEGER,
                        amount REAL, status INTEGER, funded_at TEXT);
    """
    question = "How many loans are funded? (funded means status = 3)"
    print(generate_sql(schema, question))
