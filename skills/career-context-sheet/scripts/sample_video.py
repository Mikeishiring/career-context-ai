"""Extract bounded candidate stills from a local video; selection remains a human/agent judgment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sample(source, output, count=8, times=None, force=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise ValueError('Choose an existing local video; this helper does not download media.')
    if not 2 <= count <= 16:
        raise ValueError('Use 2 to 16 candidate frames.')
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise ValueError('FFmpeg and ffprobe are unavailable. Use an available video viewer instead.')
    info = json.loads(subprocess.run([ffprobe, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries', 'format=duration',
                                     '-of', 'json', str(source)], check=True, capture_output=True, text=True).stdout)
    duration = float(info['format']['duration'])
    if not 0 < duration < 86400:
        raise ValueError('Use a video shorter than 24 hours with a known positive duration.')
    stamps = times if times is not None else [duration * (i + 1) / (count + 1) for i in range(count)]
    if not 1 <= len(stamps) <= 16 or any(not 0 <= t < duration for t in stamps) or len(set(stamps)) != len(stamps):
        raise ValueError('Use 1 to 16 distinct timestamps within the video.')
    frames = [output / f'candidate-{i+1:02d}.png' for i in range(len(stamps))]
    receipt = output / 'candidates.json'
    if source in frames + [receipt]:
        raise ValueError('Output must not replace the source.')
    if any(p.is_symlink() for p in frames + [receipt]):
        raise ValueError('Candidate outputs must not be symlinks.')
    if not force and any(p.exists() for p in frames + [receipt]):
        raise ValueError('Candidate files exist. Choose an empty output or explicitly use --force.')
    output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    records = []
    for target, stamp in zip(frames, stamps):
        subprocess.run([ffmpeg, '-v', 'error', '-y' if force else '-n', '-ss', f'{stamp:.6f}', '-protocol_whitelist', 'file,pipe', '-i', str(source),
                        '-frames:v', '1', '-update', '1', str(target)], check=True, capture_output=True)
        if not target.is_file() or not target.stat().st_size:
            raise ValueError(f'No frame decoded at {stamp:.3f}s.')
        records.append({'file': target.name, 'seconds': round(stamp, 6),
                        'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    result = {'source': str(source), 'sourceSha256': digest.hexdigest(), 'durationSeconds': duration,
              'reviewScope': 'Candidate stills only; not a full video or audio review.', 'candidates': records}
    receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source'); parser.add_argument('output')
    parser.add_argument('--count', type=int, default=8)
    parser.add_argument('--times', help='Comma-separated seconds for a focused second pass.')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    try:
        result = sample(args.source, args.output, args.count,
                        [float(t) for t in args.times.split(',')] if args.times else None, args.force)
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        parser.exit(2, f'Could not sample the video: {error}\n')
    print(json.dumps({'frames': len(result['candidates']), 'durationSeconds': result['durationSeconds'],
                      'receipt': str(Path(args.output) / 'candidates.json')}))


if __name__ == '__main__':
    main()
