"""
Storage module - persists documents to disk and maintains the search index.
All other modules read and write through this interface.
"""

import json
import uuid
from pathlib import Path


STORAGE_DIR = Path(".graphify_store")
INDEX_FILE = STORAGE_DIR / "index.json"


def _ensure_storage() -> None:
    STORAGE_DIR.mkdir(exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(json.dumps({}))


def load_index() -> dict:
    """Load the full document index from disk."""
    _ensure_storage()
    return json.loads(INDEX_FILE.read_text())


def save_index(index: dict) -> None:
    """Persist the index to disk."""
    _ensure_storage()
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def save_parsed(doc: dict) -> str:
    """Write a parsed document to storage. Returns the assigned record ID."""
    _ensure_storage()
    record_id = str(uuid.uuid4())[:8]
    path = STORAGE_DIR / f"{record_id}.json"
    path.write_text(json.dumps(doc, indent=2))

    index = load_index()
    index[record_id] = {
        "source": doc.get("source", ""),
        "format": doc.get("format", ""),
        "title": doc.get("title", ""),
    }
    save_index(index)
    return record_id


def save_processed(doc: dict) -> str:
    """Write an enriched document to storage, updating the index with keywords."""
    _ensure_storage()
    record_id = doc.get("id") or str(uuid.uuid4())[:8]
    path = STORAGE_DIR / f"{record_id}_processed.json"
    path.write_text(json.dumps(doc, indent=2))

    index = load_index()
    if record_id not in index:
        index[record_id] = {}
    index[record_id]["keywords"] = doc.get("keywords", [])
    index[record_id]["cross_refs"] = [r["id"] for r in doc.get("cross_refs", [])]
    save_index(index)
    return record_id


def load_record(record_id: str) -> dict:
    """Fetch a single document by ID."""
    _ensure_storage()
    path = STORAGE_DIR / f"{record_id}.json"
    if not path.exists():
        raise KeyError(f"No record found for ID: {record_id}")
    return json.loads(path.read_text())


def delete_record(record_id: str) -> bool:
    """Remove a document and its index entry. Returns True if it existed."""
    _ensure_storage()
    path = STORAGE_DIR / f"{record_id}.json"
    if not path.exists():
        return False
    path.unlink()
    index = load_index()
    index.pop(record_id, None)
    save_index(index)
    return True


def list_records() -> list:
    """Return all record IDs currently in storage."""
    return list(load_index().keys())
