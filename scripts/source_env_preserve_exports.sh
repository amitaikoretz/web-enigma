#!/usr/bin/env bash
# Source without overwriting variables already set in the environment:
#   . scripts/source_env_preserve_exports.sh [path/to/.env]

env_file="${1:-}"
if [[ -z "$env_file" || ! -f "$env_file" ]]; then
  return 0 2>/dev/null || exit 0
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  case "$line" in
    ''|\#*) continue ;;
  esac
  key="${line%%=*}"
  val="${line#*=}"
  if [[ -z "${!key+x}" ]]; then
    export "$key=$val"
  fi
done < "$env_file"
