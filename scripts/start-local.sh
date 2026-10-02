#!/bin/sh
# Source checkout startup. Never requires a copied virtualenv or host-generated .fmt.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
cd "$ROOT"
fail() { printf '%s\n' "$*" >&2; exit 1; }
[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || fail 'Current source runtime supports macOS Apple Silicon only.'
PYTHON=${PYTHON:-python3}
command -v "$PYTHON" >/dev/null 2>&1 || fail 'Python 3.12+ is required; install Python first.'
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ required"'
[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/python -c 'import sys; assert sys.version_info >= (3, 12)' || fail 'Copied or incompatible .venv; create a new virtualenv on this computer (preserve the old directory).'
.venv/bin/python -m pip install -r requirements-app.txt
.venv/bin/python -m scripts.light_runtime
exec .venv/bin/python -m backend "$@"
