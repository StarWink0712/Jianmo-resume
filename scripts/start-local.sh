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
if ! command -v kpsewhich >/dev/null 2>&1; then
    PATH="/Library/TeX/texbin:$PATH"
    export PATH
fi
[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/python -c 'import sys; assert sys.version_info >= (3, 12)' || fail 'Copied or incompatible .venv; create a new virtualenv on this computer (preserve the old directory).'
.venv/bin/python -m pip install -r requirements-app.txt
RUNTIME="$ROOT/.m1-build/local-install/current"
# Existing valid installs need no TeX rebuild; source rendering remains in this checkout.
if [ ! -x "$RUNTIME/resume-runtime" ] || ! .venv/bin/python -c 'import hashlib,json,sys; from pathlib import Path; p=Path(sys.argv[1]); assert json.loads(p.read_text()).get("baseline_sha256")==hashlib.sha256(Path("docs/m1/runtime-inputs.json").read_bytes()).hexdigest()' "$RUNTIME/runtime.json"; then
    command -v kpsewhich >/dev/null 2>&1 || fail 'TeX Live 2026 is required for a source build. See README prerequisites.'
    command -v xelatex >/dev/null 2>&1 || fail 'xelatex is missing from PATH; check the TeX Live installation.'
    command -v brew >/dev/null 2>&1 || fail 'Full runtime packaging currently requires Homebrew Python dependencies; see README.'
    .venv/bin/python -m pip install -r requirements-build.txt
    .venv/bin/python -m experiments.m1.build_runtime
    /bin/sh output/runtime/install-runtime.sh --prefix "$ROOT/.m1-build/local-install"
fi
"$RUNTIME/resume-runtime" verify
exec .venv/bin/python -m backend "$@"
