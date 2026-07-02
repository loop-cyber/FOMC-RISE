#!/usr/bin/env python3
"""
FOMC RAG 检索与后续流水线：

【默认：完整流水线】
  检索召回（四阶段漏斗）→ 数据聚合（相似度加权基准）→ 归因生成（CoT Prompt / 可选 LLM）

四阶段漏斗：
  1) 硬过滤：宏观 Z 与会议类型
  2) 冲击组合分：分数 = α·正向余弦相似度 + β·(1 - 标准化距离) - γ·标准化惩罚，取前 pool_shock 个候选
  3) 证据句：TF-IDF 余弦，取前 pool_evidence 个候选
  4) 语义精排：优先使用大模型声明嵌入（fomc_statement_embeddings_api.npy），取前 k 个案例

聚合：对前 k 个案例用 similarity_for_baseline 做加权平均，得到 SPY/GLD/QQQ/UUP 基准预期。

生成：拼装系统提示词和用户提示词，写入 outputs/retrieval/fomc_cot_prompts.jsonl；若指定
      --generate-llm，则调用百炼 OpenAI 兼容 /v1/chat/completions 写入
      outputs/retrieval/case_explanations.md。

【兼容】--legacy-export：仍写出原先 fomc_retrieval_neighbors_{svd,api}.csv。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# RAG 之前：政策冲击表在 data/processed/；build_rag_corpus 产物在 data/rag_corpus/
DEFAULT_SHOCKS = PROJECT_ROOT / "data" / "processed" / "fomc_policy_shocks.csv"
DEFAULT_RAG_CORPUS_DIR = PROJECT_ROOT / "data" / "rag_corpus"
# 本脚本产生的检索、基准、CoT 等输出
DEFAULT_RETRIEVE_OUT_DIR = PROJECT_ROOT / "outputs" / "retrieval"
DEFAULT_OUT_DIR = DEFAULT_RETRIEVE_OUT_DIR
DEFAULT_DASHSCOPE_CHAT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

SHOCK_KEYS = [
    "interest_rate_path",
    "inflation_concern",
    "growth_concern",
    "labor_market",
    "financial_stability",
]

RET_COLS = ["SPY_ret", "GLD_ret", "QQQ_ret", "UUP_ret"]
RET_LABELS = {"SPY_ret": "标普500(SPY)", "GLD_ret": "黄金(GLD)", "QQQ_ret": "纳指100(QQQ)", "UUP_ret": "美元指数代理(UUP)"}

COT_SYSTEM_PROMPT = """你是一个顶级的量化宏观对冲基金经理。你的任务是基于美联储(FOMC)最新会议的文本，结合我提供的「历史上最相似的 Top-k 案例及其真实市场反应」，预测本次会议后资产价格的走势。
你的推理必须严密、客观，承认历史的相似性，但也要敏锐察觉当下的微小差异。
必须严格按照指定的思维链（CoT）步骤输出。"""


def l2_normalize_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    return mat / norms


def evidence_blob(row: pd.Series) -> str:
    parts: list[str] = []
    for k in SHOCK_KEYS:
        ev = row.get(f"{k}_evidence")
        if ev is None or (isinstance(ev, float) and pd.isna(ev)):
            continue
        s = str(ev).strip()
        if s:
            parts.append(s)
    return " ".join(parts)


def macro_z_summary(row: pd.Series, z_cols: list[str], max_items: int = 8) -> str:
    items: list[str] = []
    for c in z_cols[:max_items]:
        if c not in row.index:
            continue
        v = row[c]
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(fv):
            continue
        short = c.replace("z_", "", 1)
        items.append(f"{short} z={fv:.2f}")
    return "；".join(items) if items else "(无 Z 分数列)"


def policy_shock_blurb(row: pd.Series) -> str:
    chunks: list[str] = []
    labels = {
        "interest_rate_path": "利率路径",
        "inflation_concern": "通胀担忧",
        "growth_concern": "增长担忧",
        "labor_market": "劳动力市场",
        "financial_stability": "金融稳定",
    }
    for k in SHOCK_KEYS:
        d = row.get(f"{k}_direction", "")
        st = row.get(f"{k}_strength", "")
        c = row.get(f"{k}_confidence", "")
        if pd.isna(d) and pd.isna(st):
            continue
        chunks.append(f"{labels.get(k, k)}: 方向={d}，强度={st}，置信度={c}")
    return "；".join(chunks) if chunks else "(无冲击抽取列)"


def truncate(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _default_chat_bearer() -> str:
    return (
        (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
        or (os.environ.get("OPENAI_API_KEY") or "").strip()
    )


def call_chat_openai_compatible(
    api_url: str,
    bearer: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer}",
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_err: Optional[str] = None
    for attempt in range(1, 6):
        try:
            resp = requests.post(api_url, headers=headers, json=data, timeout=(30, 600))
        except requests.RequestException as e:
            last_err = str(e)
            print(f"请求异常(第{attempt}次): {e}")
            time.sleep(2)
            continue
        if resp.status_code == 200:
            try:
                return (resp.json()["choices"][0]["message"]["content"] or "").strip()
            except (KeyError, IndexError, TypeError, ValueError) as e:
                last_err = f"bad response: {e}"
                time.sleep(2)
                continue
        last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
        print(f"HTTP {resp.status_code} (第{attempt}次): {resp.text[:500]}")
        if 400 <= resp.status_code < 500 and resp.status_code != 429:
            break
        time.sleep(2)
    raise RuntimeError(f"Chat 调用失败: {last_err}")


def shock_combo_scores(
    qi: int,
    hard_idx: np.ndarray,
    shock_n: np.ndarray,
    z_macro: np.ndarray,
    tau: float,
    alpha: float,
    beta: float,
    gamma: float,
) -> np.ndarray:
    """对每个候选 j∈hard_idx 计算组合分（越大越相似）。"""
    vq = shock_n[qi]
    sub = shock_n[hard_idx]
    cos_s = (sub * vq.reshape(1, -1)).sum(axis=1)
    cos_pos = np.clip((cos_s + 1.0) / 2.0, 0.0, 1.0)
    dist = np.linalg.norm(sub - vq.reshape(1, -1), axis=1)
    d_hat = np.clip(dist / 2.0, 0.0, 1.0)
    zq = z_macro[qi : qi + 1]
    zm = z_macro[hard_idx]
    pen = np.mean(np.abs(zm - zq), axis=1)
    pen_hat = np.clip(pen / (2.0 * max(tau, 0.25)), 0.0, 1.0)
    return alpha * cos_pos + beta * (1.0 - d_hat) - gamma * pen_hat


def run_retrieval_for_embedding(
    meta_ord: pd.DataFrame,
    event_ids: list[str],
    emb_n: np.ndarray,
    shock_n: np.ndarray,
    ev_sparse: Any,
    z_macro_cols: list[str],
    args: argparse.Namespace,
    statement_embedding_backend: str,
) -> pd.DataFrame:
    rows_out: list[dict[str, object]] = []

    for qi, qid in enumerate(event_ids):
        z_q = meta_ord.loc[qi, z_macro_cols].to_numpy(dtype=np.float64)

        tau = float(args.z_threshold)
        hard_idx: np.ndarray
        while True:
            zm = meta_ord[z_macro_cols].to_numpy(dtype=np.float64)
            diff = np.abs(zm - z_q.reshape(1, -1))
            mask = np.all(diff <= tau, axis=1)
            mask[qi] = False
            if args.meeting_type:
                mt = meta_ord["meeting_type"].astype(str)
                mask &= mt == str(args.meeting_type)
            hard_idx = np.where(mask)[0]
            if hard_idx.size >= args.min_hard_pool or tau >= args.z_threshold_max:
                break
            tau = min(tau + 0.35, args.z_threshold_max)

        if hard_idx.size == 0:
            mask = np.ones(len(event_ids), dtype=bool)
            mask[qi] = False
            if args.meeting_type:
                mt = meta_ord["meeting_type"].astype(str)
                mask &= mt == str(args.meeting_type)
            hard_idx = np.where(mask)[0]
        if hard_idx.size == 0:
            continue

        s_q = shock_n[qi : qi + 1]
        sub_shock = shock_n[hard_idx]
        shock_cos = cosine_similarity(s_q, sub_shock).ravel()
        order = np.argsort(-shock_cos)
        top_sh = order[: min(args.pool_shock, order.size)]
        idx_sh = hard_idx[top_sh]

        if idx_sh.size == 0:
            continue

        sub_ev = ev_sparse[idx_sh]
        q_ev = ev_sparse[qi : qi + 1]
        ev_cos = cosine_similarity(q_ev, sub_ev).ravel()
        order_ev = np.argsort(-ev_cos)
        top_ev = order_ev[: min(args.pool_evidence, order_ev.size)]
        idx_ev = idx_sh[top_ev]

        e_q = emb_n[qi : qi + 1]
        sub_emb = emb_n[idx_ev]
        emb_cos = cosine_similarity(e_q, sub_emb).ravel()
        order_f = np.argsort(-emb_cos)
        top_f = order_f[: min(args.top_k, order_f.size)]

        for rank, j in enumerate(top_f, start=1):
            ni = int(idx_ev[j])
            nid = event_ids[ni]
            shock_c = float(np.dot(shock_n[qi], shock_n[ni]))
            ev_c = float(cosine_similarity(ev_sparse[qi : qi + 1], ev_sparse[ni : ni + 1]).ravel()[0])
            emb_c = float(np.dot(emb_n[qi], emb_n[ni]))
            rows_out.append(
                {
                    "query_event_id": qid,
                    "statement_embedding_backend": statement_embedding_backend,
                    "neighbor_rank": rank,
                    "neighbor_event_id": nid,
                    "hard_filter_z_threshold_used": tau,
                    "hard_filter_pool_size": int(hard_idx.size),
                    "shock_cosine": shock_c,
                    "evidence_cosine": ev_c,
                    "embedding_cosine": emb_c,
                    "neighbor_date": meta_ord.loc[ni, "date"] if "date" in meta_ord.columns else "",
                    "neighbor_SPY_ret": meta_ord.loc[ni, "SPY_ret"] if "SPY_ret" in meta_ord.columns else np.nan,
                    "neighbor_GLD_ret": meta_ord.loc[ni, "GLD_ret"] if "GLD_ret" in meta_ord.columns else np.nan,
                    "neighbor_QQQ_ret": meta_ord.loc[ni, "QQQ_ret"] if "QQQ_ret" in meta_ord.columns else np.nan,
                    "neighbor_UUP_ret": meta_ord.loc[ni, "UUP_ret"] if "UUP_ret" in meta_ord.columns else np.nan,
                }
            )

    return pd.DataFrame(rows_out)


def run_four_stage_pipeline_for_query(
    qi: int,
    qid: str,
    event_ids: list[str],
    meta_ord: pd.DataFrame,
    shock_n: np.ndarray,
    z_macro: np.ndarray,
    z_macro_cols: list[str],
    ev_sparse: Any,
    emb_semantic_n: np.ndarray,
    semantic_backend: str,
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], float]:
    """
    返回 (topk 行字典列表, 最终使用的 tau)。
    """
    z_q = z_macro[qi]

    tau = float(args.z_threshold)
    while True:
        diff = np.abs(z_macro - z_q.reshape(1, -1))
        mask = np.all(diff <= tau, axis=1)
        mask[qi] = False
        if args.meeting_type:
            mt = meta_ord["meeting_type"].astype(str).to_numpy()
            mask &= mt == str(args.meeting_type)
        hard_idx = np.where(mask)[0]
        if hard_idx.size >= args.min_hard_pool or tau >= args.z_threshold_max:
            break
        tau = min(tau + 0.35, args.z_threshold_max)

    if hard_idx.size == 0:
        mask = np.ones(len(event_ids), dtype=bool)
        mask[qi] = False
        if args.meeting_type:
            mt = meta_ord["meeting_type"].astype(str).to_numpy()
            mask &= mt == str(args.meeting_type)
        hard_idx = np.where(mask)[0]
    if hard_idx.size == 0:
        return [], tau

    combo = shock_combo_scores(
        qi,
        hard_idx,
        shock_n,
        z_macro,
        tau,
        float(args.alpha),
        float(args.beta),
        float(args.gamma),
    )
    order = np.argsort(-combo)
    top_sh = order[: min(args.pool_shock, order.size)]
    idx_sh = hard_idx[top_sh]
    combo_sh = combo[top_sh]
    shock_cos_sh = (shock_n[idx_sh] * shock_n[qi]).sum(axis=1)
    dist_sh = np.linalg.norm(shock_n[idx_sh] - shock_n[qi], axis=1)
    zq_row = z_macro[qi : qi + 1]
    zm_sub = z_macro[idx_sh]
    pen_sh = np.mean(np.abs(zm_sub - zq_row), axis=1)

    sub_ev = ev_sparse[idx_sh]
    q_ev = ev_sparse[qi : qi + 1]
    ev_cos = cosine_similarity(q_ev, sub_ev).ravel()
    order_ev = np.argsort(-ev_cos)
    top_ev = order_ev[: min(args.pool_evidence, order_ev.size)]
    idx_ev = idx_sh[top_ev]
    combo_ev = combo_sh[top_ev]
    shock_cos_ev = shock_cos_sh[top_ev]
    dist_ev = dist_sh[top_ev]
    pen_ev = pen_sh[top_ev]
    ev_c = ev_cos[top_ev]

    sub_emb = emb_semantic_n[idx_ev]
    e_q = emb_semantic_n[qi : qi + 1]
    emb_cos = cosine_similarity(e_q, sub_emb).ravel()
    order_f = np.argsort(-emb_cos)
    top_f = order_f[: min(args.top_k, order_f.size)]

    rows: list[dict[str, Any]] = []
    for rank, j in enumerate(top_f, start=1):
        ni = int(idx_ev[j])
        nid = event_ids[ni]
        emb_c = float(emb_cos[j])
        sim_base = max(float(args.baseline_sim_floor), emb_c + float(args.baseline_sim_epsilon))
        rows.append(
            {
                "query_event_id": qid,
                "query_index": qi,
                "semantic_embedding_backend": semantic_backend,
                "neighbor_rank": rank,
                "neighbor_event_id": nid,
                "hard_filter_z_threshold_used": tau,
                "hard_filter_pool_size": int(hard_idx.size),
                "shock_combo_score": float(combo_ev[j]),
                "shock_cosine": float(shock_cos_ev[j]),
                "shock_l2_distance": float(dist_ev[j]),
                "macro_mean_abs_z_diff": float(pen_ev[j]),
                "evidence_cosine": float(ev_c[j]),
                "embedding_cosine_semantic": emb_c,
                "similarity_for_baseline": sim_base,
                "neighbor_date": meta_ord.loc[ni, "date"] if "date" in meta_ord.columns else "",
                "neighbor_SPY_ret": float(meta_ord.loc[ni, "SPY_ret"]) if "SPY_ret" in meta_ord.columns else np.nan,
                "neighbor_GLD_ret": float(meta_ord.loc[ni, "GLD_ret"]) if "GLD_ret" in meta_ord.columns else np.nan,
                "neighbor_QQQ_ret": float(meta_ord.loc[ni, "QQQ_ret"]) if "QQQ_ret" in meta_ord.columns else np.nan,
                "neighbor_UUP_ret": float(meta_ord.loc[ni, "UUP_ret"]) if "UUP_ret" in meta_ord.columns else np.nan,
            }
        )
    return rows, tau


def aggregate_baseline(top_rows: list[dict[str, Any]]) -> dict[str, float]:
    den = sum(r["similarity_for_baseline"] for r in top_rows)
    out: dict[str, float] = {"denominator": den}
    if den <= 0 or not top_rows:
        for c in RET_COLS:
            out[f"baseline_{c}"] = float("nan")
        return out
    for c in RET_COLS:
        num = sum(r["similarity_for_baseline"] * r[f"neighbor_{c}"] for r in top_rows if np.isfinite(r[f"neighbor_{c}"]))
        out[f"baseline_{c}"] = float(num / den)
    return out


def build_cot_user_prompt(
    query_row: pd.Series,
    z_cols: list[str],
    statement_excerpt: str,
    top_rows: list[dict[str, Any]],
    shocks_lookup: pd.DataFrame,
    baseline: dict[str, float],
) -> str:
    date_s = str(query_row.get("date", ""))
    macro_s = macro_z_summary(query_row, z_cols)
    shock_s = policy_shock_blurb(query_row)
    excerpt = truncate(statement_excerpt, 2000)

    def pct(x: float) -> str:
        if not np.isfinite(x):
            return "N/A"
        return f"{x * 100:.2f}%"

    case_blocks: list[str] = []
    for r in top_rows:
        nid = r["neighbor_event_id"]
        ndate = str(r.get("neighbor_date", ""))
        sim = r.get("shock_combo_score", 0.0)
        emb = r.get("embedding_cosine_semantic", 0.0)
        ev = r.get("evidence_cosine", 0.0)
        try:
            ev_text = evidence_blob(shocks_lookup.loc[nid])
        except Exception:  # noqa: BLE001
            ev_text = ""
        ev_text = truncate(ev_text, 600)
        case_blocks.append(
            f"案例（{nid}，日期 {ndate}）：宏观与会议类型已通过硬过滤；"
            f"冲击组合分 {sim:.4f}，证据句余弦 {ev:.4f}，声明语义余弦 {emb:.4f}。\n"
            f"历史反应：SPY [{pct(r['neighbor_SPY_ret'])}]，黄金 [{pct(r['neighbor_GLD_ret'])}]，"
            f"QQQ [{pct(r['neighbor_QQQ_ret'])}]，UUP [{pct(r['neighbor_UUP_ret'])}]。\n"
            f"历史核心证据句：「{ev_text}」"
        )
    cases_join = "\n\n".join(f"案例 {i+1}：\n{b}" for i, b in enumerate(case_blocks))

    b_spy = baseline.get("baseline_SPY_ret", float("nan"))
    b_gld = baseline.get("baseline_GLD_ret", float("nan"))
    baseline_lines = (
        f"基于语义精排相似度加权的基准预期（锚点，供你在步骤 3–4 对照修正）：\n"
        f"- SPY：{pct(b_spy)}\n"
        f"- GLD：{pct(b_gld)}\n"
        f"- QQQ：{pct(baseline.get('baseline_QQQ_ret', float('nan')))}\n"
        f"- UUP：{pct(baseline.get('baseline_UUP_ret', float('nan')))}\n"
        f"（公式：Predicted_Return = Σ(similarity_i × actual_i) / Σ(similarity_i)，其中 similarity_i 为语义 embedding 余弦加 ε。）"
    )

    return f"""【当前会议信息】
