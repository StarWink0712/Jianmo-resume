import copy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from email.message import Message

from experiments.m1.boundaries import authorize, boundary_server, fetch_verified
from experiments.m1.render import RenderError, escape_text, render_contact_link, render_markdown, render_resume
from experiments.m1.run import benchmark_passes, case_passes, expected_text
from scripts.check_contracts import build_case, cases


class RenderingTests(unittest.TestCase):
    def test_all_special_characters_are_escaped_once(self):
        self.assertEqual(escape_text('\\&%$#_{}~^'), r'\textbackslash{}\&\%\$\#\_\{\}\textasciitilde{}\textasciicircum{}')

    def test_command_like_text_is_never_executed(self):
        rendered = render_markdown(r'\input{outside} & 100%')
        self.assertNotIn(r'\input{outside}', rendered)
        self.assertIn(r'\textbackslash{}input\{outside\}', rendered)

    def test_supported_inline_and_lists(self):
        source = '**bold** and *italic* [link](https://example.com/a?q=1&b=2)\n\n3. parent\n   - child'
        result = render_markdown(source)
        for expected in (r'\textbf{bold}', r'\textit{italic}', r'\href{https://example.com/a?q=1\&b=2}', r'\begin{enumerate}[start=3]', r'\begin{itemize}'):
            self.assertIn(expected, result)

    def test_unsupported_nodes_and_links_are_rejected(self):
        for source in ('# heading', '> quote', '`code`', '```\ncode\n```', '<b>html</b>',
                       '![image](https://example.com/p.png)', '[bad](javascript:alert(1))',
                       '[bad](file:///tmp/secret)', '<https://example.com>',
                       '- one\n  - two\n    - three'):
            with self.subTest(source=source), self.assertRaises(RenderError):
                render_markdown(source)

    def test_control_characters_rejected(self):
        for value in ('test\x00', '\u202ehidden'):
            with self.assertRaises(RenderError):
                escape_text(value)

    def test_all_catalog_render_expectations(self):
        for case in cases():
            with self.subTest(case=case['id']):
                resume, assets = build_case(case)
                if case['valid'] and not case.get('render_expectation'):
                    self.assertIn(r'\end{document}', render_resume(resume, assets)[0])
                else:
                    with self.assertRaises(RenderError):
                        render_resume(resume, assets)

    def test_hidden_unsafe_markdown_still_rejected(self):
        resume, assets = build_case(next(case for case in cases() if case['id'] == 'unsafe-markdown-draft'))
        resume['sections'][2]['visible'] = False
        with self.assertRaises(RenderError):
            render_resume(resume, assets)

    def test_rendering_does_not_mutate_saved_data(self):
        resume, assets = build_case(cases()[0])
        original = copy.deepcopy(resume)
        render_resume(resume, assets)
        self.assertEqual(resume, original)

    def test_avatar_is_checked_and_normalized(self):
        resume, assets = build_case(next(case for case in cases() if case['id'] == 'avatar'))
        self.assertTrue(render_resume(resume, assets)[1].startswith(b'\x89PNG'))
        assets[next(iter(assets))] += b'corrupt'
        with self.assertRaises(RenderError):
            render_resume(resume, assets)

    def test_header_centering_is_scoped_with_and_without_avatar(self):
        for case_id in ('standard-one-page-target', 'avatar'):
            resume, assets = build_case(next(case for case in cases() if case['id'] == case_id))
            resume['basics'].update(gender='女', age=25)
            source, _ = render_resume(resume, assets)
            header = source.split(r'\par\endgroup')[0]
            self.assertIn(r'\begingroup\centering', header)
            self.assertIn(r'女 \textbar{} 25岁 \textbar{} 示例市', header)
            self.assertNotIn(r'\centering', source.split(r'\par\endgroup')[1])
            if case_id == 'avatar':
                self.assertEqual(source.count(r'{26mm}'), 2)
                self.assertIn(r'{\dimexpr\linewidth-52mm\relax}', source)
                self.assertIn(r'width=24mm,height=32mm,keepaspectratio', source)

    def test_missing_or_cleared_demographics_do_not_print_placeholders(self):
        resume, assets = build_case(next(case for case in cases() if case['id'] == 'blank'))
        resume['basics'].update(gender='', age=None)
        source, _ = render_resume(resume, assets)
        self.assertNotIn('岁', source)
        self.assertNotIn('None', source)
        resume['basics']['age'] = 0
        self.assertIn('0岁', render_resume(resume, assets)[0])
        self.assertIn('0岁', expected_text(resume))
        resume['basics']['age'] = 25.0
        self.assertIn('25岁', render_resume(resume, assets)[0])
        self.assertNotIn('25.0岁', render_resume(resume, assets)[0])

    def test_optional_contact_label_uses_safe_bare_url(self):
        resume, _ = build_case(next(case for case in cases() if case['id'] == 'blank'))
        for label in ('', '  '):
            link = {'id': 'link-test', 'label': label, 'url': 'https://example.com/a_b?q=1&k=2'}
            source = render_contact_link(link)
            self.assertNotIn('Link', source)
            self.assertIn(r'\href{https://example.com/a\_b?q=1\&k=2}', source)
            self.assertIn(r'\allowbreak{}', source)
            resume['basics']['links'] = [link]
            self.assertIn(link['url'], expected_text(resume))
        link['label'] = '作品集'
        self.assertTrue(render_contact_link(link).endswith('{作品集}'))
        self.assertIn('作品集', expected_text(resume))


