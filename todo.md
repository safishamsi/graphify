# todo

## Bugs

- [ ] `aag watch <folder>` fails on the bundled PyInstaller binary with
      `error: watchdog not installed. Run: pip install watchdog`.
      Root cause: `watchdog` is declared an *optional* dep
      (`pyproject.toml:52` → `watch = ["watchdog"]`) and the
      PyInstaller spec's hidden-imports loop is wrapped in
      `try/except Exception: pass` (`graphify.spec:41-46`), so when
      the build venv lacks `watchdog` it gets silently dropped from
      the bundle instead of failing the build. Fix options:
      1. Add `watchdog` to the install_requires (not `[watch]` extra)
         so it's always present.
      2. Or: ensure CI's release build venv installs `.[all]` (the
         release workflow already does `pip install pyinstaller .[all]`
         — check why the resulting binary still doesn't bundle it).
      3. Tighten `graphify.spec` so a missing hidden-import for a
         required runtime feature fails the build instead of warning.
