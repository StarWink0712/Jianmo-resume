"""Compatibility entry point for pre-adapter macOS callers."""
from pathlib import Path
import runpy


if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'platform_adapters/macos_exec.py'), run_name='__main__')
