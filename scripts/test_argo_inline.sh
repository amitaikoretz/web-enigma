#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"

curl -sS -X POST "${API_URL}/backtests/argo" \
  -H 'Content-Type: application/json' \
  -d @- <<'JSON'
{
  "format": "yaml",
  "split_by": "symbol_strategy",
  "config_text": "runs:\n  - run_id: test1\n    start_date: 2024-01-01\n    end_date: 2024-01-31\n    data:\n      type: alpaca\n      symbol: AAPL\n      interval: 1d\n      feed: iex\n    strategy: buy_and_hold\n    strategy_params: {}\n"
}
JSON

echo
