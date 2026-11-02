"""Export explicit work accounts for another tool. No network or archive writes."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

_spec = importlib.util.spec_from_file_location('selection_renderer', Path(__file__).with_name('render_context.py'))
renderer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(renderer)

SCHEMA = 'career-context-selection/v1'
MAX_BYTES = 512 * 1024
ACCOUNT_FIELDS = ('id', *renderer.TEXT_FIELDS, *renderer.LIST_FIELDS, 'tags', 'capabilities')
SELECTION_FIELDS = ('schema', 'updatedAt', 'reviewStatus', 'synthetic',
                    'sourceEvidenceIncluded', 'accounts', 'selectionSha256')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def fingerprint(selection):
    return hashlib.sha256(canonical({k: v for k, v in selection.items()
                                    if k != 'selectionSha256'})).hexdigest()


def validate(selection):
    """Reject extra fields: this is a selected narrative, never a full archive."""
    renderer.keys(selection, SELECTION_FIELDS, 'Selection')
    if set(selection) != set(SELECTION_FIELDS) or selection['schema'] != SCHEMA:
        raise ValueError('Unsupported or incomplete selection')
    if selection['sourceEvidenceIncluded'] is not False or type(selection['synthetic']) is not bool:
        raise ValueError('Invalid selection evidence flags')
    accounts = selection['accounts']
    if not isinstance(accounts, list) or not 1 <= len(accounts) <= 80:
        raise ValueError('Select 1–80 work accounts')
    for account in accounts:
        renderer.keys(account, ACCOUNT_FIELDS, 'Selected account')
    # Reuse the account contract. Placeholder sources are used only to validate
    # opaque reference IDs; they are never output or treated as source evidence.
    refs = []
    for account in accounts:
        if not isinstance(account.get('sourceRefs'), list):
            raise ValueError('Selected accounts need source reference IDs')
        refs.extend(account['sourceRefs'])
    if any(not isinstance(ref, str) for ref in refs):
        raise ValueError('Invalid source reference ID')
    packet = {'schema': 'career-context/v1', 'updatedAt': selection['updatedAt'],
              'reviewStatus': selection['reviewStatus'], 'synthetic': selection['synthetic'],
              'person': {'name': '', 'overview': ''}, 'accounts': accounts,
              'sources': [{'id': ref, 'label': '', 'kind': 'source_excerpt',
                           'content': '', 'scope': ''} for ref in dict.fromkeys(refs)]}
    renderer.validate(packet)
    digest = selection['selectionSha256']
    if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest) or digest != fingerprint(selection):
        raise ValueError('Selection fingerprint does not match its content')
    if len(canonical(selection)) > MAX_BYTES:
        raise ValueError('Selection exceeds 512 KiB; select fewer accounts')


def select(packet, account_ids):
    renderer.validate(packet)
    if not account_ids or len(set(account_ids)) != len(account_ids):
        raise ValueError('Name each selected account once')
    accounts = {account['id']: account for account in packet['accounts']}
    if any(key not in accounts for key in account_ids):
        raise ValueError('A selected account is missing from the archive')
    selection = {'schema': SCHEMA, 'updatedAt': packet['updatedAt'],
                 'reviewStatus': packet['reviewStatus'], 'synthetic': packet.get('synthetic', False),
                 'sourceEvidenceIncluded': False,
                 'accounts': [{key: copy.deepcopy(value) for key, value in accounts[aid].items()
                               if key in ACCOUNT_FIELDS} for aid in account_ids]}
    selection['selectionSha256'] = fingerprint(selection)
    validate(selection)
    return selection


def load_source(path):
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError('Choose a regular context file')
    if path.suffix.lower() not in {'.sqlite', '.sqlite3', '.db'}:
        return renderer.load_packet(path)
    archive_context = renderer.load_helper('archive_context')
    db = archive_context.connect(path, readonly=True)
    try:
        # Bound the selected current packet before reading it; do not copy the DB.
        row = db.execute("SELECT length(CAST(packet AS BLOB)) FROM revisions WHERE id="
                         "(SELECT value FROM metadata WHERE key='current')").fetchone()
        if row is None or row[0] > renderer.MAX_PACKET_BYTES:
            raise ValueError('Archive current revision is missing or too large')
        raw = db.execute("SELECT packet FROM revisions WHERE id="
                         "(SELECT value FROM metadata WHERE key='current')").fetchone()[0]
        return renderer.parse_packet(raw)
    finally:
        db.close()


def load_selection(path):
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError('Choose a regular selection file')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Selection exceeds 512 KiB')
    selection = json.loads(raw)
    validate(selection)
    return selection


def export(source, destination, account_ids, *, force=False):
    source, destination = Path(source).expanduser().absolute(), Path(destination).expanduser().absolute()
    if destination.is_symlink() or destination.resolve() == source.resolve():
        raise ValueError('The selection must be a separate regular file')
    if destination.resolve().is_relative_to(renderer.SKILL.resolve()):
        raise ValueError('Save personal selections outside the installed skill')
    if destination.exists() and not force:
        raise ValueError('Selection already exists; use --force to replace it')
    selection = select(load_source(source), account_ids)
    raw = canonical(selection) + b'\n'
    if len(raw) > MAX_BYTES:
        raise ValueError('Selection exceeds 512 KiB; select fewer accounts')
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix='.selection-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
        if force:
            os.replace(temporary, destination)
        else:
            renderer.publish_new(Path(temporary), destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'accounts': len(selection['accounts']), 'selectionSha256': selection['selectionSha256']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Context JSON, saved HTML or local SQLite archive')
    parser.add_argument('output', type=Path, help='Separate selection JSON; review before connecting an agent')
    parser.add_argument('--account', action='append', required=True, help='Exact account ID; repeat to select more')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = export(args.source, args.output, args.account, force=args.force)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        parser.exit(2, 'Could not export selection. Check the input, account IDs and separate output path.\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
