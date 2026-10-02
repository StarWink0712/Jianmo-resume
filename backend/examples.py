"""Bundled fictional resume content, independent of any user's database."""
from scripts.check_contracts import ROOT, read_json


EXAMPLES = {
    'java': 'java-developer',
    'algorithm': 'algorithm-engineer',
    'testing': 'test-engineer',
}


def example_document(kind):
    return read_json((ROOT / 'examples/resumes' / (EXAMPLES[kind] + '.json')).read_bytes())
