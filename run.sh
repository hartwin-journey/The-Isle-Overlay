#!/usr/bin/env sh
set -eu

if [ -x ".venv/bin/python" ]; then
    exec .venv/bin/python app.py
fi

exec python3 app.py
