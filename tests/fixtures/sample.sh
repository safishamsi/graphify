#!/usr/bin/env bash
set -euo pipefail

source ./lib.sh

deploy() {
  build_artifact
}

main() {
  deploy "$@"
}

main "$@"
