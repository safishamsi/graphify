"""
Validator module - checks that parsed documents meet schema requirements
before they are allowed into storage.
"""

from processor import normalize_text


REQUIRED_FIELDS = {"source", "format"}
MAX_TITLE_LENGTH = 200
ALLOWED_FORMATS = {"markdown", "plaintext", "json"}


class ValidationError(Exception):
    pass


def validate_document(doc: dict) -> dict:
    """Run all validation checks on a parsed document. Raises ValidationError on failure."""
    check_required_fields(doc)
    check_format(doc)
    doc = normalize_fields(doc)
    return doc


def check_required_fields(doc: dict) -> None:
    """Raise if any required field is missing."""
    missing = REQUIRED_FIELDS - doc.keys()
    if missing:
        raise ValidationError(f"Missing required fields: {missing}")


def check_format(doc: dict) -> None:
    """Raise if the format is not in the allowed list."""
    fmt = doc.get("format", "")
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError(f"Unknown format: {fmt}. Allowed: {ALLOWED_FORMATS}")


def normalize_fields(doc: dict) -> dict:
    """Clean up text fields using the processor."""
    if "title" in doc:
        doc["title"] = normalize_text(doc["title"])
        if len(doc["title"]) > MAX_TITLE_LENGTH:
            doc["title"] = doc["title"][:MAX_TITLE_LENGTH]
    if "paragraphs" in doc:
        doc["paragraphs"] = [normalize_text(p) for p in doc["paragraphs"]]
    if "sections" in doc:
        doc["sections"] = [normalize_text(s) for s in doc["sections"]]
    return doc


def validate_batch(docs: list) -> tuple:
    """Validate a list of documents. Returns (valid_docs, errors)."""
    valid = []
    errors = []
    for doc in docs:
        try:
            valid.append(validate_document(doc))
        except ValidationError as e:
            errors.append({"doc": doc.get("source", "unknown"), "error": str(e)})
    return valid, errors
