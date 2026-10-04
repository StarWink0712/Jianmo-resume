import argparse
from pathlib import Path
import socket

import uvicorn

from backend.app import create_app
from backend.domain import AppError
from platform_adapters.detect import get_adapter
from scripts.check_contracts import ROOT


def main():
    parser = argparse.ArgumentParser(description='Local resume backend, M2 developer build')
    parser.add_argument('--port', type=int, default=8770)
    parser.add_argument('--data-dir', type=Path, default=ROOT / '.local-data')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--no-examples', action='store_true', help='Start a new data directory without bundled reference resumes.')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    listener = socket.socket()
    try:
        adapter = get_adapter()
        adapter.initialize_process()
        if args.runtime is None:
            from core.managed_runtime import default_runtime
            args.runtime = default_runtime()
        adapter.configure_listener(listener)
        listener.bind(('127.0.0.1', args.port))
        # Claim the port before opening the database, including simultaneous starts.
        listener.listen(128)
        app = create_app(args.data_dir, args.runtime, origin=f'http://127.0.0.1:{args.port}', seed_examples=not args.no_examples)
    except (OSError, AppError, ValueError) as error:
        listener.close()
        raise SystemExit('无法启动本地服务，请检查端口、数据目录或专用运行时：' + str(error))
    print(f'本地简历：http://127.0.0.1:{args.port} （仅本机访问）', flush=True)
    config = uvicorn.Config(app, host='127.0.0.1', port=args.port, access_log=False,
                            proxy_headers=False, log_level='warning', timeout_graceful_shutdown=45)
    try:
        uvicorn.Server(config).run(sockets=[listener])
    except KeyboardInterrupt:
        pass
    finally:
        app.state.service.close()
        listener.close()


if __name__ == '__main__':
    main()