日期：{date_s}
宏观背景（Z-score 摘要）：{macro_s}
政策冲击判定（抽取结果）：{shock_s}
原文核心片段（Statement 摘录）：{excerpt}

【历史高度相似案例 (Top-{len(top_rows)})】
{cases_join}

【量化基准预测】
{baseline_lines}

【输出要求】
请严格按照以下 4 个步骤进行思考和输出（请保留步骤标题）：

步骤 1：历史共性映射 (Mapping)
详细说明当前会议与 Top-k 历史案例在宏观周期和美联储政策姿态上的核心共性是什么？为什么市场在历史上会做出那样的反应逻辑？

步骤 2：文本语义级偏差分析 (Nuance Detection)
对比当前会议文本与历史案例的「证据句」与措辞细节：当前联储语气更急迫还是更从容？与历史案例的关键差异是什么？

步骤 3：市场预期差推演 (Expectation Gap)
结合前两步，说明当前市场的计价是否已充分；上述量化基准预测在本次环境中更可能被放大、复刻还是反转？请给出可检验的理由。

步骤 4：最终预测结论 (Final Verdict)
给出清晰结论（可用小标题）：
SPY (美股)：[方向及幅度预判]
GLD (黄金)：[方向及幅度预判]
QQQ：[方向及幅度预判]
UUP（美元代理）：[方向及幅度预判]
核心驱动因子归因：[一句话总结]
"""


def legacy_export_neighbors(args: argparse.Namespace, rag_corpus_dir: Path) -> None:
    meta_path = rag_corpus_dir / "fomc_rag_metadata.csv"
    json_path = rag_corpus_dir / "fomc_rag_metadata.json"
    emb_svd_path = rag_corpus_dir / "fomc_statement_embeddings_svd.npy"
    emb_api_path = rag_corpus_dir / "fomc_statement_embeddings_api.npy"
    legacy_emb = rag_corpus_dir / "fomc_statement_embeddings.npy"

    bundle = json.loads(json_path.read_text(encoding="utf-8"))
    event_ids = [str(x) for x in bundle["event_ids"]]
    z_macro_cols = list(bundle["z_macro_cols"])

    meta = pd.read_csv(meta_path, encoding="utf-8").set_index("event_id", drop=False)
    meta_ord = meta.reindex(event_ids).reset_index(drop=True)

    shock_mat = np.stack(
        [meta_ord[f"shock_vec_{i}"].to_numpy(dtype=np.float64) for i in range(5)],
        axis=1,
    )
    shock_n = l2_normalize_rows(shock_mat)

    shocks = pd.read_csv(args.shocks, encoding="utf-8").set_index("event_id", drop=False)
    ev_texts = [evidence_blob(shocks.loc[e]) if e in shocks.index else "" for e in event_ids]
    tfidf = TfidfVectorizer(max_features=30_000, ngram_range=(1, 2), min_df=1, max_df=0.95)
    ev_sparse = tfidf.fit_transform(ev_texts)

    if not emb_svd_path.is_file() and legacy_emb.is_file():
        emb_svd_path = legacy_emb

    modes = ["svd", "api"] if args.statement_embedding == "both" else [args.statement_embedding]
    for mode in modes:
        path = emb_svd_path if mode == "svd" else emb_api_path
        if not path.is_file():
            print(f"[legacy] 跳过 {mode}: 未找到 {path}")
            continue
        emb = np.load(path)
        if emb.shape[0] != len(event_ids):
            print(f"[legacy] 跳过 {mode}: 行数不匹配")
            continue
        if bundle.get("skip_api") and mode == "api":
            print("[legacy] 跳过 api: skip_api")
            continue
        if mode == "api" and emb.shape[1] < 8:
            print(f"[legacy] 跳过 api: 维度过小 {emb.shape}")
            continue
        emb_n = l2_normalize_rows(emb.astype(np.float64))
        out_df = run_retrieval_for_embedding(
            meta_ord, event_ids, emb_n, shock_n, ev_sparse, z_macro_cols, args, mode
        )
        if args.output is not None and len(modes) == 1:
            out_path = args.output
        elif mode == "svd":
            out_path = args.output_svd
        else:
            out_path = args.output_api
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"[legacy] 写入 {out_path}，行数 {len(out_df)} [{mode}]")
        if mode == "svd":
            legacy = args.output_svd.parent / "fomc_retrieval_neighbors.csv"
            out_df.to_csv(legacy, index=False, encoding="utf-8")
            print(f"[legacy] 写入 {legacy}")


def main() -> None:
    ap = argparse.ArgumentParser(description="FOMC 四阶段检索 + 基准聚合 + CoT 生成")
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_RAG_CORPUS_DIR,
        help="RAG 语料目录（fomc_rag_metadata.*、embeddings、fomc_rag_texts.csv），默认 data/rag_corpus/",
    )
    ap.add_argument(
        "--shocks",
        type=Path,
        default=DEFAULT_SHOCKS,
        help="政策冲击抽取表路径，默认 data/processed/fomc_policy_shocks.csv",
    )
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="本脚本输出目录（检索 CSV、CoT、LLM），默认 outputs/retrieval/")
    ap.add_argument("--z-threshold", type=float, default=1.5)
    ap.add_argument("--z-threshold-max", type=float, default=4.0)
    ap.add_argument("--min-hard-pool", type=int, default=8)
    ap.add_argument("--pool-shock", type=int, default=20, help="阶段2后保留 Top N")
    ap.add_argument("--pool-evidence", type=int, default=10, help="阶段3后保留 Top N")
    ap.add_argument("--top-k", type=int, default=3, help="阶段4最终 Top-k")
    ap.add_argument("--meeting-type", default="Statement")
    ap.add_argument("--alpha", type=float, default=0.4, help="冲击余弦项权重（已映射到[0,1]）")
    ap.add_argument("--beta", type=float, default=0.4, help="(1-距离̂) 项权重")
    ap.add_argument("--gamma", type=float, default=0.2, help="宏观 Z 偏离惩罚权重")
    ap.add_argument(
        "--baseline-sim-epsilon",
        type=float,
        default=1e-6,
        help="基准加权 similarity 中对语义余弦的平滑项",
    )
    ap.add_argument(
        "--baseline-sim-floor",
        type=float,
        default=0.0,
        help="基准加权 similarity 下限（截断语义余弦）",
    )
    ap.add_argument(
        "--legacy-export",
        action="store_true",
        help="额外写出旧版 fomc_retrieval_neighbors_{svd,api}.csv",
    )
    ap.add_argument(
        "--statement-embedding",
        choices=("svd", "api", "both"),
        default="both",
        help="仅用于 --legacy-export",
    )
    ap.add_argument("--output-svd", type=Path, default=DEFAULT_RETRIEVE_OUT_DIR / "fomc_retrieval_neighbors_svd.csv")
    ap.add_argument("--output-api", type=Path, default=DEFAULT_RETRIEVE_OUT_DIR / "fomc_retrieval_neighbors_api.csv")
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument(
        "--pipeline-topk-csv",
        type=Path,
        default=DEFAULT_RETRIEVE_OUT_DIR / "fomc_retrieval_pipeline_topk.csv",
        help="四阶段漏斗最终 Top-k 明细",
    )
    ap.add_argument(
        "--baseline-csv",
        type=Path,
        default=DEFAULT_RETRIEVE_OUT_DIR / "fomc_baseline_predictions.csv",
        help="每查询的相似度加权基准收益",
    )
    ap.add_argument(
        "--cot-prompts-jsonl",
        type=Path,
        default=DEFAULT_OUT_DIR / "fomc_cot_prompts.jsonl",
        help="每条查询一条 JSON：system + user",
    )
    ap.add_argument(
        "--query-event-id",
        type=str,
        default="",
        help="若指定，仅生成该 event 的 CoT prompt /（与 --generate-llm 联用）仅调用一次 LLM",
    )
    ap.add_argument(
        "--generate-llm",
        action="store_true",
        help="调用百炼 Chat 生成 CoT 全文（建议与 --query-event-id 同用，避免大量扣费）",
    )
    ap.add_argument(
        "--chat-api-url",
        type=str,
        default=os.environ.get("DASHSCOPE_CHAT_API_URL", "").strip()
        or (DEFAULT_DASHSCOPE_CHAT_BASE.rstrip("/") + "/chat/completions"),
    )
    ap.add_argument("--chat-model", type=str, default=os.environ.get("DASHSCOPE_CHAT_MODEL", "qwen-plus"))
    ap.add_argument("--chat-bearer", type=str, default=_default_chat_bearer())
    ap.add_argument("--chat-temperature", type=float, default=0.3)
    ap.add_argument("--chat-max-tokens", type=int, default=4096)
    ap.add_argument(
        "--llm-output-md",
        type=Path,
        default=DEFAULT_OUT_DIR / "case_explanations.md",
        help="--generate-llm 时追加写入（与杨绮譞.md 交付物 case_explanations.md 对齐）",
    )
    args = ap.parse_args()

    rag_corpus_dir: Path = args.data_dir
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_path = rag_corpus_dir / "fomc_rag_metadata.csv"
    json_path = rag_corpus_dir / "fomc_rag_metadata.json"
    texts_path = rag_corpus_dir / "fomc_rag_texts.csv"
    emb_api_path = rag_corpus_dir / "fomc_statement_embeddings_api.npy"
    emb_svd_path = rag_corpus_dir / "fomc_statement_embeddings_svd.npy"
    legacy_emb = rag_corpus_dir / "fomc_statement_embeddings.npy"

    for p in (meta_path, json_path):
        if not p.is_file():
            raise SystemExit(f"缺少 {p}，请先运行 build_rag_corpus.py")

    bundle = json.loads(json_path.read_text(encoding="utf-8"))
    event_ids = [str(x) for x in bundle["event_ids"]]
    z_macro_cols = list(bundle["z_macro_cols"])

    meta = pd.read_csv(meta_path, encoding="utf-8").set_index("event_id", drop=False)
    meta_ord = meta.reindex(event_ids).reset_index(drop=True)

    shock_mat = np.stack(
        [meta_ord[f"shock_vec_{i}"].to_numpy(dtype=np.float64) for i in range(5)],
        axis=1,
    )
    shock_n = l2_normalize_rows(shock_mat)
    z_macro = meta_ord[z_macro_cols].to_numpy(dtype=np.float64)

    shocks = pd.read_csv(args.shocks, encoding="utf-8").set_index("event_id", drop=False)
    ev_texts = [evidence_blob(shocks.loc[e]) if e in shocks.index else "" for e in event_ids]
    tfidf = TfidfVectorizer(max_features=30_000, ngram_range=(1, 2), min_df=1, max_df=0.95)
    ev_sparse = tfidf.fit_transform(ev_texts)

    if emb_api_path.is_file():
        emb_api = np.load(emb_api_path).astype(np.float64)
        use_api = emb_api.shape[0] == len(event_ids) and emb_api.shape[1] >= 8 and not bundle.get("skip_api")
    else:
        emb_api = None
        use_api = False

    if use_api:
        emb_semantic = l2_normalize_rows(emb_api)
        semantic_backend = "api"
    else:
        print("警告: 未使用或未找到有效 API 声明 embedding，阶段4 回退到 SVD。")
        pth = emb_svd_path if emb_svd_path.is_file() else legacy_emb
        if not pth.is_file():
            raise SystemExit("缺少 fomc_statement_embeddings_svd.npy，无法完成语义精排。")
        emb_semantic = l2_normalize_rows(np.load(pth).astype(np.float64))
        semantic_backend = "svd"

    all_topk_rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []

    for qi, qid in enumerate(event_ids):
        topk, tau = run_four_stage_pipeline_for_query(
            qi,
            qid,
            event_ids,
            meta_ord,
            shock_n,
            z_macro,
            z_macro_cols,
            ev_sparse,
            emb_semantic,
            semantic_backend,
            args,
        )
        for r in topk:
            all_topk_rows.append(r)
        if topk:
            bl = aggregate_baseline(topk)
            baseline_rows.append(
                {
                    "query_event_id": qid,
                    "semantic_embedding_backend": semantic_backend,
                    "hard_filter_z_threshold_used": tau,
                    "baseline_weight_denominator": bl["denominator"],
                    **{k: bl[k] for k in bl if k != "denominator"},
                }
            )

    topk_df = pd.DataFrame(all_topk_rows)
    args.pipeline_topk_csv.parent.mkdir(parents=True, exist_ok=True)
    topk_df.to_csv(args.pipeline_topk_csv, index=False, encoding="utf-8")
    print(f"写入 {args.pipeline_topk_csv}，行数 {len(topk_df)}")

    bdf = pd.DataFrame(baseline_rows)
    bdf.to_csv(args.baseline_csv, index=False, encoding="utf-8")
    print(f"写入 {args.baseline_csv}，行数 {len(bdf)}")

    texts_df = pd.read_csv(texts_path, encoding="utf-8").set_index("event_id", drop=False) if texts_path.is_file() else None

    cot_targets: list[int] = []
    if args.query_event_id:
        if args.query_event_id not in event_ids:
            raise SystemExit(f"--query-event-id 不在索引中: {args.query_event_id}")
        cot_targets = [event_ids.index(args.query_event_id)]
    elif args.generate_llm:
        raise SystemExit("--generate-llm 需同时指定 --query-event-id，避免对全样本逐条调用扣费。")

    prompts_path = args.cot_prompts_jsonl
    prompts_path.parent.mkdir(parents=True, exist_ok=True)
    if not cot_targets:
        with prompts_path.open("w", encoding="utf-8") as fp:
            for qi, qid in enumerate(event_ids):
                rows_q = [r for r in all_topk_rows if r["query_event_id"] == qid]
                if not rows_q:
                    continue
                qrow = meta_ord.loc[qi]
                st_ex = ""
                if texts_df is not None and qid in texts_df.index:
                    st_ex = str(texts_df.loc[qid, "statement_text"])
                bl = aggregate_baseline(rows_q)
                user_content = build_cot_user_prompt(qrow, z_macro_cols, st_ex, rows_q, shocks, bl)
                rec = {
                    "query_event_id": qid,
                    "system": COT_SYSTEM_PROMPT,
                    "user": user_content,
                    "semantic_embedding_backend": semantic_backend,
                }
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"写入 {prompts_path}（全样本 {len(event_ids)} 条查询的 prompt）")
    else:
        with prompts_path.open("w", encoding="utf-8") as fp:
            for qi in cot_targets:
                qid = event_ids[qi]
                rows_q = [r for r in all_topk_rows if r["query_event_id"] == qid]
                qrow = meta_ord.loc[qi]
                st_ex = ""
                if texts_df is not None and qid in texts_df.index:
                    st_ex = str(texts_df.loc[qid, "statement_text"])
                bl = aggregate_baseline(rows_q)
                user_content = build_cot_user_prompt(qrow, z_macro_cols, st_ex, rows_q, shocks, bl)
                rec = {
                    "query_event_id": qid,
                    "system": COT_SYSTEM_PROMPT,
                    "user": user_content,
                    "semantic_embedding_backend": semantic_backend,
                }
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"写入 {prompts_path}（指定查询 {args.query_event_id}）")

    if args.generate_llm:
        bearer = str(args.chat_bearer).strip()
        if not bearer:
            raise SystemExit("调用 LLM 需要 DASHSCOPE_API_KEY（或 --chat-bearer）")
        for qi in cot_targets:
            qid = event_ids[qi]
            rows_q = [r for r in all_topk_rows if r["query_event_id"] == qid]
            qrow = meta_ord.loc[qi]
            st_ex = ""
            if texts_df is not None and qid in texts_df.index:
                st_ex = str(texts_df.loc[qid, "statement_text"])
            bl = aggregate_baseline(rows_q)
            user_content = build_cot_user_prompt(qrow, z_macro_cols, st_ex, rows_q, shocks, bl)
            text = call_chat_openai_compatible(
                args.chat_api_url,
                bearer,
                args.chat_model,
                COT_SYSTEM_PROMPT,
                user_content,
                args.chat_temperature,
                args.chat_max_tokens,
            )
            args.llm_output_md.parent.mkdir(parents=True, exist_ok=True)
            with args.llm_output_md.open("a", encoding="utf-8") as md:
                md.write(f"\n\n---\n\n## {qid}\n\n{text}\n")
            print(f"已追加 LLM 输出到 {args.llm_output_md}")

    if args.legacy_export:
        legacy_export_neighbors(args, rag_corpus_dir)


if __name__ == "__main__":
    main()
