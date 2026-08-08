"""NL → SQL end-to-end, with RAG schema retrieval.

Usage:
  python main.py how many funded loans are there
"""
import sys

import db
import llm
import store

# Only re-embeds when the schema (or the database it came from) has changed.
store.index_schema()

question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "how many funded loans are there"

# RAG step: only the most relevant table schemas go into Claude's prompt.
relevant_schemas = store.retrieve(question, k=3)
schema = "\n\n".join(relevant_schemas)

print("Question:", question)
print("\nRetrieved schema:\n")
print(schema)
print()

sql = llm.generate_sql(schema, question)
print("Generated SQL:", sql)

rows = db.run_sql(sql)  # raises if the SQL isn't a single SELECT
print("Result:", rows)

answer = llm.summarize_answer(question, sql, rows)
print("\nAnswer:", answer)

u = llm.usage
print(f"\nAPI usage: {u['calls']} calls, "
      f"{u['input_tokens']} input + {u['output_tokens']} output tokens")
