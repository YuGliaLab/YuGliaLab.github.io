#!/bin/bash
cd "$(dirname "$0")"
if ! command -v node >/dev/null || ! command -v python3 >/dev/null; then
  echo "Install Node.js and Python 3, then reopen this launcher."
  read -r -p "Press Enter to close."
  exit 1
fi
python3 local-cms/server.py
read -r -p "Press Enter to close."
