"""本地向量嵌入（无需 numpy / 外网模型）：字符 n-gram 哈希 + 纯 Python 余弦相似度。"""

from __future__ import annotations

import hashlib
import json
import math
import re

DIM = 384


def _tokenize(text: str) -> list[str]:
    text = (text or "").lower().strip()
    if not text:
        return []
    en = re.findall(r"[a-z0-9_]+", text)
    zh = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    grams: list[str] = []
    grams.extend(en)
    grams.extend(zh)
    for i in range(len(zh) - 1):
        grams.append(zh[i] + zh[i + 1])
    for i in range(len(zh) - 2):
        grams.append(zh[i] + zh[i + 1] + zh[i + 2])
    return grams


def embed_text(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for tok in tokens:
        h = hashlib.md5(tok.encode("utf-8")).hexdigest()
        idx = int(h[:8], 16) % dim
        sign = 1.0 if int(h[8:10], 16) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def embedding_to_json(vec: list[float]) -> str:
    return json.dumps(vec)


def embedding_from_json(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    try:
        arr = json.loads(raw)
        if not isinstance(arr, list) or not arr:
            return None
        return [float(x) for x in arr]
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(a[i] * a[i] for i in range(n)))
    nb = math.sqrt(sum(b[i] * b[i] for i in range(n)))
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def top_k_by_vector(
    query_vec: list[float],
    candidates: list[tuple[str, list[float], dict]],
    top_n: int = 5,
    min_score: float = 0.05,
) -> list[dict]:
    scored = []
    for key, vec, payload in candidates:
        score = cosine_similarity(query_vec, vec)
        if score >= min_score:
            item = dict(payload)
            item["score"] = round(score, 6)
            item["_key"] = key
            scored.append(item)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]
