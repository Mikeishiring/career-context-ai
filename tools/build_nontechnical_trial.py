"""A small authored trial from raw fictional notes, without a supplied profession.

This exercises the current workflow; it is not an independent model evaluation.
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('trial_renderer', ROOT / 'skills/career-context-sheet/scripts/render_context.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def packet():
    notes = (ROOT / 'tests/fixtures/nontechnical-notes.md').read_text(encoding='utf-8')
    raw = {}
    for part in notes.split('\n## ')[1:]:
        key, text = part.split('\n', 1)
        raw[key] = text.strip()
    sources = [dict(id=key, label=key.replace('-', ' ').capitalize(), kind='person_account', content=text,
                    scope='Fictional first-person note; no independent verification.') for key, text in raw.items()]
    accounts = [
        dict(id='watering-rota', title='Make watering cover visible', period='Spring 2025',
             summary='I drew a paper rota and asked neighbours to choose their days. A neighbour agreed the final rota and arranged cover for two absences. It was used for six weeks; later use is unknown.',
             contribution='Drew the rota and asked neighbours to enter their own days.', sharedCredit='A neighbour agreed the final rota and arranged the absence cover.',
             outcome='The group used the rota for six weeks.', limits=['Later use is unknown.', 'Plant health and time saved were not measured.'], sourceRefs=['garden-note']),
        dict(id='chair-repair', title='Help return a chair to use', period='2024 · month not recorded',
             summary='I cleaned old glue from a loose chair joint and helped clamp it. An experienced volunteer chose the adhesive and checked the repair. The chair returned to use; I would still need help choosing another repair method.',
             contribution='Cleaned away old glue and helped clamp the joint.', sharedCredit='An experienced volunteer selected the adhesive and checked the finished repair.',
             outcome='The chair returned to use.', limits=['Independent repair-method selection is not established.'], sourceRefs=['chair-note']),
        dict(id='display-sketch', title='Plan a display that was never built', period='Autumn 2025',
             summary='I sketched a display using spare boards. Another volunteer located boards, but bad weather cancelled the open day. The display was never built and later use of the sketch is unknown.',
             contribution='Sketched a display using spare boards.', sharedCredit='Another volunteer found boards that could be used.',
             outcome='The event was cancelled; the display remained a sketch.', limits=['No completed display or later reuse is established.'], sourceRefs=['display-note']),
        dict(id='personal-background', title='Unpaid work around other commitments', period='Dates not supplied',
             summary='These are unpaid contributions alongside other commitments. Employment history, qualifications and a target job were not supplied.',
             contribution='Helped with the activities described in the other accounts.', sharedCredit='', outcome='',
             limits=['No employment chronology or qualifications have been supplied.'], sourceRefs=['background-note'])
    ]
    for a in accounts:
        a.update(context='', aim='', decisions=[], questions=[])
    data = dict(schema='career-context/v1', synthetic=True, updatedAt='2026-11-02', reviewStatus='draft',
                person=dict(name='Contributor 01', overview='I help with shared routines and practical tasks, including a supervised repair and an idea that remained unfinished.'), accounts=accounts, sources=sources)
    data['collection'] = [dict(platform='Supplied notes', location='nontechnical-notes.md', access='supplied', status='read',
                               scope='All four fictional notes read. Approximate dates retained; no exhaustive search across these periods.', nextStep='')]
    data['timeline'] = [dict(id=key, period=label, title=a['title'], focus=a['contribution'], actions=[a['contribution']],
                             tension=' '.join(a['limits']), approach=a['sharedCredit'], questions=[], sourceRefs=a['sourceRefs'], accountIds=[a['id']])
                        for key, label, a in [('2024-record','2024 · month not recorded',accounts[1]),('2025-spring','Spring 2025',accounts[0]),('2025-autumn','Autumn 2025',accounts[2])]]
    basis = renderer.sections.evidence_fingerprint(data)
    data['presentation'] = {
        'briefs': {'contextSha256': basis, 'accounts': {
            'watering-rota': ['Drew a paper rota; neighbours chose their own days.', 'A neighbour arranged cover for two absences. The rota was used for six weeks; later use is unknown.'],
            'chair-repair': ['Cleaned old glue and helped clamp a loose chair joint.', 'An experienced volunteer selected the adhesive and checked the repair. The chair returned to use; independent repair-method selection is not claimed.'],
            'display-sketch': ['Sketched a display; another volunteer found spare boards.', 'Bad weather cancelled the event. The display was never built.'],
            'personal-background': ['Unpaid contributions alongside other commitments.', 'No employment dates, qualifications or target job supplied.']}},
        'workGroups': {'contextSha256': basis, 'groups': [
            {'title':'Shared routines', 'kind':'work', 'accountIds':['watering-rota']},
            {'title':'Making & repairing', 'kind':'work', 'accountIds':['chair-repair','display-sketch']},
            {'title':'Personal background', 'kind':'background', 'accountIds':['personal-background']}]},
        'timelineReading': {'contextSha256': basis,
            'periods': {p['id']: {'title':p['title'], 'bullets':[p['focus'],p['tension']], 'accountIds':p['accountIds']} for p in data['timeline']},
            'years': {'2024': {'title':'A supervised chair repair', 'bullets':['Helped return a chair to use under an experienced volunteer’s guidance. The month is not recorded.']},
                      '2025': {'title':'A shared routine and an unfinished idea', 'bullets':['The group used the paper watering rota for six weeks; later use is unknown.', 'A proposed display stayed a sketch after the open day was cancelled.']}}}}
    data['interview'] = dict(schema='interview-preparation/v1', contextSha256=basis, preparedOn='2026-11-02', target=None,
        headline='Explain the watering rota', throughline='A simple shared routine, with clear limits on my contribution.',
        signals=[dict(title='Make the next responsibility visible', reason='The rota records a concrete contribution and shared follow-through.', storyId='watering-rota')],
        stories=[dict(id='watering-rota', tests='Coordination and shared ownership', takeaway='I made cover visible; a neighbour agreed and arranged it.',
                      chapters=[dict(title='Make days visible', text=accounts[0]['summary'])], timeline=[dict(when='Spring 2025', text='Used for six weeks; later use unknown.')])],
        opening=['I help with shared routines and practical tasks. One example is a paper watering rota.'],
        questions=[dict(id='share-responsibility', question='How did you make a shared responsibility easier to follow?', tests='Personal action and shared ownership', storyId='watering-rota', reason='The account distinguishes drawing the rota from arranging cover.', answer=accounts[0]['summary'])], priorityGap=None)
    data['journey'] = renderer.guided_path.initial_state(data, basis)
    data['publicProfile'] = renderer.public_profile.initial_state(data, basis)
    renderer.validate(data)
    return data


if __name__ == '__main__':
    source = ROOT / 'private/nontechnical-trial.json'
    source.write_text(json.dumps({k:v for k,v in packet().items() if k != 'interview' or '--context-only' not in sys.argv}, ensure_ascii=True, indent=2)+'\n', encoding='utf-8', newline='\n')
    result = renderer.render(source, ROOT / 'private/nontechnical-trial.html', guided=True)
    print(json.dumps({k:result[k] for k in ['accounts','sources','sha256']}))
