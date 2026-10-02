"""Build portable backup archives from the bundled fictional JSON documents."""
from backend.backup import export_backup
from backend.domain import validate
from backend.examples import EXAMPLES, example_document
from scripts.check_contracts import ROOT


def main():
    directory = ROOT / 'examples/backups'
    directory.mkdir(parents=True, exist_ok=True)
    for kind, filename in EXAMPLES.items():
        document = example_document(kind)
        validate(document, {})
        (directory / (filename + '.resume.zip')).write_bytes(export_backup(document, {}))
        print('Built examples/backups/' + filename + '.resume.zip')


if __name__ == '__main__':
    main()
