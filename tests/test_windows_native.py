"""Real Win32 acceptance. These tests never enable the production adapter."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from platform_adapters.contracts import LockBusy


@unittest.skipUnless(sys.platform == 'win32', 'requires native Windows')
class WindowsNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from platform_adapters import windows_native
        cls.native = windows_native
        cls.temporary = tempfile.TemporaryDirectory(prefix='jianmo 中文 & (native)-')
        cls.root = Path(cls.temporary.name)
        cls.runtime = cls.root / 'python'
        cls.native.private_directory(cls.runtime)
        base = Path(sys.base_prefix)
        version = f'python{sys.version_info.major}{sys.version_info.minor}'
        for name in ('python.exe', version + '.dll', 'python3.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
            if (base / name).exists():
                shutil.copyfile(base / name, cls.runtime / name)
        # A disposable, read-only probe runtime; never change ACLs on installed Python.
        with zipfile.ZipFile(cls.runtime / (version + '.zip'), 'w') as archive:
            for path in (base / 'Lib').rglob('*.py'):
                relative = path.relative_to(base / 'Lib')
                if not set(relative.parts) & {'site-packages', 'test', 'tests', '__pycache__'}:
                    archive.write(path, relative.as_posix())
        shutil.copytree(base / 'DLLs', cls.runtime / 'DLLs', ignore=shutil.ignore_patterns('*.pdb', '__pycache__'))
        (cls.runtime / (version + '._pth')).write_text(version + '.zip\nDLLs\n.\n', encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.root, prefix='job-')
        self.addCleanup(self.temp.cleanup)
        self.job = Path(self.temp.name)
        self.native.private_directory(self.job)

    def run_probe(self, source, **kwargs):
        with self.native.app_container() as (sid, text):
            self.native.grant_tree(self.runtime, text)
            self.native.grant_tree(self.job, text, True)
            engine = self.runtime / 'python.exe'
            result = self.native.run_in_container([str(engine), '-I', '-S', '-c', source],
                self.job, self.native.environment(self.job, engine), sid, **kwargs)
            return result, (self.job / 'process.log').read_text(encoding='utf-8', errors='replace')

    def test_private_acl_and_inheritance(self):
        data = self.job / 'resumes.sqlite3'
        data.write_text('artificial database', encoding='utf-8')
        for path in (self.job, data):
            acl = self.native.security_text(path)
            self.assertIn(self.native.current_user_sid(), acl)
            self.assertNotIn(';;;BU)', acl)
            self.assertNotIn(';;;WD)', acl)
            self.assertNotIn(';;;AC)', acl)
        self.assertIn('D:P', self.native.security_text(self.job))

    def test_exclusive_lease_and_release(self):
        with self.native.acquire_lock(self.job, '.lock'):
            with self.assertRaises(LockBusy):
                self.native.acquire_lock(str(self.job).upper(), '.lock')
        self.native.acquire_lock(self.job, '.lock').close()

    def test_ambiguous_lock_paths_are_rejected(self):
        for name in ('NUL', 'con.txt', 'COM1', 'LPT¹', '../lock', 'x:stream', 'lock.', 'lock ', 'x?'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.native.acquire_lock(self.job, name)

    def test_lease_released_after_host_death(self):
        code = ('from platform_adapters.windows_native import acquire_lock; import sys,time; '
                'lease=acquire_lock(sys.argv[1],".lock"); print("ready",flush=True); time.sleep(30)')
        with subprocess.Popen([sys.executable, '-c', code, str(self.job)], stdout=subprocess.PIPE, text=True) as child:
            try:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                with self.assertRaises(LockBusy):
                    self.native.acquire_lock(self.job, '.lock')
            finally:
                child.kill()
                child.wait(timeout=5)
        self.native.acquire_lock(self.job, '.lock').close()

    def test_appcontainer_executes_and_writes_only_its_job(self):
        secret = self.root / 'artificial-secret.txt'
        secret.write_text('not real user data', encoding='utf-8')
        self.native.set_private_acl(secret)
        source = f'''import pathlib, json
p=pathlib.Path('allowed.txt');p.write_text('ok');assert p.read_text()=='ok'
blocked=[]
for action in [lambda: pathlib.Path({str(secret)!r}).read_text(), lambda: pathlib.Path({str(secret)!r}).write_text('bad')]:
 try: action()
 except PermissionError: blocked.append(True)
print(json.dumps({{'blocked':len(blocked),'positive':p.read_text()}}))
assert len(blocked)==2
'''
        result, log = self.run_probe(source)
        self.assertEqual(result['returncode'], 0, (result, log))
        self.assertIn('"blocked": 2', log)
        self.assertEqual(secret.read_text(encoding='utf-8'), 'not real user data')

    def test_loopback_denied_with_positive_control(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(2)
            port = listener.getsockname()[1]
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                accepted, _ = listener.accept()
                accepted.close()
            source = f'''import socket
s=socket.socket();s.settimeout(2)
try: s.connect(('127.0.0.1',{port}))
except (PermissionError, TimeoutError): print('blocked')
else: raise AssertionError('loopback was permitted')
'''
            result, log = self.run_probe(source)
            listener.settimeout(.1)
            with self.assertRaises(TimeoutError):
                listener.accept()
            # The listener stayed healthy during the denied sandbox operation.
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                accepted, _ = listener.accept()
                accepted.close()
        self.assertEqual(result['returncode'], 0, (result, log))
        self.assertIn('blocked', log)

    def test_other_job_and_runtime_write_are_denied(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary, self.native.app_container() as (_, other_sid):
            other = Path(temporary)
            self.native.private_directory(other)
            secret = other / 'resumes.sqlite3'
            secret.write_text('artificial database', encoding='utf-8')
            self.native.grant_tree(other, other_sid, True)
            source = f'''from pathlib import Path
blocked=0
for action in [lambda:Path({str(secret)!r}).read_text(),lambda:Path({str(self.runtime / 'injected.dll')!r}).write_bytes(b'bad')]:
 try:action()
 except PermissionError:blocked+=1
print('blocked',blocked)
assert blocked==2
'''
            result, log = self.run_probe(source)
            self.assertEqual(result['returncode'], 0, (result, log))
            self.assertEqual(secret.read_text(encoding='utf-8'), 'artificial database')
            self.assertFalse((self.runtime / 'injected.dll').exists())

    def test_junction_is_rejected_before_acl_or_lock_access(self):
        import _winapi
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            target = Path(temporary)
            before = self.native.security_text(target)
            alias = self.job / 'alias'
            _winapi.CreateJunction(str(target), str(alias))
            try:
                with self.assertRaises(ValueError):
                    self.native.private_directory(alias)
                with self.assertRaises(ValueError):
                    self.native.acquire_lock(alias, '.lock')
                self.assertEqual(self.native.security_text(target), before)
                self.assertFalse((target / '.lock').exists())
            finally:
                alias.rmdir()

    def test_prototype_drive_is_removed_on_exception(self):
        from scripts.probe_windows_engine import prototype_drive
        (self.job / 'marker').write_text('owned')
        with self.assertRaisesRegex(RuntimeError, 'test interruption'):
            with prototype_drive(self.job) as mapped:
                self.assertEqual((mapped / 'marker').read_text(), 'owned')
                raise RuntimeError('test interruption')
        self.assertFalse((mapped / 'marker').exists())

    def test_handle_owned_aliases_allow_independent_outputs(self):
        from scripts.probe_windows_engine import prototype_drive
        with tempfile.TemporaryDirectory(dir=self.root) as other:
            (self.job / 'marker').write_text('first')
            (Path(other) / 'marker').write_text('second')
            with prototype_drive(self.job) as first, prototype_drive(Path(other)) as second:
                self.assertNotEqual(first, second)
                self.assertEqual((first / 'marker').read_text(), 'first')
                self.assertEqual((second / 'marker').read_text(), 'second')

    def test_alias_disappears_after_supervisor_is_killed(self):
        (self.job / 'marker').write_text('owned')
        code = ('from platform_adapters.windows_paths import runtime_alias; import sys,time; '
                'scope=runtime_alias(sys.argv[1]); print(str(scope.__enter__()),flush=True);time.sleep(60)')
        with subprocess.Popen([sys.executable, '-c', code, str(self.job)], stdout=subprocess.PIPE, text=True) as host:
            try:
                alias = Path(host.stdout.readline().strip())
                self.assertEqual((alias / 'marker').read_text(), 'owned')
            finally:
                host.kill()
                host.wait(timeout=5)
            # Process signalling can precede deferred handle-table rundown.
            deadline = time.monotonic() + 5
            while (alias / 'marker').exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertFalse((alias / 'marker').exists())

    def image_policy(self):
        from platform_adapters.windows_images import ImagePolicy
        import hashlib
        return ImagePolicy({path: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in self.runtime.rglob('*') if path.suffix in ('.exe', '.dll', '.pyd')})

    def test_dynamic_images_are_audited_with_hashes(self):
        policy = self.image_policy()
        result, log = self.run_probe("import ctypes;ctypes.WinDLL('version.dll');print('loaded')", image_policy=policy)
        self.assertEqual(result['returncode'], 0, (result, log))
        self.assertIn('version.dll', [item['name'] for item in result['loaded_images']])
        self.assertTrue(all(len(item['sha256']) == 64 for item in result['loaded_images']))

    def test_image_outside_runtime_is_stopped(self):
        source = Path(self.native.system_directory()) / 'version.dll'
        shutil.copyfile(source, self.job / 'unapproved.dll')
        result, log = self.run_probe("import ctypes;ctypes.WinDLL('./unapproved.dll');print('must-not-run')",
                                     image_policy=self.image_policy())
        self.assertEqual(result['reason'], 'image_policy', (result, log))
        self.assertNotIn('must-not-run', log)

    def test_wrong_image_hash_is_stopped_before_execution(self):
        policy = self.image_policy()
        policy.pinned[os.path.normcase(str(self.runtime / 'python.exe'))] = '0' * 64
        result, log = self.run_probe("print('must-not-run')", image_policy=policy)
        self.assertEqual(result['reason'], 'image_policy', (result, log))
        self.assertNotIn('must-not-run', log)

    def test_hardlink_cannot_change_external_acl(self):
        external = self.root / 'hardlink-secret'
        external.write_text('owned elsewhere')
        before = self.native.security_text(external)
        link = self.job / 'linked'
        os.link(external, link)
        try:
            with self.assertRaises(ValueError):
                self.native.grant_tree(self.job, None)
            self.assertEqual(self.native.security_text(external), before)
        finally:
            link.unlink()
            external.unlink()

    def test_open_path_pins_ancestor_against_rename(self):
        parent = self.job / 'nested'
        parent.mkdir()
        child = parent / 'file'
        child.write_text('owned')
        with self.native.hold_path(child):
            with self.assertRaises(OSError):
                parent.rename(self.job / 'renamed')
        parent.rename(self.job / 'renamed')

    def test_wall_timeout_and_descendant_cleanup(self):
        source = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);print('spawned',flush=True);time.sleep(60)"
        result, log = self.run_probe(source, timeout=1)
        self.assertIn('spawned', log)
        self.assertTrue(result['timed_out'], result)
        self.assertEqual(result['process_tree_cleanup'], 'terminated_and_drained')

    def test_descendants_cleaned_after_parent_success(self):
        source = "import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);print('spawned',flush=True)"
        result, log = self.run_probe(source)
        self.assertEqual(result['returncode'], 0, (result, log))
        self.assertEqual(result['process_tree_cleanup'], 'terminated_and_drained')

    def test_cancellation(self):
        cancel = threading.Event()
        timer = threading.Timer(.5, cancel.set)
        timer.start()
        try:
            result, log = self.run_probe("import time;print('started',flush=True);time.sleep(60)", cancel=cancel)
        finally:
            timer.cancel()
        self.assertEqual(result['reason'], 'cancelled', (result, log))

    def test_failed_job_assignment_never_executes_child(self):
        with patch.object(self.native, 'AssignJob', return_value=False):
            with self.assertRaises(OSError):
                self.run_probe("open('must-not-exist','w').write('bad')")
        self.assertFalse((self.job / 'must-not-exist').exists())

    def test_memory_commit_hard_limit(self):
        result, log = self.run_probe("a=[]\ntry:\n while True:a.append(bytearray(8*1024*1024))\nexcept MemoryError:print('bounded',len(a));assert len(a)*8*1024**2<64*1024**2", memory_limit_bytes=64*1024**2)
        self.assertEqual(result['returncode'], 0, (result, log))
        self.assertIn('bounded', log)
        # Job peak accounting may include a failed allocation; it is not RSS.
        self.assertGreater(result['peak_job_memory_bytes'], 0)

    def test_output_budget(self):
        result, log = self.run_probe("import time\nwith open('large','wb') as f:\n while True:f.write(b'x'*65536);f.flush();time.sleep(.01)", output_limit_bytes=1024*1024)
        self.assertEqual(result['reason'], 'file_limit', (result, log))

    def test_output_sampling_tolerates_removed_temporary_directories(self):
        result, log = self.run_probe("import pathlib,time\np=pathlib.Path('transient');end=time.monotonic()+1\nwhile time.monotonic()<end:\n p.mkdir();(p/'file').write_bytes(b'x');(p/'file').unlink();p.rmdir()\nprint('done')")
        self.assertEqual(result['returncode'], 0, (result, log))
        self.assertIn('done', log)

    def test_cpu_budget(self):
        result, log = self.run_probe("print('started',flush=True)\nwhile True:pass", cpu_seconds=.5, timeout=5)
        self.assertIn('started', log)
        self.assertFalse(result['timed_out'], result)
        self.assertEqual(result['reason'], 'cpu_limit')
        self.assertNotEqual(result['returncode'], 0, result)
        self.assertLess(result['seconds'], 5)

    def test_host_death_kills_the_entire_job(self):
        import ctypes as C
        from ctypes import wintypes as W
        native = self.native
        open_process = native.api(native.kernel, 'OpenProcess', W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
        with native.app_container() as (sid, text):
            native.grant_tree(self.runtime, text)
            native.grant_tree(self.job, text, True)
            engine = self.runtime / 'python.exe'
            source = ("import subprocess,sys,os,time,json; "
                      "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); "
                      "open('pids.json','w').write(json.dumps([os.getpid(),child.pid]));time.sleep(60)")
            host_code = '''import ctypes as C,sys,json
from ctypes import wintypes as W
from pathlib import Path
from platform_adapters import windows_native as n
convert=n.api(n.advapi,'ConvertStringSidToSidW',W.BOOL,W.LPCWSTR,C.POINTER(n.P))
sid=n.P();n.checked(convert(sys.argv[1],C.byref(sid)))
job=Path(sys.argv[2]);engine=Path(sys.argv[3])
try:n.run_in_container([str(engine),'-I','-S','-c',sys.argv[4]],job,n.environment(job,engine),sid)
finally:n.LocalFree(sid)
'''
            process_handles = []
            with subprocess.Popen([sys.executable, '-c', host_code, text, str(self.job), str(engine), source]) as host:
                try:
                    deadline = time.monotonic() + 8
                    while not (self.job / 'pids.json').exists() and time.monotonic() < deadline:
                        time.sleep(.05)
                    pids = json.loads((self.job / 'pids.json').read_text())
                    for pid in pids:
                        process_handles.append(native.checked(open_process(0x100000, False, pid)))
                    host.kill()
                    host.wait(timeout=5)
                    for handle in process_handles:
                        self.assertEqual(native.Wait(handle, 5000), 0)
                finally:
                    if host.poll() is None:
                        host.kill()
                        host.wait(timeout=5)
                    for handle in process_handles:
                        native.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
