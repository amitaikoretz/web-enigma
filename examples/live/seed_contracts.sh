#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
NOW="${NOW:-$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")}"
END="${END:-$(date -u -v+7d +"%Y-%m-%dT%H:%M:%S+00:00" 2>/dev/null || date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%S+00:00")}"

curl -fsS -X POST "${API_BASE_URL}/trading-contracts" \
  -H 'Content-Type: application/json' \
  -d "{
    \"symbol\": \"AAPL\",
    \"strategy\": \"buy_and_hold\",
    \"strategy_params\": {\"stake\": 1},
    \"start_datetime\": \"${NOW}\",
    \"end_datetime\": \"${END}\",
    \"maximum_trade_size\": 1000,
    \"total_invested\": 2500
  }"

echo
echo "Seeded active trading contract at ${API_BASE_URL}"
