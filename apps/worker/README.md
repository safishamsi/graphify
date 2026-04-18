# depOS worker

Snapshot and CI jobs run the **`depos`** Python package:

- `python -c "from depos.snapshot import build_graph_for_root; ..."` for local graphs.
- `depos-api` (see `pyproject.toml`) starts the FastAPI service used by CI and the dashboard.

Heavy clone/fan-out workers can be added here as separate processes calling the same library.
