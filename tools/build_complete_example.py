"""Rebuild the single public document from fictional work, periods and preparation."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_context', ROOT / 'skills/career-context-sheet/scripts/render_context.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def example():
    packet = json.loads((ROOT / 'examples/career-context.json').read_text(encoding='utf-8'))
    quarters = json.loads((ROOT / 'examples/notebook-quarters.json').read_text(encoding='utf-8'))['quarters']
    packet['timeline'] = [{**{k: v for k, v in q.items() if k not in ['style', 'accountId']},
                           'approach': q['style'], 'accountIds': [q['accountId']]} for q in quarters]
    packet['interview'] = json.loads((ROOT / 'examples/interview-preparation.json').read_text(encoding='utf-8'))
    packet['interview']['contextSha256'] = renderer.sections.evidence_fingerprint(packet)
    packet['presentation'] = {'briefs': {'contextSha256': renderer.sections.evidence_fingerprint(packet), 'accounts': {
        'request-handoffs': [
            'Mapped requests arriving by email, at the desk and in a shared notebook, then introduced a weekly review with coordinators.',
            'Revised unclear status labels after coordinator feedback. The team kept the review after the trial.',
            'Continued use is documented for this one team; turnaround was not measured.'],
        'volunteer-guide': [
            'Turned recurring volunteer questions into a short desk guide. A colleague checked the procedures.',
            'Two volunteers tried it in supervised shifts. Their feedback changed the room-booking instructions; the revised guide stayed in the next induction.',
            'Independent use and time savings were not tested.'],
        'equipment-prototype': [
            'Sketched an equipment checkout flow and used AI to generate a Python prototype.',
            'Checked checkout and return with fictional items. No real borrower or equipment data was imported.',
            'The team has not tried it. Deployment and maintenance remain open; independent Python ability is not claimed.']}}}
    packet['presentation']['timelineReading'] = {
        'contextSha256': renderer.sections.evidence_fingerprint(packet),
        'periods': {
            '2030-Q1': {'title': 'Make request ownership visible', 'bullets': ['Traced request handoffs and introduced a shared review.', 'Coordinator feedback changed the status labels. Continued use is documented for one team; turnaround was not measured.'], 'accountIds': ['request-handoffs']},
            '2030-Q2': {'title': 'Test a volunteer desk guide', 'bullets': ['Drafted a guide and observed two volunteers using it in supervised shifts.', 'Rewrote room-booking instructions after their feedback. Independent use was not tested.'], 'accountIds': ['volunteer-guide']},
            '2030-Q3': {'title': 'Try an equipment checkout prototype', 'bullets': ['Used AI assistance to build a local checkout and return prototype with fictional items.', 'No real records or user trial yet. Maintenance ownership remains open.'], 'accountIds': ['equipment-prototype']}
        },
        'years': {'2030': {'title': 'Make everyday coordination easier', 'bullets': ['Introduced a shared request review and tested a volunteer desk guide with colleagues.', 'Built an AI-assisted equipment prototype; it has not had a user trial.', 'Saved periods are approximate groupings, not a complete record of the year.']}}
    }
    renderer.validate(packet)
    return packet


if __name__ == '__main__':
    source = ROOT / 'examples/complete-context.json'
    source.write_text(json.dumps(example(), ensure_ascii=True, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(renderer.render(source, ROOT / 'CAREER-CONTEXT.html')))
