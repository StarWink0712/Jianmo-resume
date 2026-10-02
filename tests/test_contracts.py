import copy
import unittest

from jsonschema import Draft202012Validator

from scripts.check_contracts import (
    BACKUP_SCHEMA,
    RESUME_SCHEMA,
    build_case,
    cases,
    json_bytes,
    make_manifest,
    read_json,
    safe_url,
    validate_backup,
    validate_resume,
)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.resume, self.assets = build_case(cases()[0])

    def test_schemas_are_valid(self):
        for schema in (RESUME_SCHEMA, BACKUP_SCHEMA):
            Draft202012Validator.check_schema(schema)

    def test_catalog(self):
        ids = [case['id'] for case in cases()]
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases():
            with self.subTest(case=case['id']):
                resume, _ = build_case(case)
                errors = validate_resume(resume)
                self.assertEqual(not errors, case['valid'], errors)

    def test_legacy_fixture_module_types_are_preserved(self):
        self.assertEqual(
            {section['type'] for section in self.resume['sections']},
            {'education', 'employment', 'project', 'skills', 'custom'},
        )

    def test_round_trip_preserves_order_visibility_and_characters(self):
        for case in cases():
            if case['valid']:
                with self.subTest(case=case['id']):
                    resume, _ = build_case(case)
                    self.assertEqual(read_json(json_bytes(resume)), resume)

    def test_validation_does_not_mutate_input(self):
        original = copy.deepcopy(self.resume)
        validate_resume(self.resume)
        self.assertEqual(self.resume, original)

    def test_optional_gender_age_and_empty_link_label(self):
        self.assertNotIn('gender', self.resume['basics'])
        self.assertNotIn('age', self.resume['basics'])
        self.assertEqual(validate_resume(self.resume), [])
        for age in (None, 0, 25, 150):
            self.resume['basics'].update(gender='女', age=age)
            self.resume['basics']['links'][0]['label'] = ''
            self.assertEqual(validate_resume(self.resume), [])
        self.resume['basics'].update(gender='', age=None)
        self.assertEqual(validate_resume(self.resume), [])

    def test_demographic_field_bounds(self):
        for value in (-1, 151, 25.5, '25', True):
            with self.subTest(age=value):
                self.resume['basics']['age'] = value
                self.assertTrue(validate_resume(self.resume))
        self.resume['basics']['age'] = None
        for value in (None, False, 'x' * 21):
            with self.subTest(gender=value):
                self.resume['basics']['gender'] = value
                self.assertTrue(validate_resume(self.resume))

    def test_new_fields_survive_backup_contract(self):
        self.resume['basics'].update(gender='男', age=29)
        self.resume['basics']['links'][0]['label'] = ''
        manifest, payloads = make_manifest(self.resume, self.assets)
        self.assertEqual(validate_backup(manifest, payloads), [])
        self.assertEqual(read_json(payloads['resume.json']), self.resume)

    def test_wrong_entry_type_is_rejected(self):
        self.resume['sections'][0]['entries'][0]['organization'] = 'Example'
        self.assertTrue(validate_resume(self.resume))

    def test_empty_titles_are_rejected(self):
        for value in ('', '   ', '\n\t'):
            with self.subTest(value=repr(value)):
                self.resume['title'] = value
                self.assertTrue(validate_resume(self.resume))

    def test_style_boundaries(self):
        for value, valid in ((9.5, False), (10, True), (10.5, True),
                             (10.2, False), (12, True), (12.5, False)):
            with self.subTest(font=value):
                self.resume['style']['font_size_pt'] = value
                self.assertEqual(not validate_resume(self.resume), valid)

    def test_all_allowed_line_heights(self):
        for value in (1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.45, 1.5):
            self.resume['style']['line_height'] = value
            self.assertFalse(validate_resume(self.resume))

    def test_invalid_month_and_updated_time_are_rejected(self):
        self.resume['sections'][0]['entries'][0]['start_date'] = '2024-13'
        self.assertTrue(validate_resume(self.resume))
        self.resume, _ = build_case(cases()[0])
        self.resume['updated_at'] = '2025-10-01T10:00:00Z'
        self.assertTrue(validate_resume(self.resume))

    def test_integer_and_size_bounds(self):
        for value in (0, -1, 1.5, True, 9007199254740992):
            self.resume['revision'] = value
            self.assertTrue(validate_resume(self.resume))
        self.resume, _ = build_case(cases()[0])
        self.resume['sections'][0]['entries'][0]['body'] = 'a' * 10001
        self.assertTrue(validate_resume(self.resume))

    def test_total_utf8_size_limit(self):
        entry = self.resume['sections'][2]['entries'][0]
        self.resume['sections'][2]['entries'] = [
            dict(entry, id=f'large-{i}', body='测' * 10000) for i in range(80)
        ]
        self.assertIn('resume exceeds 2 MiB', validate_resume(self.resume))

    def test_safe_url_policy(self):
        for value in ('https://example.com/a?q=1#part', 'http://example.com',
                      'https://example.com/%20'):
            self.assertTrue(safe_url(value), value)
        for value in ('javascript:alert(1)', 'file:///tmp/test', '//example.com',
                      'https://user:pass@example.com', 'https://example.com:bad',
                      'https://example.com\\evil', 'https://example.com/\n',
                      'https://example.com/%0a', 'https://',
                      'https://example.com:99999', ' https://example.com'):
            self.assertFalse(safe_url(value), value)

    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        for value in (b'{"a":1,"a":2}', b'{"value":NaN}', b'{"value":Infinity}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                read_json(value)

    def test_unpaired_surrogate_is_rejected(self):
        self.resume['basics']['name'] = '\ud800'
        self.assertTrue(validate_resume(self.resume))

    def test_markdown_checks_are_explicitly_deferred(self):
        deferred = [case for case in cases() if case.get('render_expectation')]
        self.assertEqual(len(deferred), 2)
        for case in deferred:
            resume, _ = build_case(case)
            self.assertFalse(validate_resume(resume))

    def test_backup_for_every_valid_case(self):
        for case in cases():
            if case['valid']:
                with self.subTest(case=case['id']):
                    resume, assets = build_case(case)
                    manifest, payloads = make_manifest(resume, assets)
                    self.assertFalse(validate_backup(manifest, payloads))

    def test_avatar_is_deterministic_and_referenced(self):
        case = next(case for case in cases() if case['id'] == 'avatar')
        resume, assets = build_case(case)
        self.assertEqual(build_case(case), (resume, assets))
        self.assertTrue(next(iter(assets.values())).startswith(b'\x89PNG\r\n\x1a\n'))
        resume['basics']['avatar_attachment_id'] = None
        self.assertTrue(validate_resume(resume))

    def test_hidden_avatar_is_preserved_in_backup(self):
        case = next(case for case in cases() if case['id'] == 'avatar')
        resume, assets = build_case(case)
        resume['basics']['avatar_visible'] = False
        self.assertFalse(validate_resume(resume))
        manifest, payloads = make_manifest(resume, assets)
        self.assertEqual(len(payloads), 2)
        self.assertFalse(validate_backup(manifest, payloads))

    def test_backup_missing_extra_and_corrupt_files(self):
        for mode in ('missing', 'extra', 'corrupt'):
            with self.subTest(mode=mode):
                manifest, payloads = make_manifest(self.resume, {})
                if mode == 'missing':
                    payloads.clear()
                elif mode == 'extra':
                    payloads['unlisted.txt'] = b'extra'
                else:
                    payloads['resume.json'] += b' '
                self.assertTrue(validate_backup(manifest, payloads))

    def test_backup_duplicate_and_unsafe_paths(self):
        manifest, payloads = make_manifest(self.resume, {})
        manifest['files'].append(copy.deepcopy(manifest['files'][0]))
        self.assertTrue(validate_backup(manifest, payloads))
        for path in ('../resume.json', '/resume.json', 'assets/../resume.json',
                     'assets\\avatar.png'):
            with self.subTest(path=path):
                manifest, payloads = make_manifest(self.resume, {})
                manifest['files'][0]['path'] = path
                self.assertTrue(validate_backup(manifest, payloads))

    def test_backup_identity_mismatch(self):
        for field, value in (('resume_id', 'other-resume'), ('revision', 2),
                             ('backup_version', 2), ('resume_schema_version', 2)):
            manifest, payloads = make_manifest(self.resume, {})
            manifest[field] = value
            self.assertTrue(validate_backup(manifest, payloads))

    def test_avatar_manifest_mismatch(self):
        resume, assets = build_case(next(case for case in cases() if case['id'] == 'avatar'))
        manifest, payloads = make_manifest(resume, assets)
        manifest['files'][1]['attachment_id'] = 'other-asset'
        self.assertTrue(validate_backup(manifest, payloads))

    def test_avatar_payload_mismatch_with_matching_manifest(self):
        resume, assets = build_case(next(case for case in cases() if case['id'] == 'avatar'))
        # A self-consistent manifest must still agree with resume attachment metadata.
        path = next(iter(assets))
        assets[path] += b'changed'
        manifest, payloads = make_manifest(resume, assets)
        self.assertTrue(validate_backup(manifest, payloads))


if __name__ == '__main__':
    unittest.main()
