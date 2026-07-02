#!/usr/bin/env python3
"""
从 data/raw/data_for_text_diff.xlsx 与 data/processed/fomc_policy_shocks.csv
构建 RAG 事件表示:

- 五维政策冲击数值向量（方向 x 强度）及五类因子的文本指标（方向、强度、置信度、证据句），
  其中文本类指标通过「声明级」拼接文本统一做向量化（API 与 TF-IDF+SVD 两套）。
- 声明原文 statement_text、previous_statement_text 落盘保存。
- 文本向量化两种都做，分开保存：
  - API：默认阿里云百炼 OpenAI 兼容模式 POST .../v1/embeddings（模型 text-embedding-v4），密钥读 DASHSCOPE_API_KEY；请求风格与 test.py 一致（Bearer、timeout、重试）。
  - 传统方法：TF-IDF + TruncatedSVD，行 L2 归一化。
- 宏观状态向量、市场预状态向量：数值列 Z-score。

默认输出目录为 data/rag_corpus/，实际路径见脚本末尾打印。
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import requests
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCEL = PROJECT_ROOT / "data" / "raw" / "data_for_text_diff.xlsx"
DEFAULT_SHOCKS = PROJECT_ROOT / "data" / "processed" / "fomc_policy_shocks.csv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "rag_corpus"

# 北京地域；新加坡地域请设环境变量 DASHSCOPE_API_BASE
DEFAULT_DASHSCOPE_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-v4"


def _default_embedding_bearer() -> str:
    return (
        (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
        or (os.environ.get("SJTU_API_KEY") or "").strip()
        or (os.environ.get("CHAT_API_KEY") or "").strip()
        or (os.environ.get("OPENAI_API_KEY") or "").strip()
    )

SHOCK_KEYS = [
    "interest_rate_path",
    "inflation_concern",
    "growth_concern",
    "labor_market",
    "financial_stability",
]

MACRO_LEVEL_COLS = [
    "DX-Y.NYB",
    "^VIX",
    "DGS2",
    "DGS10",
    "CPIAUCSL",
    "UNRATE",
    "PAYEMS",
    "T10Y2Y",
    "BAA10Y",
]

MARKET_LEVEL_COLS = [
    "SPY_close",
    "GLD_close",
    "QQQ_close",
    "UUP_close",
    "SPY_volume",
    "GLD_volume",
    "QQQ_volume",
    "UUP_volume",
]

RETURN_COLS = ["SPY_ret", "GLD_ret", "QQQ_ret", "UUP_ret"]


def direction_multiplier(direction: Any) -> float:
    if direction is None or (isinstance(direction, float) and pd.isna(direction)):
        return 0.0
    d = str(direction).lower().strip()
    if d == "hawkish":
        return 1.0
    if d == "dovish":
        return -1.0
    return 0.0


def shock_row_to_vector(row: pd.Series) -> np.ndarray:
    v = np.zeros(5, dtype=np.float64)
    for i, key in enumerate(SHOCK_KEYS):
        m = direction_multiplier(row.get(f"{key}_direction"))
        st = row.get(f"{key}_strength")
        try:
            st_f = float(st)
        except (TypeError, ValueError):
            st_f = 0.0
        if not np.isfinite(st_f):
            st_f = 0.0
        st_f = max(0.0, min(5.0, st_f))
        v[i] = m * st_f
    return v


def clean_statement(text: Any) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    s = str(text).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def shock_indicators_text_blob(row: pd.Series) -> str:
    """将五类因子、方向、强度、置信度和证据句拼接为文本，供 API 与 SVD 向量化。"""
    parts: list[str] = []
    for k in SHOCK_KEYS:
        d = row.get(f"{k}_direction")
        st = row.get(f"{k}_strength")
        c = row.get(f"{k}_confidence")
        ev = row.get(f"{k}_evidence")
        d_s = "" if d is None or (isinstance(d, float) and pd.isna(d)) else str(d).strip()
        st_s = "" if st is None or (isinstance(st, float) and pd.isna(st)) else str(st).strip()
        c_s = "" if c is None or (isinstance(c, float) and pd.isna(c)) else str(c).strip()
        ev_s = clean_statement(ev)
        parts.append(
            f"[{k}] direction={d_s} strength={st_s} confidence={c_s} evidence={ev_s}"
        )
    return "\n".join(parts)


def post_embeddings_test_py_style(
    texts: list[str],
    embeddings_url: str,
    bearer_token: str,
    model: str,
    batch_size: int,
) -> np.ndarray:
    """
    与 test.py 相同风格: Bearer、POST json、timeout (30,600)、最多 5 次重试、
    4xx(非429) 停止重试。
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token}",
    }
    all_vecs: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        # DashScope 兼容接口与 OpenAI 一致：model + input（字符串或字符串列表）。
        data: dict[str, Any] = {"model": model, "input": batch}
        last_err: Optional[str] = None
        batch_ok = False
        for attempt in range(1, 6):
            try:
                resp = requests.post(
                    embeddings_url,
                    headers=headers,
                    json=data,
                    timeout=(30, 600),
                )
            except requests.RequestException as e:
                last_err = str(e)
                print(f"请求异常(第{attempt}次): {e}")
                time.sleep(2)
                continue

            if resp.status_code == 200:
                try:
                    payload = resp.json()
                except ValueError as e:
                    last_err = f"invalid json: {e}"
                    time.sleep(2)
                    continue
                items = payload.get("data") or []
                indexed = sorted(items, key=lambda x: int(x.get("index", 0)))
                for item in indexed:
                    emb = item.get("embedding")
                    if not isinstance(emb, list):
                        raise RuntimeError("响应中缺少 embedding 列表")
                    all_vecs.append([float(x) for x in emb])
                batch_ok = True
                break

            last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
            print(f"HTTP {resp.status_code} (第{attempt}次): {resp.text[:500]}")
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                break
            time.sleep(2)
        if not batch_ok:
            raise RuntimeError(f"embedding 批次失败: {last_err}")

    return np.asarray(all_vecs, dtype=np.float64)


