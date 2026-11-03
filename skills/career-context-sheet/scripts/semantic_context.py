"""Local embeddings over selected text. Only explicit model preparation uses a network."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

MODEL = 'BAAI/bge-small-en-v1.5'
REVISION = '5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'
FILES = {
    'model.onnx': ('onnx/model.onnx', 133093490,
                   '828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35'),
    'tokenizer.json': ('tokenizer.json', 711396,
                       'd241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66'),
}
WINDOW = 224
OVERLAP = 32
MAX_CHUNKS = 32768
BATCH = 16


def verified_bytes(directory, name):
    path = Path(directory).expanduser() / name
    _, size, expected = FILES[name]
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
        raise ValueError('Missing or invalid local semantic model. Run semantic_context.py prepare explicitly.')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Local semantic model checksum mismatch; inference is blocked.')
    return raw


def prepare(directory, *, download=False):
    """Fetch only pinned public artifacts; this function accepts no career data."""
    if not download:
        raise ValueError('Model setup needs --download; retrieval itself never downloads anything.')
    import urllib.request
    directory = Path(directory).expanduser().absolute()
    if directory.is_symlink():
        raise ValueError('Use a real model directory, not a symbolic link.')
    directory.mkdir(parents=True, exist_ok=True)
    # Do not silently repair or overwrite files the user already supplied.
    for name in FILES:
        if (directory / name).exists() or (directory / name).is_symlink():
            verified_bytes(directory, name)
    for name, (remote, size, expected) in FILES.items():
        if (directory / name).exists():
            continue
        fd, temporary = tempfile.mkstemp(dir=directory, prefix='.semantic-')
        try:
            request = urllib.request.Request(f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{remote}')
            with os.fdopen(fd, 'wb') as target, urllib.request.urlopen(request, timeout=60) as response:
                hasher, total = hashlib.sha256(), 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > size:
                        raise ValueError('Model download exceeded its pinned size.')
                    hasher.update(block)
                    target.write(block)
            if total != size or hasher.hexdigest() != expected:
                raise ValueError('Downloaded model checksum mismatch; file was not installed.')
            # Exclusive publication also protects concurrent preparation.
            if os.name == 'nt':
                os.rename(temporary, directory / name)
            else:
                os.link(temporary, directory / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {'model': MODEL, 'revision': REVISION, 'bytes': sum(f[1] for f in FILES.values()),
            'directory': str(directory), 'careerDataRead': False}


class LocalEncoder:
    """Pinned data files, CPU kernels, no hub client, model code or remote endpoint."""
    query_prefix = 'Represent this sentence for searching relevant passages: '

    def __init__(self, directory):
        model = verified_bytes(directory, 'model.onnx')
        tokenizer = verified_bytes(directory, 'tokenizer.json')
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as error:
            raise ValueError('Semantic search needs the optional packages in scripts/semantic-requirements.txt.') from error
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.enable_profiling = False
        options.intra_op_num_threads = min(4, os.cpu_count() or 1)
        self.session = ort.InferenceSession(model, sess_options=options, providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_str(tokenizer.decode('utf-8'))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.np = np
        self.metadata = {'model': MODEL, 'revision': REVISION,
                         'modelSha256': FILES['model.onnx'][2], 'tokenizerSha256': FILES['tokenizer.json'][2],
                         'runtime': 'onnxruntime CPU', 'runtimeVersion': ort.__version__,
                         'processing': 'local_only', 'pooling': 'CLS', 'queryPrefix': self.query_prefix,
                         'windowTokens': WINDOW, 'overlapTokens': OVERLAP}

    def passages(self, text):
        encoded = self.tokenizer.encode(text, add_special_tokens=False)
        for i in range(0, len(encoded.ids), WINDOW - OVERLAP):
            end = min(i + WINDOW, len(encoded.ids))
            start_offset, end_offset = encoded.offsets[i][0], encoded.offsets[end - 1][1]
            if end_offset > start_offset:
                yield start_offset, end_offset, encoded.ids[i:end]
            if end == len(encoded.ids):
                break

    def encode(self, token_batches):
        np = self.np
        if any(not ids or len(ids) > WINDOW for ids in token_batches):
            raise ValueError('Semantic input must fit a nonempty token window.')
        length = max(map(len, token_batches)) + 2
        ids = np.zeros((len(token_batches), length), dtype=np.int64)
        mask = np.zeros_like(ids)
        for i, tokens in enumerate(token_batches):
            row = [101, *tokens, 102]  # Pinned BERT tokenizer: CLS, content, SEP.
            ids[i, :len(row)] = row
            mask[i, :len(row)] = 1
        hidden = self.session.run(None, {'input_ids': ids, 'attention_mask': mask,
                                        'token_type_ids': np.zeros_like(ids)})[0]
        if hidden.shape != (len(token_batches), length, 384):
            raise ValueError('Unexpected semantic model output shape.')
        # BGE's documented CLS pooling, followed by normalization below.
        return hidden[:, 0]


def unit_vectors(encoder, inputs, dimensions=None):
    output = encoder.encode(inputs)
    if len(output) != len(inputs):
        raise ValueError('Semantic encoder returned an incomplete batch.')
    rows = []
    for raw in output:
        row = tuple(float(v) for v in raw)
        if not row or any(not math.isfinite(v) for v in row) or (dimensions is not None and len(row) != dimensions):
            raise ValueError('Semantic encoder returned invalid vectors.')
        dimensions = len(row)
        norm = math.sqrt(math.fsum(v * v for v in row))
        if not math.isfinite(norm) or norm == 0:
            raise ValueError('Semantic encoder returned a zero or invalid vector.')
        rows.append(tuple(v / norm for v in row))
    return rows


def rank(queries, fields, encoder, minimum=0.5):
    """Stream bounded exact spans; keep the strongest reading lead per record."""
    if not isinstance(minimum, (int, float)) or isinstance(minimum, bool) or not math.isfinite(minimum) or not 0 <= minimum <= 1:
        raise ValueError('Minimum similarity must be between zero and one.')
    query_tokens = []
    for query in queries:
        chunks = list(encoder.passages(getattr(encoder, 'query_prefix', '') + query))
        if len(chunks) != 1:
            raise ValueError('Use a shorter, nonempty semantic query.')
        query_tokens.append(chunks[0][2])
    vectors = unit_vectors(encoder, query_tokens)
    hits, batch, count = {}, [], 0

    def flush():
        embeddings = unit_vectors(encoder, [item[-1] for item in batch], len(vectors[0]))
        for (layer, key, field, text, start, end, _), vector in zip(batch, embeddings):
            scores = [math.fsum(a * b for a, b in zip(vector, query)) for query in vectors]
            chosen = max(range(len(scores)), key=scores.__getitem__)
            score = max(-1.0, min(1.0, scores[chosen]))
            if score < minimum or ((layer, key) in hits and score <= hits[layer, key]['similarity']):
                continue
            hits[layer, key] = {'query': queries[chosen], 'field': field, 'start': start, 'end': end,
                               'quote': text[start:end], 'fieldSha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                               'similarity': score}
        batch.clear()

    for layer, key, field, text in fields:
        for start, end, tokens in encoder.passages(text):
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                raise ValueError('Semantic encoder returned an invalid source span.')
            count += 1
            if count > MAX_CHUNKS:
                raise ValueError('Semantic scope exceeds 32768 chunks. Select fewer layers or a smaller packet; nothing was truncated.')
            batch.append((layer, key, field, text, start, end, tokens))
            if len(batch) == BATCH:
                flush()
    if batch:
        flush()
    return hits, count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--download', action='store_true', help='Explicitly download the pinned public model; no source data is read')
    args = parser.parse_args(argv)
    try:
        result = prepare(args.directory, download=args.download)
    except (ValueError, OSError) as error:
        parser.exit(2, f'Could not prepare semantic model: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
