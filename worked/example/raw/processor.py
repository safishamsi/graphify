"""
Processor module - transforms validated documents into enriched records
ready for storage and retrieval.
"""
import re
from storage import load_index, save_processed



STOPWORDS = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with"}


def normalize_text(text: str) -> str:
    """Lowercase, strip extra whitespace, remove control characters."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x20-\x7e]", "", text)
    return text


def extract_keywords(text: str) -> list:
    """Pull non-stopword tokens from text, deduplicated."""
    tokens = re.findall(r"\b[a-z]{3,}\b", normalize_text(text))
    seen = set()
    keywords = []
    for t in tokens:
        if t not in STOPWORDS and t not in seen:
            seen.add(t)
            keywords.append(t)
    return keywords


def enrich_document(doc: dict) -> dict:
    """Add keyword index and cross-references to a validated document."""
    text_blob = " ".join([
        doc.get("title", ""),
        " ".join(doc.get("sections", [])),
        " ".join(doc.get("paragraphs", [])),
    ])
    doc["keywords"] = extract_keywords(text_blob)
    doc["cross_refs"] = find_cross_references(doc)
    return doc


def find_cross_references(doc: dict) -> list:
    """Look up the index and return IDs of related documents by keyword overlap."""
    index = load_index()
    keywords = set(doc.get("keywords", []))
    refs = []
    for record_id, entry in index.items():
        other_keywords = set(entry.get("keywords", []))
        overlap = keywords & other_keywords
        if len(overlap) >= 3:
            refs.append({"id": record_id, "shared_keywords": list(overlap)})
    return refs


def process_and_save(doc: dict) -> str:
    """Enrich a validated document and persist it. Returns the record ID."""
    enriched = enrich_document(doc)
    record_id = save_processed(enriched)
    return record_id


def reprocess_all() -> int:
    """Re-enrich all records in the index. Returns count of records updated."""
    index = load_index()
    count = 0
    for record_id, doc in index.items():
        process_and_save(doc)
        count += 1
    return count