def fit_svd_embeddings(
    texts: list[str],
    n_components: int,
    random_state: int,
    min_df: int = 2,
) -> tuple[np.ndarray, Pipeline]:
    n_comp = min(n_components, max(2, len(texts) - 1))
    pipe = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    max_features=50_000,
                    ngram_range=(1, 2),
                    min_df=max(1, int(min_df)),
                    max_df=0.95,
                    sublinear_tf=True,
                ),
            ),
            ("svd", TruncatedSVD(n_components=n_comp, random_state=random_state)),
        ]
    )
    mat = pipe.fit_transform(texts)
    dense = mat.toarray() if hasattr(mat, "toarray") else np.asarray(mat, dtype=np.float64)
    norms = np.linalg.norm(dense, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    out = dense / norms
    return out.astype(np.float64), pipe


def main() -> None:
    p = argparse.ArgumentParser(description="构建 FOMC RAG: 双路文本向量 + 冲击/宏观/市场绑定")
    p.add_argument("--excel", type=Path, default=DEFAULT_EXCEL)
    p.add_argument("--shocks", type=Path, default=DEFAULT_SHOCKS)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument(
        "--api-base",
        default=os.environ.get("DASHSCOPE_API_BASE", DEFAULT_DASHSCOPE_API_BASE),
        help="OpenAI 兼容 Base URL(无末尾斜杠也可)。百炼北京默认 compatible-mode/v1；新加坡见 DASHSCOPE 文档",
    )
    p.add_argument(
        "--embedding-model",
        default=os.environ.get("DASHSCOPE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        help="Embeddings 的 model 字段；纯文本推荐 text-embedding-v4(勿用 vision 多模态模型调文本 embeddings 接口)",
    )
    p.add_argument(
        "--embedding-batch-size",
        type=int,
        default=int(os.environ.get("DASHSCOPE_EMBEDDING_BATCH_SIZE", "10")),
        help="每批条数(长声明多时宜小, 避免超 token 限制)",
    )
    p.add_argument("--svd-dim-statement", type=int, default=256)
    p.add_argument("--svd-dim-shock-text", type=int, default=128)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument(
        "--bearer",
        default=_default_embedding_bearer(),
        help="Bearer(API Key)；默认依次读取 DASHSCOPE_API_KEY / SJTU_API_KEY / CHAT_API_KEY / OPENAI_API_KEY",
    )
    p.add_argument("--skip-api",action="store_true",help="仅调试 SVD 时跳过 API")
    args = p.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    api_base = str(args.api_base).rstrip("/")
    embeddings_url = f"{api_base}/embeddings"

    panel = pd.read_excel(args.excel, engine="openpyxl")
    shocks = pd.read_csv(args.shocks, encoding="utf-8")

    if "event_id" not in panel.columns or "event_id" not in shocks.columns:
        raise SystemExit("panel 或 shocks 缺少 event_id")

    shock_cols_keep = [
        c
        for c in shocks.columns
        if c == "event_id"
        or any(c.startswith(f"{k}_") for k in SHOCK_KEYS)
        or c in ("model", "extraction_status", "text_change_summary")
    ]
    shocks_slim = shocks[shock_cols_keep]

    merged = panel.merge(shocks_slim, on="event_id", how="left", suffixes=("", "_shock"))
    merged["statement_clean"] = merged["statement_text"].map(clean_statement)

    shock_mat = np.vstack([shock_row_to_vector(merged.iloc[i]) for i in range(len(merged))])

    z_macro_cols = [f"z_{c}" for c in MACRO_LEVEL_COLS]
    z_mkt_cols = [f"z_{c}" for c in MARKET_LEVEL_COLS]

    macro_raw = merged[MACRO_LEVEL_COLS].apply(pd.to_numeric, errors="coerce")
    mkt_raw = merged[MARKET_LEVEL_COLS].apply(pd.to_numeric, errors="coerce")

    macro_scaler = StandardScaler()
    z_macro = macro_scaler.fit_transform(macro_raw.to_numpy(dtype=np.float64))
    z_macro = np.nan_to_num(z_macro, nan=0.0, posinf=0.0, neginf=0.0)

    mkt_scaler = StandardScaler()
    z_mkt = mkt_scaler.fit_transform(mkt_raw.to_numpy(dtype=np.float64))
    z_mkt = np.nan_to_num(z_mkt, nan=0.0, posinf=0.0, neginf=0.0)

    for j, name in enumerate(z_macro_cols):
        merged[name] = z_macro[:, j]
    for j, name in enumerate(z_mkt_cols):
        merged[name] = z_mkt[:, j]

    texts_statement = merged["statement_clean"].tolist()
    texts_shock_blob = [shock_indicators_text_blob(merged.iloc[i]) for i in range(len(merged))]

    # --- SVD：声明文本与冲击指标文本（两套独立流水线）---
    emb_stmt_svd, pipe_stmt_svd = fit_svd_embeddings(
        texts_statement, n_components=args.svd_dim_statement, random_state=args.random_state
    )
    emb_shock_svd, pipe_shock_svd = fit_svd_embeddings(
        texts_shock_blob,
        n_components=args.svd_dim_shock_text,
        random_state=args.random_state + 1,
        min_df=1,
    )

    # --- API：与 test.py 相同的调用方式 ---
    if args.skip_api:
        emb_stmt_api = np.zeros((len(texts_statement), 1), dtype=np.float64)
        emb_shock_api = np.zeros((len(texts_shock_blob), 1), dtype=np.float64)
        api_stmt_dim = 0
        api_shock_dim = 0
    else:
        bearer = str(args.bearer).strip()
        if not bearer:
            raise SystemExit(
                "调用百炼 Embeddings 需要 API Key: 请 export DASHSCOPE_API_KEY='sk-...' 或使用 --bearer。\n"
                "地域: 北京默认 --api-base 已为 compatible-mode/v1；新加坡请设置\n"
                "  DASHSCOPE_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1\n"
                "模型: 纯文本请用 text-embedding-v4(--embedding-model), 勿将 vision 嵌入模型用于本接口。"
            )
        emb_stmt_api = post_embeddings_test_py_style(
            texts_statement,
            embeddings_url=embeddings_url,
            bearer_token=bearer,
            model=str(args.embedding_model),
            batch_size=int(args.embedding_batch_size),
        )
        emb_shock_api = post_embeddings_test_py_style(
            texts_shock_blob,
            embeddings_url=embeddings_url,
            bearer_token=bearer,
            model=str(args.embedding_model),
            batch_size=int(args.embedding_batch_size),
        )
        api_stmt_dim = int(emb_stmt_api.shape[1])
        api_shock_dim = int(emb_shock_api.shape[1])

    event_ids = merged["event_id"].astype(str).tolist()

    meta_cols = (
        ["event_id", "date", "meeting_type"]
        + MACRO_LEVEL_COLS
        + MARKET_LEVEL_COLS
        + RETURN_COLS
        + [f"{k}_{s}" for k in SHOCK_KEYS for s in ("direction", "strength", "confidence")]
        + [f"shock_vec_{i}" for i in range(5)]
        + z_macro_cols
        + z_mkt_cols
        + ["extraction_status", "model", "text_change_summary"]
    )
    meta = merged.reindex(columns=[c for c in meta_cols if c in merged.columns]).copy()
    for i in range(5):
        meta[f"shock_vec_{i}"] = shock_mat[:, i]

    # 原始长文本单独保存，避免元数据表过大。
    texts_out = pd.DataFrame(
        {
            "event_id": merged["event_id"].astype(str),
            "statement_text": merged["statement_text"].astype(str),
            "previous_statement_text": merged["previous_statement_text"].astype(str),
        }
    )
    texts_csv = out_dir / "fomc_rag_texts.csv"
    texts_out.to_csv(texts_csv, index=False, encoding="utf-8")

    np.save(out_dir / "fomc_statement_embeddings_api.npy", emb_stmt_api)
    np.save(out_dir / "fomc_statement_embeddings_svd.npy", emb_stmt_svd)
    np.save(out_dir / "fomc_shock_indicators_embeddings_api.npy", emb_shock_api)
    np.save(out_dir / "fomc_shock_indicators_embeddings_svd.npy", emb_shock_svd)

    with (out_dir / "fomc_statement_embedding_svd.pkl").open("wb") as f:
        pickle.dump(pipe_stmt_svd, f, protocol=pickle.HIGHEST_PROTOCOL)
    with (out_dir / "fomc_shock_indicators_embedding_svd.pkl").open("wb") as f:
        pickle.dump(pipe_shock_svd, f, protocol=pickle.HIGHEST_PROTOCOL)

    bundle = {
        "event_ids": event_ids,
        "embedding_provider": "dashscope_compatible",
        "api_base": api_base,
        "embeddings_url": embeddings_url,
        "embedding_model": str(args.embedding_model),
        "statement_embedding_api_dim": api_stmt_dim if not args.skip_api else None,
        "statement_embedding_svd_dim": int(emb_stmt_svd.shape[1]),
        "shock_indicators_embedding_api_dim": api_shock_dim if not args.skip_api else None,
        "shock_indicators_embedding_svd_dim": int(emb_shock_svd.shape[1]),
        "macro_level_cols": MACRO_LEVEL_COLS,
        "market_level_cols": MARKET_LEVEL_COLS,
        "z_macro_cols": z_macro_cols,
        "z_market_cols": z_mkt_cols,
        "shock_keys": SHOCK_KEYS,
        "texts_csv": str(texts_csv.name),
        "artifacts": {
            "statement_embeddings_api": "fomc_statement_embeddings_api.npy",
            "statement_embeddings_svd": "fomc_statement_embeddings_svd.npy",
            "shock_indicators_embeddings_api": "fomc_shock_indicators_embeddings_api.npy",
            "shock_indicators_embeddings_svd": "fomc_shock_indicators_embeddings_svd.npy",
            "statement_svd_pipeline": "fomc_statement_embedding_svd.pkl",
            "shock_indicators_svd_pipeline": "fomc_shock_indicators_embedding_svd.pkl",
            "metadata_csv": "fomc_rag_metadata.csv",
            "texts_csv": "fomc_rag_texts.csv",
        },
        "skip_api": bool(args.skip_api),
    }
    json_path = out_dir / "fomc_rag_metadata.json"
    json_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = out_dir / "fomc_rag_metadata.csv"
    meta.to_csv(csv_path, index=False, encoding="utf-8")

    # 兼容旧文件名：声明 SVD 仍写一份 fomc_statement_embeddings.npy，供未改动的检索脚本使用。
    np.save(out_dir / "fomc_statement_embeddings.npy", emb_stmt_svd)

    print(f"行数: {len(merged)}")
    print(f"写入: {csv_path}")
    print(f"写入: {texts_csv}")
    print(f"写入: {json_path}")
    print(f"写入: {out_dir / 'fomc_statement_embeddings_api.npy'}  shape={emb_stmt_api.shape}")
    print(f"写入: {out_dir / 'fomc_statement_embeddings_svd.npy'}  shape={emb_stmt_svd.shape}")
    print(f"写入: {out_dir / 'fomc_shock_indicators_embeddings_api.npy'}  shape={emb_shock_api.shape}")
    print(f"写入: {out_dir / 'fomc_shock_indicators_embeddings_svd.npy'}  shape={emb_shock_svd.shape}")
    print(f"兼容: {out_dir / 'fomc_statement_embeddings.npy'} -> 与 svd 声明向量相同")


if __name__ == "__main__":
    main()