class BoundaryTests(unittest.TestCase):
    def test_non_ascii_token_is_rejected_without_crashing(self):
        headers = {'Host': '127.0.0.1:1234', 'X-Resume-Token': '\u00e9'}
        self.assertEqual(authorize('GET', headers, 'http://127.0.0.1:1234', 'token'), 403)

    def test_duplicate_security_headers_are_rejected(self):
        headers = Message()
        headers['Host'] = '127.0.0.1:1234'
        headers['Host'] = 'attacker.example'
        self.assertEqual(authorize('GET', headers, 'http://127.0.0.1:1234', 'token'), 400)

    def test_real_loopback_http_boundary(self):
        with boundary_server() as (origin, token):
            headers = {'Origin': origin, 'X-Resume-Token': token, 'Content-Type': 'application/json'}
            with urlopen(Request(origin, b'{}', headers), timeout=2) as response:
                self.assertEqual(response.status, 200)
            for changed in ({'Host': 'attacker.example'}, {'Origin': 'https://attacker.example'},
                            {'Origin': 'null'}, {'X-Resume-Token': 'bad'}, {'Content-Type': 'text/plain'}):
                with self.subTest(changed=changed), self.assertRaises(HTTPError) as error:
                    urlopen(Request(origin, b'{}', headers | changed), timeout=2)
                self.assertIn(error.exception.code, (403, 415))
                error.exception.close()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(origin, b'{}', {'X-Resume-Token': token, 'Content-Type': 'application/json'}), timeout=2)
            error.exception.close()
            with self.assertRaises(HTTPError) as error:
                urlopen(origin, timeout=2)
            error.exception.close()


class ExperimentGateTests(unittest.TestCase):
    def test_unexpected_acceptance_or_rejection_fails(self):
        self.assertFalse(case_passes({'id': 'unsafe', 'valid': False}, {'ok': True}))
        self.assertFalse(case_passes({'id': 'valid', 'valid': True}, {'rejected': True}))
        self.assertTrue(case_passes({'id': 'unsafe', 'valid': False}, {'rejected': True}))

    def test_page_targets_are_enforced(self):
        case = {'id': 'two-page-target', 'valid': True}
        self.assertFalse(case_passes(case, {'ok': True, 'pages': 3}))
        self.assertTrue(case_passes(case, {'ok': True, 'pages': 2}))

    def test_performance_requires_enough_samples_and_correct_pages(self):
        benchmark = {'iterations': 30, 'pages': 2, 'p95_seconds': 1, 'p95_target_seconds': 3}
        self.assertTrue(benchmark_passes(benchmark))
        self.assertIsNone(benchmark_passes(benchmark | {'iterations': 1}))
        self.assertFalse(benchmark_passes(benchmark | {'p95_seconds': 4}))
        self.assertFalse(benchmark_passes(benchmark | {'pages': 3}))


class DownloadTests(unittest.TestCase):
    def test_interrupted_download_cleans_temporary_file_and_retry_works(self):
        class Broken(io.BytesIO):
            def geturl(self):
                return 'https://example.com/runtime'

            def read(self, _size):
                raise OSError('simulated connection loss')

        class Complete(io.BytesIO):
            def geturl(self):
                return 'https://example.com/runtime'

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'runtime'
            target.write_bytes(b'old')
            digest = hashlib.sha256(b'new').hexdigest()
            with self.assertRaises(OSError):
                fetch_verified('https://example.com/runtime', target, digest, 3, lambda *_a, **_k: Broken())
            self.assertEqual(target.read_bytes(), b'old')
            self.assertEqual(list(Path(temporary).glob('.download-*')), [])
            fetch_verified('https://example.com/runtime', target, digest, 3, lambda *_a, **_k: Complete(b'new'))
            self.assertEqual(target.read_bytes(), b'new')

    def test_integrity_cache_and_atomic_failure(self):
        payload = b'fictional runtime artifact'
        digest = hashlib.sha256(payload).hexdigest()

        class Response(io.BytesIO):
            def geturl(self):
                return 'https://example.com/runtime'

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'runtime.bin'
            opener = lambda *_args, **_kwargs: Response(payload)
            self.assertEqual(fetch_verified('https://example.com/runtime', target, digest, len(payload), opener), 'downloaded')
            self.assertEqual(fetch_verified('https://example.com/runtime', target, digest, len(payload), opener), 'cached')
            for bad in (payload + b'excess', payload[:-1], b'x' * len(payload)):
                with self.subTest(kind=len(bad)), self.assertRaises(ValueError):
                    fetch_verified('https://example.com/runtime', target, '0' * 64, len(payload), lambda *_a, **_k: Response(bad))
                self.assertEqual(target.read_bytes(), payload)
                self.assertEqual(list(Path(temporary).glob('.download-*')), [])

    def test_insecure_download_and_redirect_are_rejected(self):
        class Response(io.BytesIO):
            def geturl(self):
                return 'http://example.com/runtime'

        with tempfile.TemporaryDirectory() as temporary:
            for url in ('http://example.com/runtime', 'https://example.com/runtime'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    fetch_verified(url, Path(temporary) / 'test', '0' * 64, 1, lambda *_a, **_k: Response(b'x'))


if __name__ == '__main__':
    unittest.main()
