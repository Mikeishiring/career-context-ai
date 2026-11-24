"""SQLite-cached local ONNX semantic & hybrid RRF search over BOTH source chunks AND episodes.

- Stores compact float16 vectors in SQLite `embeddings_cache` (50% smaller than float32).
- Indexes both `source_chunks` and `episodes` so paraphrased queries rank episodes AND raw evidence accurately.
- Caches the ONNX session in-process so warm queries inside the localhost Studio UI run in ~30-80ms!
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .db import CareerVault, sha256_text

MODEL_ID = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MAX_TOKENS = 256
BATCH_SIZE = 32

_RUNTIME_CACHE: dict[str, tuple[Any, Any, Any, set[str]]] = {}


def _load_runtime(model_dir: str | Path):
    mdir = str(Path(model_dir).expanduser().resolve())
    if mdir in _RUNTIME_CACHE:
        return _RUNTIME_CACHE[mdir]
    try:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Cached semantic search needs numpy, onnxruntime, and tokenizers (optional)."
        ) from exc

    p = Path(mdir)
    model_path = p / "model.onnx"
    tok_path = p / "tokenizer.json"
    if not model_path.is_file() or not tok_path.is_file():
        raise FileNotFoundError(f"Expected model.onnx and tokenizer.json in {p}")
    tok = Tokenizer.from_file(str(tok_path))
    tok.enable_truncation(max_length=MAX_TOKENS)
    tok.enable_padding(pad_id=0, pad_token="[PAD]")
    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_names = {i.name for i in sess.get_inputs()}
    bundle = (np, sess, tok, input_names)
    _RUNTIME_CACHE[mdir] = bundle
    return bundle


def _embed_batch(np, sess, tok, input_names: set[str], texts: list[str]):
    vecs = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        encs = tok.encode_batch(batch)
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feeds: dict[str, Any] = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(ids, dtype=np.int64)
        out = sess.run(None, feeds)[0]
        cls = out[:, 0, :].astype(np.float32)
        norms = np.linalg.norm(cls, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs.append(cls / norms)
    return np.vstack(vecs) if vecs else np.zeros((0, 384), dtype=np.float32)


def _episode_embed_text(ep: dict[str, Any]) -> str:
    parts = [
        ep["title"],
        ep["summary_l1"],
        ep["context_l1"],
        ep["contribution_l1"],
        " ".join(ep["decisions"]),
        ep["outcome_l1"],
        " ".join(ep["tags"]),
    ]
    return "\n".join(p for p in parts if p).strip()


def sync_embeddings(vault: CareerVault, model_dir: str | Path) -> dict[str, Any]:
    """Embed any uncached source chunks AND episodes as compact float16 BLOBs in SQLite."""
    t0 = time.perf_counter()

    # 1. Uncached source chunks
    chunk_rows = vault.conn.execute(
        """SELECT DISTINCT sc.chunk_sha256 AS sha, sc.text
           FROM source_chunks sc
           LEFT JOIN embeddings_cache ec
             ON ec.content_sha256 = sc.chunk_sha256 AND ec.model_id = ?
           WHERE ec.content_sha256 IS NULL AND length(trim(sc.text)) > 0""",
        (MODEL_ID,),
    ).fetchall()

    # 2. Uncached episodes (keyed by hash of their searchable text)
    episodes = vault.list_episodes()
    ep_pending: list[tuple[str, str]] = []
    cached_shas = {
        r[0]
        for r in vault.conn.execute(
            "SELECT content_sha256 FROM embeddings_cache WHERE model_id = ?", (MODEL_ID,)
        ).fetchall()
    }
    for ep in episodes:
        txt = _episode_embed_text(ep)
        if not txt:
            continue
        sha = sha256_text(txt)
        if sha not in cached_shas:
            ep_pending.append((sha, txt))
            cached_shas.add(sha)

    pending_shas = [r["sha"] for r in chunk_rows] + [s for s, _ in ep_pending]
    pending_texts = [r["text"] for r in chunk_rows] + [t for _, t in ep_pending]

    total_chunks = vault.conn.execute("SELECT COUNT(DISTINCT chunk_sha256) FROM source_chunks").fetchone()[0]
    total_items = total_chunks + len(episodes)

    if not pending_texts:
        return {
            "model": MODEL_ID,
            "dtype": "float16",
            "total_items": total_items,
            "newly_embedded": 0,
            "cached": total_items,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    np, sess, tok, input_names = _load_runtime(model_dir)
    mat = _embed_batch(np, sess, tok, input_names, pending_texts)

    with vault.conn:
        for sha, vec in zip(pending_shas, mat):
            blob = vec.astype(np.float16).tobytes()
            vault.conn.execute(
                """INSERT OR REPLACE INTO embeddings_cache(content_sha256, model_id, dim, dtype, vector, created_at)
                   VALUES (?,?,?,'float16',?,datetime('now'))""",
                (sha, MODEL_ID, int(vec.shape[0]), blob),
            )
    return {
        "model": MODEL_ID,
        "dtype": "float16",
        "total_items": total_items,
        "newly_embedded": len(pending_texts),
        "cached": max(0, total_items - len(pending_texts)),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def _decode_matrix(np, rows: list[Any]):
    if not rows:
        return None
    dtype = np.float16 if rows[0]["dtype"] == "float16" else np.float32
    return np.frombuffer(b"".join(r["vector"] for r in rows), dtype=dtype).reshape(len(rows), -1).astype(np.float32)


def hybrid_search(
    vault: CareerVault,
    query: str,
    model_dir: str | Path,
    *,
    channel: str | None = None,
    limit: int = 12,
    min_similarity: float = 0.45,
) -> dict[str, Any]:
    """Hybrid FTS5 + SQLite-cached float16 ONNX semantic search (RRF) over BOTH sources AND episodes."""
    t0 = time.perf_counter()
    sync_stats = sync_embeddings(vault, model_dir)
    t_sync = time.perf_counter()

    # 1. Lexical FTS5 candidates
    fts = vault.search(query, channel=channel, limit=limit * 3)

    # 2. Vectorized cosine similarity over cached source chunks AND episodes
    np, sess, tok, input_names = _load_runtime(model_dir)
    q_vec = _embed_batch(np, sess, tok, input_names, [QUERY_PREFIX + query])[0]

    # 2a. Source chunks
    sql = """
        SELECT sc.source_id, sc.text, ec.vector, ec.dtype,
               s.channel, s.title, s.event_date, s.sensitivity, s.url
        FROM source_chunks sc
        JOIN embeddings_cache ec ON ec.content_sha256 = sc.chunk_sha256 AND ec.model_id = ?
        JOIN sources s ON s.id = sc.source_id
    """
    params: list[Any] = [MODEL_ID]
    if channel:
        sql += " WHERE s.channel = ?"
        params.append(channel.lower())
    rows = vault.conn.execute(sql, params).fetchall()
    sem_by_source: dict[str, dict[str, Any]] = {}
    if rows:
        mat = _decode_matrix(np, rows)
        sims = mat @ q_vec
        for row, sim in zip(rows, sims.tolist()):
            if sim < min_similarity:
                continue
            sid = row["source_id"]
            prev = sem_by_source.get(sid)
            if prev is None or sim > prev["similarity"]:
                sem_by_source[sid] = {
                    "source_id": sid,
                    "channel": row["channel"],
                    "title": row["title"],
                    "event_date": row["event_date"],
                    "sensitivity": row["sensitivity"],
                    "url": row["url"],
                    "snippet": row["text"][:260].replace("\n", " "),
                    "similarity": round(float(sim), 4),
                }
    sem_sources = sorted(sem_by_source.values(), key=lambda x: x["similarity"], reverse=True)

    # 2b. Episodes semantic ranking
    episodes = vault.list_episodes()
    ep_vec_map = {
        r["content_sha256"]: (r["vector"], r["dtype"])
        for r in vault.conn.execute(
            "SELECT content_sha256, vector, dtype FROM embeddings_cache WHERE model_id = ?", (MODEL_ID,)
        ).fetchall()
    }
    ep_rows = []
    ep_objs = []
    for ep in episodes:
        sha = sha256_text(_episode_embed_text(ep))
        if sha in ep_vec_map:
            vec, dt = ep_vec_map[sha]
            ep_rows.append({"vector": vec, "dtype": dt})
            ep_objs.append(ep)
    sem_episodes: list[dict[str, Any]] = []
    if ep_rows:
        emat = _decode_matrix(np, ep_rows)
        esims = emat @ q_vec
        for ep, sim in zip(ep_objs, esims.tolist()):
            if sim < min_similarity:
                continue
            sem_episodes.append({
                "episode_id": ep["id"],
                "title": ep["title"],
                "period_label": ep["period_label"],
                "status": ep["status"],
                "role_id": ep["role_id"],
                "snippet": ep["summary_l1"][:220],
                "similarity": round(float(sim), 4),
            })
        sem_episodes.sort(key=lambda x: x["similarity"], reverse=True)

    # 3. Reciprocal Rank Fusion (k=60) for BOTH sources and episodes
    def fuse(fts_list: list[dict[str, Any]], sem_list: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        scores: dict[str, float] = {}
        recs: dict[str, dict[str, Any]] = {}
        for rank, item in enumerate(fts_list, start=1):
            k = item[key]
            scores[k] = scores.get(k, 0.0) + 1.0 / (60 + rank)
            recs[k] = {**item, "methods": ["fts5"]}
        for rank, item in enumerate(sem_list, start=1):
            k = item[key]
            scores[k] = scores.get(k, 0.0) + 1.0 / (60 + rank)
            if k in recs:
                recs[k]["methods"].append("semantic")
                recs[k]["similarity"] = item["similarity"]
            else:
                recs[k] = {**item, "methods": ["semantic"]}
        out = sorted(recs.values(), key=lambda r: scores[r[key]], reverse=True)[:limit]
        for r in out:
            r["rrf_score"] = round(scores[r[key]], 5)
        return out

    fused_sources = fuse(fts["sources"], sem_sources, "source_id")
    fused_episodes = fuse(fts["episodes"], sem_episodes, "episode_id")

    t_end = time.perf_counter()
    return {
        "query": query,
        "method": "hybrid_fts5_plus_cached_float16_onnx_rrf",
        "sync": sync_stats,
        "query_ms": round((t_end - t_sync) * 1000, 1),
        "total_ms": round((t_end - t0) * 1000, 1),
        "sources": fused_sources,
        "episodes": fused_episodes,
    }


def semantic_triage_unlinked(
    vault: CareerVault,
    model_dir: str | Path,
    *,
    attach_threshold: float = 0.70,
    limit: int = 300,
) -> dict[str, Any]:
    """Matrix-multiply cached float16 embeddings of all unlinked sources vs episodes in <50ms."""
    t0 = time.perf_counter()
    sync_embeddings(vault, model_dir)
    import numpy as np

    episodes = vault.list_episodes()
    vec_map = {
        r["content_sha256"]: (r["vector"], r["dtype"])
        for r in vault.conn.execute(
            "SELECT content_sha256, vector, dtype FROM embeddings_cache WHERE model_id = ?", (MODEL_ID,)
        ).fetchall()
    }
    ep_rows, ep_objs = [], []
    for ep in episodes:
        sha = sha256_text(_episode_embed_text(ep))
        if sha in vec_map:
            vec, dt = vec_map[sha]
            ep_rows.append({"vector": vec, "dtype": dt})
            ep_objs.append(ep)

    unlinked = vault.list_sources(unlinked_only=True, limit=limit)
    if not ep_rows or not unlinked:
        return {
            "method": "semantic_float16_triage",
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            "unlinked_examined": len(unlinked),
            "attach_candidates": [],
            "potential_new_clusters": [],
        }

    ep_mat = _decode_matrix(np, ep_rows)  # (E, D)
    # Grab first chunk embedding per unlinked source (or max across all its chunks)
    unlinked_ids = [s["id"] for s in unlinked]
    placeholders = ",".join("?" for _ in unlinked_ids)
    chunk_rows = vault.conn.execute(
        f"""SELECT sc.source_id, ec.vector, ec.dtype
            FROM source_chunks sc
            JOIN embeddings_cache ec ON ec.content_sha256 = sc.chunk_sha256 AND ec.model_id = ?
            WHERE sc.source_id IN ({placeholders})""",
        [MODEL_ID, *unlinked_ids],
    ).fetchall()

    best_per_source: dict[str, tuple[float, int]] = {}
    if chunk_rows:
        c_mat = _decode_matrix(np, chunk_rows)  # (C, D)
        sims = c_mat @ ep_mat.T  # (C, E)
        max_idx = np.argmax(sims, axis=1)
        max_val = sims[np.arange(len(chunk_rows)), max_idx]
        for row, score, eidx in zip(chunk_rows, max_val.tolist(), max_idx.tolist()):
            sid = row["source_id"]
            prev = best_per_source.get(sid)
            if prev is None or score > prev[0]:
                best_per_source[sid] = (float(score), int(eidx))

    attach_candidates: list[dict[str, Any]] = []
    orphan_clusters: dict[str, list[dict[str, Any]]] = {}
    for s in unlinked:
        match = best_per_source.get(s["id"])
        if match and match[0] >= attach_threshold:
            score, eidx = match
            ep = ep_objs[eidx]
            attach_candidates.append({
                "source_id": s["id"],
                "channel": s["channel"],
                "title": s["title"],
                "event_date": s["event_date"],
                "suggested_episode_id": ep["id"],
                "suggested_episode_title": ep["title"],
                "similarity": round(score, 4),
                "method": "semantic_float16",
            })
        else:
            ym = (s["event_date"] or "undated")[:7]
            ck = f"{s['channel']} · {ym}"
            orphan_clusters.setdefault(ck, []).append({
                "source_id": s["id"],
                "channel": s["channel"],
                "title": s["title"],
                "event_date": s["event_date"],
                "best_sim": round(match[0], 4) if match else 0.0,
                "preview": s["preview"][:140],
            })

    attach_candidates.sort(key=lambda x: x["similarity"], reverse=True)
    clusters = [
        {"cluster": k, "count": len(v), "sources": v[:10]}
        for k, v in sorted(orphan_clusters.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]
    return {
        "method": "semantic_float16_triage",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        "unlinked_examined": len(unlinked),
        "attach_threshold": attach_threshold,
        "attach_candidates": attach_candidates,
        "potential_new_clusters": clusters,
    }

