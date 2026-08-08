"""Schema vector store: index table DDL, retrieve the most relevant tables.

The index is stamped with the database it was built from. Point the app at a
different database and the whole collection is thrown away and rebuilt, so
tables from a previous source can never leak into retrieval.

Rebuild by hand:  python store.py
"""
import hashlib
import json
from pathlib import Path

import chromadb

import db

# PersistentClient saves vectors to disk (folder "chroma_db/").
_PATH = Path("chroma_db")
_NAME = "table_schemas"
_STAMP = _PATH / "index_stamp.json"

_client = chromadb.PersistentClient(path=str(_PATH))

# Chroma rejects very large add() calls, and a real schema is thousands of
# tables, so writes go in chunks.
_BATCH = 500


def _open():
    """Open (or create) the collection. Never cached — index_schema drops it."""
    return _client.get_or_create_collection(
        name=_NAME,
        metadata={"hnsw:space": "cosine"},  # same similarity metric as embed_lab.py
    )


def _digest(tables):
    """Fingerprint of the schema text, so an unchanged schema isn't re-embedded."""
    sha = hashlib.sha256()
    for name, sql in tables:
        sha.update(name.encode())
        sha.update(b"\0")
        sha.update(sql.encode())
        sha.update(b"\0")
    return sha.hexdigest()


def _read_stamp():
    try:
        return json.loads(_STAMP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def index_schema(force=False):
    """Embed each table's CREATE TABLE text. Returns the number of tables indexed."""
    tables = db.get_table_schemas()  # [(name, create_sql), ...]
    if not tables:
        raise RuntimeError("No tables found. Run: python db.py")

    source = db.describe_source()
    digest = _digest(tables)
    stamp = _read_stamp()
    collection = _open()
    if (not force
            and stamp.get("source") == source
            and stamp.get("digest") == digest
            and collection.count() == len(tables)):
        return len(tables)

    # Drop the collection instead of upserting: an upsert would leave behind
    # every table that existed in whatever database was indexed before.
    try:
        _client.delete_collection(_NAME)
    except Exception:  # noqa: BLE001 - nothing to delete on a first run
        pass
    collection = _open()

    ids = [name for name, _sql in tables]
    documents = [sql for _name, sql in tables]
    for start in range(0, len(ids), _BATCH):
        collection.add(ids=ids[start:start + _BATCH],
                       documents=documents[start:start + _BATCH])

    _PATH.mkdir(parents=True, exist_ok=True)
    _STAMP.write_text(
        json.dumps({"source": source, "digest": digest, "tables": len(ids)}),
        encoding="utf-8",
    )
    return len(ids)


def ensure_index():
    """Startup path: index only when the vectors on disk don't match the source.

    Reading a real database's schema is expensive enough that it shouldn't
    happen on every app boot, so a matching stamp is taken at face value.
    Use the sidebar's reindex button after a schema change.
    """
    stamp = _read_stamp()
    if stamp.get("source") == db.describe_source():
        count = _open().count()
        if count and count == stamp.get("tables"):
            return count
    return index_schema(force=True)


def retrieve(question, k=3):
    """Return the top-k CREATE TABLE strings most relevant to the question.

    Flow: question → embed → nearest-neighbor search → matching documents.
    """
    collection = _open()
    total = collection.count()
    if not total:
        raise RuntimeError("Schema index is empty. Run: python store.py")

    results = collection.query(
        query_texts=[question],  # Chroma embeds this for us
        n_results=min(k, total),
    )
    # results["documents"] is a list-of-lists: one inner list per query.
    documents = results["documents"][0]
    return documents


if __name__ == "__main__":
    # Ensure the demo DB exists, then rebuild the vector index and smoke-test.
    if db.DB_KIND == "sqlite":
        db.setup_database()

    count = index_schema(force=True)
    print(f"Indexed {count} tables from {db.describe_source()}")

    question = "how many funded loans are there"
    hits = retrieve(question, k=2)
    print(f'\nTop matches for: "{question}"\n')
    for i, doc in enumerate(hits, start=1):
        print(f"--- #{i} ---")
        print(doc)
        print()
