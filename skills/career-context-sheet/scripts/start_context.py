"""Check this runtime, inspect a selected context, or create a private empty archive."""
import argparse
from datetime import datetime, timezone
import importlib.util
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

spec = importlib.util.spec_from_file_location('career_start_retrieval', Path(__file__).with_name('retrieve_context.py'))
retrieval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retrieval)
renderer = retrieval.renderer


class ResumeReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.parts = []
        self.count = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('id') == 'career-resume-data':
            self.count += 1
            if self.count != 1 or attrs.get('type') != 'application/json':
                raise ValueError('Invalid or duplicate resume metadata; preserve this file and recover the matching private save.')
            self.capture = True

    def handle_data(self, value):
        if self.capture:
            self.parts.append(value)

    def handle_endtag(self, tag):
        if tag == 'script':
            self.capture = False


def inspect_handoff(raw, basis, journey):
    reader = ResumeReader()
    reader.feed(raw)
    if not reader.count:
        return {'present': False, 'matched': None}  # Older private files remain supported.
    text = ''.join(reader.parts)
    if len(text) > 16000:
        raise ValueError('Resume metadata exceeds its limit.')
    value = json.loads(text)
    if (not isinstance(value, dict) or set(value) != {'schema', 'contextSha256', 'journeyUpdatedAt', 'instructions'} or
            value['schema'] != 'career-resume/v1' or not isinstance(value['instructions'], str) or
            not value['instructions'].strip() or '\0' in value['instructions'] or
            type(value['journeyUpdatedAt']) is not int):
        raise ValueError('Invalid resume metadata; do not apply pending corrections from this file.')
    if value['contextSha256'] != basis or value['journeyUpdatedAt'] != journey.get('updatedAt', 0):
        raise ValueError('Resume metadata does not match this file. Preserve it and recover or reconcile the matching private save.')
    return {'present': True, 'matched': True}


def inspect_runtime(source=None, model_dir=None, *, expected_context=None, expected_session=None):
    """No directory discovery, writes, model calls or connector access."""
    with sqlite3.connect(':memory:') as database:
        sqlite_ready = database.execute('SELECT 1').fetchone() == (1,)
    result = {
        'localRuntime': {'python': sys.version.split()[0], 'supported': sys.version_info >= (3, 11),
                         'sqlite': sqlite_ready, 'renderer': True, 'lexicalRetrieval': True},
        'semantic': {'checked': False, 'optional': True},
        'hostChecksRequired': ['Read the selected skill files', 'Discover available source tools without ingesting them',
                               'Establish current source, retention and model-processing authorization',
                               'Establish an authorized output location or an honest file-download fallback'],
        'permissionsGranted': False,
    }
    if model_dir is not None:
        semantic = renderer.load_helper('semantic_context')
        for name in semantic.FILES:
            semantic.verified_bytes(model_dir, name)
        result['semantic'] = {'checked': True, 'optional': True, 'modelFilesVerified': True,
                              'packagesAvailable': all(importlib.util.find_spec(name) for name in ['numpy', 'onnxruntime', 'tokenizers']),
                              'inferenceTested': False}
    if (expected_context is not None or expected_session is not None) and source is None:
        raise ValueError('Select the saved input that belongs to this continuation.')
    if expected_context is not None and (not isinstance(expected_context, str) or not re.fullmatch('[a-f0-9]{64}', expected_context)):
        raise ValueError('Expected context must be a SHA-256 fingerprint.')
    if expected_session is not None and (type(expected_session) is not int or not 0 <= expected_session <= 9007199254740991):
        raise ValueError('Expected session must be a safe nonnegative update time.')
    if source is not None:
        packet = retrieval.load_input(Path(source))
        if Path(source).suffix.lower() in {'.html', '.htm'} and re.search(
                r'<script[^>]+id=[\"\']career-draft-data[\"\']', Path(source).read_text(encoding='utf-8-sig')):
            raise ValueError('This saved notebook contains a separate draft. Preserve this file and reconcile it with scripts/merge_notebook.py before resuming the canonical context; do not discard the notebook edits.')
        basis = renderer.sections.evidence_fingerprint(packet)
        journey = packet.get('journey', {})
        handoff = inspect_handoff(Path(source).read_text(encoding='utf-8-sig'), basis, journey) if Path(source).suffix.lower() in {'.html', '.htm'} else {'present': False, 'matched': None}
        if ((expected_context is not None and expected_context != basis) or
                (expected_session is not None and expected_session != journey.get('updatedAt', 0))):
            raise ValueError('This file does not match the continuation. Supply the matching latest private save; do not apply corrections from an incomplete or different file.')
        checkpoint = journey.get('continuation')
        result['context'] = {
            'input': str(Path(source).resolve()), 'contextSha256': basis, 'journeyUpdatedAt': journey.get('updatedAt', 0),
            'handoff': handoff,
            'accounts': len(packet['accounts']), 'sources': len(packet['sources']),
            'claims': len(renderer.memory.claims(packet)), 'reviewStatus': packet['reviewStatus'],
            'continuation': checkpoint,
            'continuationCurrent': checkpoint is not None and checkpoint['contextSha256'] == basis,
            'investigationPresent': 'investigation' in journey,
            'investigationCurrent': journey.get('investigation', {}).get('contextSha256') == basis,
            'investigationReviewCurrent': journey.get('investigation', {}).get('reviewSha256', renderer.guided_path.review_fingerprint({})) == renderer.guided_path.review_fingerprint(packet) if 'investigation' in journey else False,
            'pendingCorrections': [key for key, review in journey.get('reviews', {}).items()
                                   if review['decision'] in ['correction', 'revision', 'needs_evidence']],
            'notesPresent': any(value.strip() for value in journey.get('notes', {}).values()),
            'collection': packet.get('collection', []),
        }
    return result


