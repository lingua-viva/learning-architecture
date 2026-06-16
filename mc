#!/bin/bash
# Mission Canvas CLI — entry point
# Usage: mc <intent> <query>
# Intents: protect, research, decide, create, diagnose, reflect, health, stats, cron
exec python3 "$(dirname "$(readlink -f "$0")")/src/mc_cli.py" "$@"
