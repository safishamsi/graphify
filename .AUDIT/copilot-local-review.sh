#!/usr/bin/env bash
set -uo pipefail
# Owner: Codex
#
# Private local gate: run GitHub Copilot CLI against the staged diff before a
# local commit. This is an early-warning review, not a replacement for the
# origin/upstream PR review gate.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT" || exit 2

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

if [[ "${AUDIT_PRIVATE_GUARD:-1}" != "0" && -x "$SCRIPT_DIR/private-guard.sh" ]]; then
  "$SCRIPT_DIR/private-guard.sh" --quiet || exit "$?"
fi

usage() {
  cat <<'EOF'
Usage: .AUDIT/copilot-local-review.sh [--cached|--worktree|--base <ref>] [--advisory] [--max-diff-bytes <n>]

Runs GitHub Copilot CLI against a local diff and blocks when Copilot reports
actionable findings.

Modes:
  --cached        review staged changes; default and intended for pre-commit
  --worktree      review unstaged worktree changes
  --base <ref>    review changes from merge-base(<ref>, HEAD) to HEAD
  --advisory      always exit 0 after saving/reporting review output

Environment:
  AUDIT_COPILOT_MAX_DIFF_BYTES  default 120000; local review blocks above this
  AUDIT_COPILOT_REPORT_DIR      default .AUDIT/reports

Output contract:
  Copilot must emit exactly one decision line:
    LOCAL_COPILOT_REVIEW_DECISION: PASS
    LOCAL_COPILOT_REVIEW_DECISION: BLOCK

PASS means no actionable correctness/security/regression/test issue was found.
BLOCK or ambiguous output stops the commit gate.
EOF
}

mode="cached"
base_ref=""
advisory=0
max_diff_bytes="${AUDIT_COPILOT_MAX_DIFF_BYTES:-2000000}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cached)
      mode="cached"
      ;;
    --worktree)
      mode="worktree"
      ;;
    --base)
      if [[ $# -lt 2 ]]; then
        echo "[copilot-local-review] USAGE_ERROR: --base requires a ref" >&2
        exit 2
      fi
      mode="base"
      base_ref="$2"
      shift
      ;;
    --base=*)
      mode="base"
      base_ref="${1#--base=}"
      ;;
    --advisory)
      advisory=1
      ;;
    --max-diff-bytes)
      if [[ $# -lt 2 ]]; then
        echo "[copilot-local-review] USAGE_ERROR: --max-diff-bytes requires a number" >&2
        exit 2
      fi
      max_diff_bytes="$2"
      shift
      ;;
    --max-diff-bytes=*)
      max_diff_bytes="${1#--max-diff-bytes=}"
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "[copilot-local-review] USAGE_ERROR: unknown option '$1'" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

case "$max_diff_bytes" in
  ''|*[!0-9]*)
    echo "[copilot-local-review] USAGE_ERROR: max diff bytes must be a non-negative integer" >&2
    exit 2
    ;;
esac

if ! command -v copilot >/dev/null 2>&1; then
  echo "[copilot-local-review] BLOCKED: GitHub Copilot CLI is not installed or not on PATH" >&2
  echo "[copilot-local-review] Install/authenticate Copilot CLI or set AUDIT_SKIP_LOCAL_COPILOT=1 for an explicit bypass." >&2
  exit 1
fi

diff_file="$(mktemp)"
stat_file="$(mktemp)"
trap 'rm -f "$diff_file" "$stat_file"' EXIT

if [[ "$mode" == "cached" ]]; then
  git diff --cached --stat >"$stat_file"
  git diff --cached --no-ext-diff --binary --unified=80 >"$diff_file"
elif [[ "$mode" == "worktree" ]]; then
  git diff --stat >"$stat_file"
  git diff --no-ext-diff --binary --unified=80 >"$diff_file"
else
  merge_base="$(git merge-base HEAD "$base_ref")" || {
    echo "[copilot-local-review] GIT_CONTEXT_ERROR: could not merge-base HEAD and $base_ref" >&2
    exit 2
  }
  git diff --stat "$merge_base..HEAD" >"$stat_file"
  git diff --no-ext-diff --binary --unified=80 "$merge_base..HEAD" >"$diff_file"
fi