def start(workspace, name, goal=''):
    """Explicit new-workspace operation. An existing workspace is never reset."""
    renderer.check_text(name, 'Name', 200)
    renderer.check_text(goal, 'Goal', 3000)
    if not name.strip():
        raise ValueError('Supply the person\'s name; do not invent one.')
    workspace = Path(workspace).expanduser().resolve()
    if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
        raise ValueError('Workspace is not empty. Run check on its saved HTML or SQLite archive and continue it.')
    workspace.mkdir(parents=True, exist_ok=True)
    packet = {'schema': 'career-context/v1', 'updatedAt': datetime.now(timezone.utc).date().isoformat(),
              'reviewStatus': 'draft', 'person': {'name': name.strip(), 'overview': ''}, 'accounts': [], 'sources': []}
    basis = renderer.sections.evidence_fingerprint(packet)
    packet['journey'] = renderer.guided_path.initial_state(packet, basis)
    packet['journey']['continuation'] = {
        'contextSha256': basis, 'goal': goal, 'nextAction': 'Draft one account from material the person selects.',
        'questions': [], 'scopeNotes': 'No source access, model processing or publication permission is established by creating this archive.'}
    with tempfile.TemporaryDirectory(dir=workspace, prefix='.start-') as temporary:
        source = Path(temporary) / 'input.json'
        source.write_text(json.dumps(packet, ensure_ascii=False), encoding='utf-8')
        sheet = Path(temporary) / 'input.html'
        renderer.render(source, sheet, guided=True)
        result = renderer.load_helper('archive_context').build(sheet, workspace)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='Read-only runtime check; optionally inspect exactly one selected saved input')
    check.add_argument('input', nargs='?', type=Path)
    check.add_argument('--model-dir', type=Path, help='Verify explicitly selected optional model files; never download')
    check.add_argument('--expected-context', help='Reject an input whose evidence differs from the copied continuation')
    check.add_argument('--expected-session', type=int, help='Reject an input whose saved journey version differs from the continuation')
    create = commands.add_parser('start', help='Create an empty private HTML and SQLite archive in a new folder')
    create.add_argument('workspace', type=Path)
    create.add_argument('--name', required=True)
    create.add_argument('--goal', default='')
    args = parser.parse_args(argv)
    try:
        result = inspect_runtime(args.input, args.model_dir, expected_context=args.expected_context, expected_session=args.expected_session) if args.command == 'check' else start(args.workspace, args.name, args.goal)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(2, f'Could not start or continue: {error}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
