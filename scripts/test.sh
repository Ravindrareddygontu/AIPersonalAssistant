#!/bin/bash
# Test runner script with options for fast/slow tests
#
# Usage:
#   ./scripts/test.sh          # Run fast tests only (default)
#   ./scripts/test.sh fast     # Run fast tests only  
#   ./scripts/test.sh slow     # Run slow/integration tests only
#   ./scripts/test.sh all      # Run all tests
#   ./scripts/test.sh <file>   # Run specific test file

set -e

cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

MODE="${1:-fast}"

case "$MODE" in
    fast)
        echo "🚀 Running FAST tests (290 tests, ~1 second)..."
        python -m pytest tests/ -m "not slow" -q "${@:2}"
        ;;
    slow)
        echo "🐢 Running SLOW/integration tests (6 tests, ~6 minutes)..."
        python -m pytest tests/ -m "slow" -v "${@:2}"
        ;;
    all)
        echo "🔄 Running ALL tests (296 tests, ~6 minutes)..."
        python -m pytest tests/ -v "${@:2}"
        ;;
    *)
        # Assume it's a file path or pytest args
        echo "🧪 Running: pytest $@"
        python -m pytest "$@"
        ;;
esac

