#!/usr/bin/env bash
set -euo pipefail

pyinstaller --onefile --name backend \
  --add-data "prompts:prompts" \
  server.py
