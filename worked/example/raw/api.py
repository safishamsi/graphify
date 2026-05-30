"""
API module - exposes the document pipeline over HTTP.
Thin layer over parser, validator, processor, and storage.
"""

from parser import batch_parse, parse_file
from validator import validate_document, ValidationError
from processor import process_and_save, enrich_document
from storage import load_record, delete_record, list_records, load_index


def handle_upload(paths: list) -> dict:
    """
    Accept a list of file paths, run the full pipeline on each,
    and return a summary of what succeeded and what failed.
    """
    results = batch_parse(paths)
    succeeded = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    return {
        "uploaded": len(succeeded),
        "failed": len(failed),
        "ids": [r["id"] for r in succeeded],
        "errors": failed,
    }


def handle_get(record_id: str) -> dict:
    """Fetch a document by ID and return it."""
    try:
        return load_record(record_id)
    except KeyError:
        return {"error": f"Record {record_id} not found"}


def handle_delete(record_id: str) -> dict:
    """Delete a document by ID."""
    deleted = delete_record(record_id)
    if deleted:
        return {"deleted": record_id}
    return {"error": f"Record {record_id} not found"}


def handle_list() -> dict:
    """List all document IDs in storage."""
    return {"records": list_records()}


def handle_search(query: str) -> dict:
    """
    Simple keyword search over the index.
    Returns documents whose keyword list overlaps with the query terms.
    """
    terms = set(query.lower().split())
    index = load_index()
    matches = []
    for record_id, entry in index.items():
        keywords = set(entry.get("keywords", []))
        if terms & keywords:
            matches.append(
                {
                    "id": record_id,
                    "title": entry.get("title", ""),
                    "matched_keywords": list(terms & keywords),
                }
            )
    return {"query": query, "results": matches}


def handle_enrich(record_id: str) -> dict:
    """Re-enrich a document to pick up new cross-references."""
    try:
        doc = load_record(record_id)
    except KeyError:
        return {"error": f"Record {record_id} not found"}
    try:
        validated = validate_document(doc)
    except ValidationError as e:
        return {"error": str(e)}
    enriched_id = process_and_save(validated)
    return {"enriched": enriched_id}
