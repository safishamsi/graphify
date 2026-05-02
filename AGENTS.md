# Graphify Fork Operating Notes

This repository is Mase's fork of upstream Graphify.

## Remotes

- `origin`: `https://github.com/matzls/graphify.git`
- `upstream`: `https://github.com/safishamsi/graphify.git`

Keep upstream mirror branches such as `v6` clean. Put local customizations on
`mase/local-fixes` unless a task explicitly creates a narrower PR branch.

## Local Development

- Do not patch the uv tool site-packages copy directly.
- Make source changes in this repository.
- Run targeted tests before reinstalling the active CLI.
- Install the active CLI from this checkout when local fixes should be used:

```bash
uv tool install --force --reinstall /Users/mase/Codebase/Personal-Projects/graphify \
  --with faster-whisper \
  --with yt-dlp \
  --with watchdog
```

## Upstream Sync

To take upstream changes while preserving local fixes:

```bash
git fetch upstream
git checkout v6
git merge --ff-only upstream/v6
git checkout mase/local-fixes
git rebase v6
uv run pytest tests/test_watch.py tests/test_transcribe.py tests/test_hooks.py
uv tool install --force --reinstall /Users/mase/Codebase/Personal-Projects/graphify \
  --with faster-whisper \
  --with yt-dlp \
  --with watchdog
```

If upstream includes equivalent fixes, drop the matching local commits from
`mase/local-fixes`.

## Local Patch Goals

Current local fixes should stay small and upstream-friendly:

- Preserve semantic community labels during code-only rebuilds.
- Avoid transcript filename collisions for same-stem media files.

Prefer tests in `tests/test_watch.py`, `tests/test_transcribe.py`, and
`tests/test_hooks.py` for these patches.
