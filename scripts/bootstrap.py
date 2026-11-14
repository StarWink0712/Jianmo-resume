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
    parser.add_argument('--check-appcontainer', action='store_true')
    parser.add_argument('--no-sandbox', action='store_true')
    options, backend_args = parser.parse_known_args()
    if sys.version_info < (3, 12) or struct.calcsize('P') != 8:
        raise ValueError('需要 Python 3.12 或更高版本的 64 位解释器。')
    from platform_adapters.detect import platform_key
    key = platform_key()
    if options.no_sandbox and (key != 'windows-x64' or options.check_appcontainer):
        parser.error('--no-sandbox 仅用于 Windows x64 本地编译，不能与 --check-appcontainer 同用。')
    if options.check_appcontainer:
        if key != 'windows-x64':
            raise ValueError('--check-appcontainer 需要 Windows x64。')
        import platform
        from platform_adapters.windows_native import AppContainerAccessDenied, app_container
        print(f'Windows {platform.win32_edition()}，Build {sys.getwindowsversion().build}，'
              f'Python {platform.python_version()}（64 位）', flush=True)
        try:
            with app_container(stage='独立检查'):
                pass
        except AppContainerAccessDenied as error:
            raise SystemExit(f'检查失败：{error}\n请在 issue 中附上这两行输出。'
                             '如有其他本地账户，可用相同命令对照。') from error
        print('检查通过：当前账户已成功创建并删除临时 AppContainer。')
        return 0
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
        from platform_adapters.windows_native import AppContainerAccessDenied
        from scripts.install_windows_runtime import install
        try:
            prefix = 'windows-local' if options.no_sandbox else 'windows-install'
            runtime = install(ROOT / '.m1-build' / prefix, ROOT / '.m1-build/engine-cache', options.offline,
                              no_sandbox=options.no_sandbox)
        except AppContainerAccessDenied as error:
            raise SystemExit(f'启动失败：{error}\n请在项目目录用同一账户运行 '
                             'py -3 scripts/bootstrap.py --check-appcontainer 检查权限，或加 --no-sandbox 本地编译。') from error
    else:
        from scripts.light_runtime import install
        install(ROOT / '.m1-build/local-install', ROOT / '.m1-build/engine-cache', options.offline)
        runtime = ROOT / '.m1-build/local-install/current'
    if options.setup_only:
        print('环境已准备好：' + str(runtime), flush=True)
        return 0
    # Run the server in this interpreter so Ctrl+C reaches its graceful shutdown
    # and its data-directory lease lives exactly as long as the server does.
    if options.no_sandbox:
        backend_args.append('--no-sandbox')
    sys.argv = ['backend', '--runtime', str(runtime), *backend_args]
    from backend.__main__ import main as serve
    serve()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit('启动失败：' + str(error)) from error
