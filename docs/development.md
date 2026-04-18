# depOS — development

## Requirements

- Python 3.10+
- Dependencies from [pyproject.toml](../pyproject.toml)

## Install (editable)

From the repository root:

```bash
pip install -e .
pip install -e ".[depos]"   # depOS API, fusion, blast (FastAPI, SQLAlchemy, Pydantic)
pip install -e ".[all]"    # optional graphify extras
```

## Tests

```bash
pytest tests/ -q
```

## Package note

The published distribution may still be named `graphifyy` on PyPI historically; depOS may introduce a separate package name in a future release. CLI entry point: `graphify`.
