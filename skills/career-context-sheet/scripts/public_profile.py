"""An explicitly authored public projection, never an automatic evidence export."""
import html
import re


def initial_state(packet, basis):
    # Never infer public permission from a private overview or work account.
    return {'contextSha256': basis, 'updatedAt': 0, 'name': packet['person']['name'],
            'headline': '', 'overview': '', 'examples': []}


def validate(packet, check_text, keys):
    profile = packet.get('publicProfile')
    if profile is None:
        return
    keys(profile, ['contextSha256', 'updatedAt', 'name', 'headline', 'overview', 'examples'], 'Public profile')
    if not isinstance(profile.get('contextSha256'), str) or not re.fullmatch('[a-f0-9]{64}', profile['contextSha256']):
        raise ValueError('Public profile needs its evidence fingerprint')
    if type(profile.get('updatedAt')) is not int or not 0 <= profile['updatedAt'] <= 9007199254740991:
        raise ValueError('Public profile needs a safe update time')
    for field, limit in [('name', 200), ('headline', 200), ('overview', 3000)]:
        check_text(profile.get(field), 'Public ' + field, limit)
    examples = profile.get('examples')
    if not isinstance(examples, list) or len(examples) > 8:
        raise ValueError('Public profile allows up to eight examples')
    for item in examples:
        keys(item, ['title', 'summary', 'synthetic'], 'Public example')
        check_text(item.get('title'), 'Public example title', 200)
        check_text(item.get('summary'), 'Public example summary', 2000)
        if type(item.get('synthetic')) is not bool:
            raise ValueError('Public example needs an explicit synthetic flag')


def preview(profile, synthetic=False):
    esc = html.escape
    examples = ''.join('<article class="public-example"><h2>' + esc(e['title']) + '</h2><div>'
                       + ('<p class="public-synthetic">Synthetic example</p>' if e['synthetic'] else '')
                       + '<p>' + esc(e['summary']) + '</p></div></article>' for e in profile['examples'] if e['title'] or e['summary'])
    return ('<article class="profile-page"><header class="public-intro"><p class="public-name">' + esc(profile['name'])
            + '</p><div><h1>' + esc(profile['headline']) + '</h1><p class="public-overview">' + esc(profile['overview'])
            + '</p></div></header>' + ('<p class="public-synthetic">Synthetic demo data</p>' if synthetic else '')
            + '<div class="public-examples">' + examples + '</div></article>')


def render(packet, basis):
    if 'publicProfile' not in packet:
        return ''
    markup = '''<section id="profile" class="document-view public-profile-shell" aria-labelledby="public-title" data-evidence="''' + basis + '''">
<div class="public-toolbar js-only"><h2 id="public-title">Profile</h2><div class="public-switch" role="group" aria-label="Profile view"><button type="button" id="public-preview-tab" aria-pressed="true">Preview</button><button type="button" id="public-edit-tab" aria-pressed="false">Edit</button></div><button type="button" class="path-primary" id="public-export">Export public HTML <span aria-hidden="true">↗</span></button></div>
<div class="public-context js-only"><p>Only this profile is exported. Check the wording for confidential details.</p><details><summary>What belongs here?</summary><p>Describe the problem, your role and the general approach. Omit confidential names, dates, figures, internal methods and identifying combinations. Anonymising a name alone may leave the work recognisable.</p><p>Use “Synthetic example” only for newly invented or reconstructed demonstrations with no confidential data. It does not make a real private account safe to share.</p></details></div>
<p id="public-status" class="public-status js-only" role="status"></p>
<div id="public-editor" class="js-only" hidden></div><div id="public-preview">''' + preview(packet['publicProfile'], packet.get('synthetic', False)) + '''</div>
<p id="public-empty" class="js-only" hidden>Add a name, headline and overview to export.</p>
<div class="public-footer js-only"><a href="#path-write">Refine your wording</a><button type="button" class="path-secondary" id="public-save">Save private working file</button></div>
</section>'''

    if 'journey' not in packet:
        markup = markup.replace('href="#path-write"', 'href="#work"').replace('start with your writing style', 'review your work').replace('Refine your wording', 'Review your work')
    return markup
