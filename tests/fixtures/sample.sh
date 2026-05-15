#!/usr/bin/env bash
set -euo pipefail

source ./helpers.sh

export APP_ENV="production"

build() {
    echo "Building..."
    local out_dir="dist"
    mkdir -p "$out_dir"
}

test_suite() {
    echo "Running tests..."
    build
}

deploy() {
    build
    test_suite
    echo "Deploying to $APP_ENV"
}