if [[ ! -s "$diff_file" ]]; then
  echo "[copilot-local-review] clean: no diff to review for mode=$mode"
  exit 0
fi

if grep -Eq '^(Binary files |GIT binary patch)' "$diff_file"; then
  echo "[copilot-local-review] BLOCKED: binary diff present; Copilot local text review cannot inspect it reliably" >&2
  exit 1
fi

diff_bytes="$(wc -c <"$diff_file" | tr -d '[:space:]')"
if (( max_diff_bytes > 0 && diff_bytes > max_diff_bytes )); then
  echo "[copilot-local-review] BLOCKED: diff is ${diff_bytes} bytes, above local review limit ${max_diff_bytes}" >&2
  echo "[copilot-local-review] Split the commit or use origin PR review as the authoritative review surface." >&2
  exit 1
fi

report_dir="${AUDIT_COPILOT_REPORT_DIR:-$SCRIPT_DIR/reports}"
mkdir -p "$report_dir"
report_file="$report_dir/$(date +%Y%m%d-%H%M%S)-copilot-local-review.md"

prompt_file="$(mktemp)"
trap 'rm -f "$diff_file" "$stat_file" "$prompt_file"' EXIT

{
  cat <<'EOF'
You are GitHub Copilot reviewing a local staged diff before commit.

Review only the supplied diff. Do not edit files. Do not run tools. Do not ask
questions. Focus on correctness, security, data loss, regression risk, broken
tests, missing tests for changed behavior, and user-visible behavior. Ignore
pure style unless it can create functional risk.

Your response MUST include exactly one decision line:

LOCAL_COPILOT_REVIEW_DECISION: PASS

or:

LOCAL_COPILOT_REVIEW_DECISION: BLOCK

Use PASS only if you find no actionable issue. Use BLOCK if there is any
actionable issue or if the diff is too incomplete to review safely.

After the decision line, provide concise findings with file/path references
when blocking. If passing, provide a brief explanation of the risk areas you
checked.

Diff stat:
EOF
  cat "$stat_file"
  printf '\nDiff:\n```diff\n'
  cat "$diff_file"
  printf '\n```\n'
} >"$prompt_file"

echo "[copilot-local-review] invoking Copilot CLI mode=$mode diff_bytes=$diff_bytes"
set +e
copilot_output="$(
  copilot \
    -p "$(cat "$prompt_file")" \
    --disable-builtin-mcps \
    --disallow-temp-dir \
    --no-color \
    --output-format text 2>&1
)"
copilot_rc=$?
set -e

{
  echo "# Local Copilot Review"
  echo
  echo "- Mode: \`$mode\`"
  [[ -n "$base_ref" ]] && echo "- Base: \`$base_ref\`"
  echo "- Diff bytes: \`$diff_bytes\`"
  echo "- Copilot exit code: \`$copilot_rc\`"
  echo "- Started: \`$(date -u +%Y-%m-%dT%H:%M:%SZ)\`"
  echo
  echo "## Diff Stat"
  echo
  echo '```text'
  cat "$stat_file"
  echo '```'
  echo
  echo "## Copilot Output"
  echo
  echo '```text'
  printf '%s\n' "$copilot_output"
  echo '```'
} >"$report_file"

printf '%s\n' "$copilot_output"
echo "[copilot-local-review] report=$report_file"

if (( advisory == 1 )); then
  echo "[copilot-local-review] advisory mode: not blocking"
  exit 0
fi

if (( copilot_rc != 0 )); then
  echo "[copilot-local-review] BLOCKED: Copilot CLI exited $copilot_rc" >&2
  exit 1
fi

pass_count="$(grep -c '^LOCAL_COPILOT_REVIEW_DECISION: PASS$' "$report_file" || true)"
block_count="$(grep -c '^LOCAL_COPILOT_REVIEW_DECISION: BLOCK$' "$report_file" || true)"

if [[ "$pass_count" == "1" && "$block_count" == "0" ]]; then
  echo "[copilot-local-review] clean: Copilot returned PASS"
  exit 0
fi

if [[ "$block_count" != "0" ]]; then
  echo "[copilot-local-review] BLOCKED: Copilot returned BLOCK" >&2
  exit 1
fi

echo "[copilot-local-review] BLOCKED: Copilot output did not contain the required PASS decision line" >&2
exit 1
