"""Opt-in real network acceptance; unavailable host controls are failures.

Only DNS and TCP handshakes to www.python.org are used. No resume data is sent.
The disposable Python/AppContainer harness is shared with native developer tests.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]


def run():
    from test_windows_native import WindowsNativeTests
    report = {'schema': 1, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'application_ready': False, 'checks': {}, 'passed': False,
              'scope': 'IPv4 DNS/public TCP/local LAN; loopback covered by native suite',
              'unverified': ['IPv6', 'remote LAN peer']}
    WindowsNativeTests.setUpClass()
    probe = WindowsNativeTests()
    try:
        probe.setUp()
        host = 'www.python.org'
        address = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        with socket.create_connection((address, 443), timeout=5):
            pass
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect((address, 443))
            local = route.getsockname()[0]
        if local.startswith('127.') or local == '0.0.0.0':
            raise ValueError('No usable LAN interface for the positive control.')
        with socket.socket() as listener:
            listener.bind((local, 0))
            listener.listen(4)
            port = listener.getsockname()[1]

            def positive_lan():
                with socket.create_connection((local, port), timeout=2):
                    accepted, _ = listener.accept()
                    accepted.close()

            positive_lan()
            source = f'''import socket,json
results={{}}
try:socket.getaddrinfo({host!r},443,socket.AF_INET,socket.SOCK_STREAM)
except socket.gaierror as e:results['dns']={{'blocked':True,'error':e.errno}}
else:results['dns']={{'blocked':False}}
for name,endpoint in [('public_tcp',({address!r},443)),('local_lan',({local!r},{port}))]:
 s=socket.socket();s.settimeout(2)
 try:s.connect(endpoint)
 except (PermissionError,TimeoutError) as e:results[name]={{'blocked':True,'error':getattr(e,'winerror',None) or e.errno}}
 else:results[name]={{'blocked':False}}
 finally:s.close()
print(json.dumps(results))
assert all(value['blocked'] for value in results.values())
'''
            result, log = probe.run_probe(source, timeout=12)
            if result['reason'] != 'success':
                raise ValueError('Network sandbox probe failed: ' + log)
            report['checks'] = json.loads(log.strip())
            listener.settimeout(.2)
            try:
                received, _ = listener.accept()
            except TimeoutError:
                pass
            else:
                received.close()
                raise ValueError('LAN listener received an unexpected sandbox connection.')
            positive_lan()
        socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
        with socket.create_connection((address, 443), timeout=5):
            pass
        report['host_controls_before_and_after'] = True
        report['process_tree_cleanup'] = result['process_tree_cleanup']
        report['passed'] = all(item['blocked'] for item in report['checks'].values())
    except (OSError, ValueError) as error:
        report['error'] = str(error)
    finally:
        probe.doCleanups()
        WindowsNativeTests.tearDownClass()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS network isolation' if report['passed'] else 'FAIL network isolation: ' + report.get('error', 'unknown'))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
