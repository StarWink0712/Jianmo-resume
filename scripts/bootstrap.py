"""Prepare the source checkout and launch the local application without activation."""

import argparse
import importlib.metadata
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def required_packages(path):
    result = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('-r '):
            result.update(required_packages(path.parent / line[3:].strip()))
        else:
            name, version = line.split('==', 1)
            result[name] = version
    return result


def dependencies_ready():
    for name, expected in required_packages(ROOT / 'requirements-app.txt').items():
        try:
            if importlib.metadata.version(name) != expected:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--setup-only', action='store_true')
    options, backend_args = parser.parse_known_args()
    if sys.version_info < (3, 12) or struct.calcsize('P') != 8:
        raise ValueError('需要 Python 3.12 或更高版本的 64 位解释器。')
    from platform_adapters.detect import platform_key
    key = platform_key()
    python = ROOT / ('.venv/Scripts/python.exe' if key == 'windows-x64' else '.venv/bin/python')
    if Path(sys.executable).absolute() != python.absolute():
        if not python.exists():
            if (ROOT / '.venv').exists():
                raise ValueError('现有 .venv 与本机不兼容，请保留旧目录后重新创建；不能跨系统复制虚拟环境。')
            subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], check=True)
        return subprocess.call([str(python), str(Path(__file__)), *sys.argv[1:]], cwd=ROOT)
    if not dependencies_ready():
        if options.offline:
            raise ValueError('离线启动所需的 Python 依赖缺失；请先联网运行一次启动命令。')
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                        '-r', str(ROOT / 'requirements-app.txt')], cwd=ROOT, check=True)
    if key == 'windows-x64':
        from scripts.install_windows_runtime import install
        runtime = install(ROOT / '.m1-build/windows-install', ROOT / '.m1-build/engine-cache', options.offline)
    else:
        from scripts.light_runtime import install
        install(ROOT / '.m1-build/local-install', ROOT / '.m1-build/engine-cache', options.offline)
        runtime = ROOT / '.m1-build/local-install/current'
    if options.setup_only:
        print('环境已准备好：' + str(runtime), flush=True)
        return 0
    # Run the server in this interpreter so Ctrl+C reaches its graceful shutdown
    # and its data-directory lease lives exactly as long as the server does.
    sys.argv = ['backend', '--runtime', str(runtime), *backend_args]
    from backend.__main__ import main as serve
    serve()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit('启动失败：' + str(error)) from error
