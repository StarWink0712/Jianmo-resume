# Lightweight TeX Runtime

Windows development uses the separate `locks/windows-x64.prototype.json` and
`scripts/probe_windows_engine.py`. That lock records upstream archive hashes,
eight selected native EXE/DLL files and the static PE import closure; it is not
approved for production. The three archives total 11,755,948 bytes. Actual DLL
loads are now checked through debug events; Microsoft runtime redistribution
obligations and the full production acceptance still need review.
Downloaded executables remain ignored local build outputs. See
[native Windows progress](../work-logs/2026-10-04-windows-application.md).

The Windows source-build installer is `scripts/install_windows_runtime.py`.
It uses immutable releases and `current.json`, verifies native PDF fixtures before
activation, and supports `--offline` with a populated engine cache. Launch with
`scripts/start-local.ps1` or `py -3 scripts/bootstrap.py`. The backend verifies the
installed manifest and build identity before granting compiler access. Published
binary redistribution and wider Windows certification are separate from this
locally tested source build. The macOS-specific instructions remain below.

The normal startup command is `sh scripts/start-local.sh`. Only Python 3.12+ and macOS Apple Silicon are required; no system TeX, Homebrew libraries, PyInstaller or compiler toolchain is used by setup.

## Included and Downloaded Files

- `tex-support.tar.xz`: necessary macro/format inputs, CMap, Latin Modern initialization fonts, original source files and notices. No executable or pre-generated host format is included.
- `support-inventory.json`: readable per-file SHA-256 inventory and TeX package provenance. The same inventory is embedded in the support archive.
- `tex.lock.json`: approved baseline, archive sizes and hashes, and exact engine members to extract.
- Noto fonts are reused from `assets/fonts/`, not downloaded or duplicated in the support archive.

The active `tex/texmf-dist` contains only the document compilation closure. Format-only inputs are stored in `format-sources/` and copied into the search tree only while generating the format. Supplementary sources and notices live under `licenses/texlive/`, outside Kpathsea's search paths, so preserving source provenance does not slow down normal compilation.

The installer downloads only the original TeX Live `xetex.universal-darwin` and `dvipdfmx.universal-darwin` archives: 16,242,404 bytes in total. It extracts only `xetex` (invoked as `xelatex`) and `xdvipdfmx`. Unsafe shell wrappers, other executables and the rest of TeX Live are not installed. Upstream universal binaries are retained byte-for-byte; this application currently supports only their arm64 execution path.

Current CTAN mirrors are attempted for speed, with a dated **2026-03-23** historical snapshot as fallback. Every mirror must supply the same SHA-512 from the original TeX Live package metadata; an upstream update never becomes an automatic engine upgrade. Extracted executables also must match the approved M1 SHA-256 baseline. HTTPS redirects to HTTP are refused. No GitHub Release address or mutable remote checksum is trusted.

## Installation and Offline Use

Setup installs to `.m1-build/local-install/`, preserving older releases and switching `current` only after source/font/inventory checks and real PDF self-tests pass. It generates `xelatex.fmt` from the bundled approved sources in a network-disabled sandbox, never from a system format cache. A failed download, corrupt package, format failure or PDF failure cannot activate a partial installation.

Once Python dependencies and the runtime are installed, start offline with:

```bash
.venv/bin/python -m backend
```

For a second Mac without access to the TeX download mirrors, copy the verified `.m1-build/engine-cache/` from an installed copy of the same version, preserving filenames. After preparing Python dependencies, run:

```bash
.venv/bin/python -m scripts.light_runtime --offline --cache-dir /path/to/engine-cache
.venv/bin/python -m backend
```

Do not copy `.venv` between computers. Engine cache entries are checked even in offline mode. Cache and installed runtime directories are private build outputs and are not committed to Git. An unavailable mirror is an installation error, not a reason to bypass hashes or install full MacTeX.

## Sources and Licenses

The project does **not** redistribute engine executables or the former frozen Python bundle. Users obtain the unmodified native packages directly from TeX Live mirrors or its dated archive. Engine source distribution remains with upstream: [TeX Live sources](https://tug.org/texlive/svn/) and [TeX Live licensing](https://tug.org/texlive/copying.html). Locally downloaded archives should not be re-uploaded as a project release without addressing their separate source-distribution obligations.

The support archive preserves original source headers, relevant package source files (`.dtx`, `.ins`, etc.), original license/readme/manifest files, `LICENSE.TL`, `LICENSE.CTAN`, and package metadata. The inventory lists each owning package and its recorded license. Packages with no catalogue label retain their own source-header terms; the project's MIT license does not replace them. LaTeX packages use their original LPPL/MIT/etc. terms, hyphenation inputs keep their original notices, Latin Modern retains GUST Font License, and Noto retains OFL. No third-party source is edited or renamed.

## Maintainer Rebuild

Only rebuilding the support archive requires a TeX tree matching the approved source baseline:

```bash
.venv/bin/python -m scripts.build_light_runtime
.venv/bin/python -m scripts.light_runtime
.venv/bin/python -m scripts.check_light_runtime --fresh-startup
.venv/bin/python scripts/check_pre_push.py --full
```

The builder refuses stale M1 evidence or changed source hashes. It produces deterministic file contents and archive metadata. New engine/source versions still require the formal [baseline review](../docs/m1/tex-baseline-update.md); never replace one hash to accept an arbitrary machine's TeX installation. The legacy frozen builder remains a maintainer experiment, not the normal installation path.
