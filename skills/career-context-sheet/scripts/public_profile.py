"""An explicitly authored public projection, never an automatic evidence export."""
import base64
import binascii
import html
import re
from urllib.parse import urlsplit

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_MEDIA_BYTES = 6 * 1024 * 1024


def safe_video_url(value):
    if not isinstance(value, str) or not value.startswith('https://') or re.search(r'[\s\\\x00-\x1f\x7f]', value):
        return False
    try:
        url = urlsplit(value)
        return bool(url.hostname and not url.username and not url.password and (url.port is None or 0 < url.port < 65536))
    except ValueError:
        return False


def image_bytes(value):
    if not isinstance(value, str) or len(value) > 2800000:
        raise ValueError('Profile screenshots must be at most 2 MiB each')
    match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)', value)
    if not match:
        raise ValueError('Use an embedded PNG, JPEG or WebP screenshot')
    try:
        raw = base64.b64decode(match[2], validate=True)
    except binascii.Error as error:
        raise ValueError('Invalid screenshot encoding') from error
    signatures = {'png': raw.startswith(b'\x89PNG\r\n\x1a\n'), 'jpeg': raw.startswith(b'\xff\xd8\xff'),
                  'webp': raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'}
    if not signatures[match[1]] or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError('Screenshot format or size is invalid')
    return raw


def media_projection(items):
    result = []
    for item in items:
        if item.get('included') is not True:
            continue
        if item['kind'] == 'video' and not safe_video_url(item['url']):
            continue
        fields = ('kind', 'title', 'caption', 'credit', 'alt', 'dataUrl') if item['kind'] == 'image' else ('kind', 'title', 'caption', 'credit', 'url')
        result.append({k: item[k] for k in fields})
    return result


def media_preview(items):
    rows = []
    for item in items:
        esc = html.escape
        caption = ('<p>' + esc(item['caption']) + '</p>' if item['caption'] else '')
        credit = ('<p class="public-media-credit">' + esc(item['credit']) + '</p>' if item['credit'] else '')
        if item['kind'] == 'image':
            rows.append('<article class="public-visual"><details><summary><img src="' + esc(item['dataUrl'], quote=True) + '" alt="' + esc(item['alt'], quote=True) + '" loading="lazy"><span>' + esc(item['title']) + '</span><span class="public-enlarge">View full size</span><span class="public-enlarge public-close">Close full size</span></summary><div class="public-full-image" tabindex="0" role="region" aria-label="Full size screenshot"><img src="' + esc(item['dataUrl'], quote=True) + '" alt="' + esc(item['alt'], quote=True) + '" loading="lazy"></div>' + '</details>' + caption + credit + '</article>')
        else:
            rows.append('<article class="public-video"><a href="' + esc(item['url'], quote=True) + '" target="_blank" rel="noopener noreferrer">' + esc(item['title']) + ' ↗</a><span class="public-video-host">' + esc(urlsplit(item['url']).hostname) + '</span>' + caption + credit + '</article>')
    return '<section class="public-media"><h2>Work samples</h2><div class="public-gallery">' + ''.join(rows) + '</div></section>' if rows else ''


def initial_state(packet, basis):
    # Never infer public permission from a private overview or work account.
    return {'contextSha256': basis, 'updatedAt': 0, 'name': packet['person']['name'],
            'headline': '', 'overview': '', 'shareOverview': False,
            'direction': '', 'shareDirection': False, 'northStar': '', 'shareNorthStar': False, 'media': [], 'examples': [], 'timeline': []}


def validate(packet, check_text, keys):
    profile = packet.get('publicProfile')
    if profile is None:
        return
    keys(profile, ['contextSha256', 'updatedAt', 'name', 'headline', 'overview', 'shareOverview', 'direction', 'shareDirection', 'northStar', 'shareNorthStar', 'media', 'examples', 'timeline'], 'Public profile')
    check_text(profile.get('northStar', ''), 'Profile North Star', 1000)
    if 'shareNorthStar' in profile and type(profile['shareNorthStar']) is not bool:
        raise ValueError('North Star sharing must be boolean')
    media = profile.get('media', [])
    if not isinstance(media, list) or len(media) > 8:
        raise ValueError('Profile allows up to eight work samples')
    ids, total = set(), 0
    for item in media:
        keys(item, ['id', 'kind', 'title', 'caption', 'credit', 'included', 'alt', 'dataUrl', 'url'], 'Profile media')
        if not isinstance(item.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}', item['id']) or item['id'] in ids:
            raise ValueError('Profile media needs unique safe IDs')
        ids.add(item['id'])
        if type(item.get('included')) is not bool or item.get('kind') not in ['image', 'video']:
            raise ValueError('Profile media needs a kind and explicit sharing choice')
        for key, maximum in [('title', 200), ('caption', 1000), ('credit', 500)]:
            check_text(item.get(key), 'Profile media '+key, maximum)
        if item['included'] and not item['title'].strip(): raise ValueError('Shared work samples need a title')
        if item['kind'] == 'image':
            check_text(item.get('alt'), 'Screenshot description', 500)
            if (item['included'] and not item['alt'].strip()) or 'url' in item: raise ValueError('Shared screenshots need a description and embedded bytes only')
            total += len(image_bytes(item.get('dataUrl')))
        else:
            check_text(item.get('url'), 'Video URL', 2000)
            if 'dataUrl' in item or 'alt' in item: raise ValueError('Video samples contain links only')
            if item['included'] and not safe_video_url(item['url']): raise ValueError('Shared videos need an HTTPS link without credentials')
    if total > MAX_MEDIA_BYTES: raise ValueError('Profile screenshots must total at most 6 MiB')
    check_text(profile.get('direction', ''), 'Profile direction', 1500)
    if 'shareDirection' in profile and type(profile['shareDirection']) is not bool:
        raise ValueError('Profile direction sharing must be boolean')
    if 'shareOverview' in profile and type(profile['shareOverview']) is not bool:
        raise ValueError('Profile overview sharing must be boolean')
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
        keys(item, ['title', 'summary', 'synthetic', 'included', 'detail', 'shareDetail'], 'Public example')
        check_text(item.get('detail', ''), 'Public example detail', 2500)
        if 'shareDetail' in item and type(item['shareDetail']) is not bool:
            raise ValueError('Profile detail sharing must be boolean')
        if 'included' in item and type(item['included']) is not bool:
            raise ValueError('Profile example sharing must be boolean')
        check_text(item.get('title'), 'Public example title', 200)
        check_text(item.get('summary'), 'Public example summary', 2000)
        if type(item.get('synthetic')) is not bool:
            raise ValueError('Public example needs an explicit synthetic flag')


    timeline = profile.get('timeline', [])
    if not isinstance(timeline, list) or len(timeline) > 30:
        raise ValueError('Public timeline allows up to 30 entries')
    for entry in timeline:
        keys(entry, ['period', 'title', 'summary', 'included'], 'Public timeline entry')
        if 'included' in entry and type(entry['included']) is not bool:
            raise ValueError('Profile period sharing must be boolean')
        for field, limit in [('period', 60), ('title', 200), ('summary', 1500)]:
            check_text(entry.get(field), 'Public timeline ' + field, limit)


def projection(profile):
    """Only selected, deliberately authored components cross the sharing boundary."""
    return {'name': profile['name'], 'headline': profile['headline'],
            'overview': profile['overview'] if profile.get('shareOverview', True) else '',
            'direction': profile.get('direction', '') if profile.get('shareDirection', False) else '',
            'northStar': profile.get('northStar', '') if profile.get('shareNorthStar', False) else '',
            'media': media_projection(profile.get('media', [])),
            'examples': [{**{k: e[k] for k in ('title', 'summary', 'synthetic')},
                          'detail': e.get('detail', '') if e.get('shareDetail', False) else ''}
                         for e in profile['examples'] if e.get('included', True)],
            'timeline': [{k: e[k] for k in ('period', 'title', 'summary')}
                         for e in profile.get('timeline', []) if e.get('included', True)]}


def timeline_preview(profile):
    rows = ''.join('<details class="public-year"><summary><span>' + html.escape(e['period']) + '</span><strong>' + html.escape(e['title']) + '</strong><span aria-hidden="true">+</span></summary><p>' + html.escape(e['summary']) + '</p></details>' for e in profile.get('timeline', []) if any(e.values()))
    return '<section class="public-timeline"><h2>Over time</h2><div>' + rows + '</div></section>' if rows else ''


def preview(profile, synthetic=False):
    profile = projection(profile)
    esc = html.escape
    examples = ''.join('<article class="public-example"><h2>' + esc(e['title']) + '</h2><div>'
                       + ('<p class="public-synthetic">Synthetic example</p>' if e['synthetic'] else '')
                       + '<p>' + esc(e['summary']) + '</p>'
                       + ('<details class="public-detail"><summary>More context</summary><p>' + esc(e['detail']) + '</p></details>' if e['detail'] else '')
                       + '</div></article>' for e in profile['examples'] if e['title'] or e['summary'])
    return ('<article class="profile-page"><header class="public-intro"><p class="public-name">' + esc(profile['name'])
            + '</p><div><h1>' + esc(profile['headline']) + '</h1><p class="public-overview">' + esc(profile['overview'])
            + '</p></div></header>' + ('<p class="public-synthetic">Synthetic demo data</p>' if synthetic else '')
            + ''.join('<section class="public-direction"><h2>' + label + '</h2><p>' + esc(profile[key]) + '</p></section>' for key, label in [('northStar', 'North Star'), ('direction', 'Direction')] if profile[key])
            + '<div class="public-examples">' + examples + '</div>' + media_preview(profile['media']) + timeline_preview(profile) + '</article>')


def render(packet, basis):
    if 'publicProfile' not in packet:
        return ''
    markup = '''<section id="profile" class="document-view public-profile-shell" aria-labelledby="public-title" data-evidence="''' + basis + '''">
<div class="public-toolbar js-only"><h2 id="public-title">Profile</h2><div class="public-switch" role="group" aria-label="Profile view"><button type="button" id="public-preview-tab" aria-pressed="true">Preview</button><button type="button" id="public-edit-tab" aria-pressed="false">Edit</button></div><span id="public-share-count" aria-live="polite"></span><button type="button" class="path-primary" id="public-export">Download selected profile <span aria-hidden="true">↓</span></button></div>
<div class="public-context js-only"><details class="public-sharing" open><summary>Choose what to share</summary><p>Name and headline are always included. Unselected drafts stay private.</p><div id="public-sharing"></div></details><details><summary>Sharing guidance</summary><p>Describe the problem, your contribution and the general approach. Omit confidential names, dates, figures, internal methods and identifying combinations. Anonymising a name alone may leave the work recognisable.</p><p>Use “Synthetic example” only for newly invented or reconstructed demonstrations with no confidential data. It does not make a real private account safe to share.</p><p>Selected screenshots are embedded in the download; video links open the external site only when clicked. Check images, captions, credits and URLs for private information. This downloads a local file; nothing is published. Included details travel with it even when collapsed. Access cannot be revoked.</p></details></div>
<p id="public-status" class="public-status js-only" role="status"></p>
<div id="public-freshness" class="public-freshness js-only" hidden><p>Your private context has changed. Check this profile against the current record.</p><button type="button" class="path-secondary" id="public-mark-reviewed">Mark profile reviewed</button></div>
<div id="public-editor" class="js-only" hidden></div><div id="public-preview">''' + preview(packet['publicProfile'], packet.get('synthetic', False)) + '''</div>
<p id="public-empty" class="js-only" hidden>Add a name, headline and at least one selected component to export.</p>
<div class="public-footer js-only"><a href="#path-write">Back to your context</a><button type="button" class="path-secondary" id="public-save">Save private working file</button></div>
</section>'''

    if 'journey' not in packet:
        markup = markup.replace('href="#path-write"', 'href="#work"')
    return markup
