"""
句级显式对齐：按冲击维度关键词筛选句子，
对前后声明中筛出的句子做 TF-IDF 向量余弦相似度，贪心一对一匹配，输出可审计句对。

不调用大模型；供 run_batch 与附录导出复用。
"""
from __future__ import annotations

import json
import re
from typing import Any

# 与 run_batch.SHOCK_KEYS 顺序、语义一致
SHOCK_KEYS = [
    "interest_rate_path",
    "inflation_concern",
    "growth_concern",
    "labor_market",
    "financial_stability",
]

# 每类冲击：用于筛选句子的关键词（小写匹配子串）
SHOCK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "interest_rate_path": (
        "federal funds",
        "target range",
        "policy stance",
        "adjustments",
        "extent and timing",
        "additional adjustments",
        "monetary policy",
        "hold",
        "patient",
        "data-dependent",
        "data dependent",
        "committee decided",
        "stance of monetary",
    ),
    "inflation_concern": (
        "inflation",
        "price stability",
        "pce",
        "2 percent",
        "two percent",
        "expectations",
        "elevated",
        "symmetric",
    ),
    "growth_concern": (
        "economic activity",
        "growth",
        "expanding",
        "pace",
        "outlook",
        "downside",
        "risks",
        "demand",
        "gdp",
    ),
    "labor_market": (
        "employment",
        "labor market",
        "job gains",
        "unemployment",
        "maximum employment",
        "tight",
    ),
    "financial_stability": (
        "financial",
        "credit",
        "banking",
        "market functioning",
        "international developments",
        "conditions",
        "liquidity",
    ),
}


def split_sentences(text: str) -> list[str]:
    """按句切分（英文声明：句号/问号/叹号 + 空格）。"""
    if text is None or not str(text).strip():
        return []
    t = re.sub(r"\s+", " ", str(text).strip())
    parts = re.split(r"(?<=[.!?])\s+", t)
    return [p.strip() for p in parts if p.strip()]


def sentence_hits_keywords(sentence: str, keywords: tuple[str, ...]) -> bool:
    low = sentence.lower()
    return any(kw in low for kw in keywords)


def _greedy_match_pairs(
    prev_sents: list[str],
    curr_sents: list[str],
    min_cosine: float,
) -> list[dict[str, Any]]:
    if not prev_sents or not curr_sents:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as e:
        raise ImportError(
            "句级余弦对齐需要 scikit-learn，请执行: pip install scikit-learn"
        ) from e

    all_text = prev_sents + curr_sents
    vec = TfidfVectorizer(
        lowercase=True,
        token_pattern=r"(?u)\b\w\w+\b",
        max_features=8192,
    )
    try:
        X = vec.fit_transform(all_text)
    except ValueError:
        return []

    n_p = len(prev_sents)
    Xp = X[:n_p]
    Xc = X[n_p:]
    sim = cosine_similarity(Xp, Xc)
    triples: list[tuple[float, int, int]] = []
    for i in range(n_p):
        for j in range(len(curr_sents)):
            c = float(sim[i, j])
            if c >= min_cosine:
                triples.append((c, i, j))
    triples.sort(key=lambda x: -x[0])
    used_i: set[int] = set()
    used_j: set[int] = set()
    pairs: list[dict[str, Any]] = []
    for c, i, j in triples:
        if i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        pairs.append(
            {
                "previous_sentence": prev_sents[i],
                "current_sentence": curr_sents[j],
                "cosine": round(c, 4),
            }
        )
    return pairs


def build_keyword_cosine_alignment(
    prev: str,
    curr: str,
    min_cosine: float = 0.12,
) -> dict[str, Any]:
    """
    对五类冲击分别：关键词筛句 → TF-IDF 余弦 → 贪心句对匹配。
    """
    prev_sents = split_sentences(prev)
    curr_sents = split_sentences(curr)
    out: dict[str, Any] = {
        "method": "keyword_filter_tfidf_cosine_greedy",
        "min_cosine": min_cosine,
        "prev_sentence_count": len(prev_sents),
        "curr_sentence_count": len(curr_sents),
        "by_shock": {},
    }
    for key in SHOCK_KEYS:
        kws = SHOCK_KEYWORDS[key]
        p_f = [s for s in prev_sents if sentence_hits_keywords(s, kws)]
        c_f = [s for s in curr_sents if sentence_hits_keywords(s, kws)]
        pairs = _greedy_match_pairs(p_f, c_f, min_cosine)
        out["by_shock"][key] = {
            "keywords_preview": list(kws[:16]),
            "prev_filtered_count": len(p_f),
            "curr_filtered_count": len(c_f),
            "matched_pairs": pairs,
        }
    return out


def alignment_to_json_str(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
