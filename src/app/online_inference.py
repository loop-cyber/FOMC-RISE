#!/usr/bin/env python3
"""前端在线 RAG 检索与预测流水线。"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import build_frontend_data as frontend_data
except ModuleNotFoundError:  # pragma: no cover
    from src.app import build_frontend_data as frontend_data

from src.modeling import modeling

TUNED_PARAMS_FILE = (
    PROJECT_ROOT
    / "outputs"
    / "modeling"
    / "tuning"
    / "baseline_tuning_20260525_221743"
    / "baseline_best_params.csv"
)
QUERY_EVENT_ID = "ONLINE_QUERY"
MACRO_COLS = list(modeling.MACRO_MARKET_FEATURES)
TOP_K_DEFAULT = 3


def compact_text(value, limit=1200) -> str:
    if pd.isna(value):
        return ""
    text = " ".join(str(value).split())
    return text[:limit] + ("..." if len(text) > limit else "")


def load_static_context() -> dict:
    preds = pd.read_csv(frontend_data.PREDICTIONS_FILE)
    eval_df = pd.read_csv(frontend_data.EVALUATION_FILE)
    segment_df = pd.read_csv(frontend_data.SEGMENT_EVALUATION_FILE)
    panel = pd.read_excel(frontend_data.PANEL_FILE)
    shocks = pd.read_csv(frontend_data.SHOCK_FILE)
    retrieval = pd.read_csv(frontend_data.RETRIEVAL_FILE)
    config = json.loads(frontend_data.CONFIG_FILE.read_text(encoding="utf-8"))
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
    shocks["meeting_date"] = pd.to_datetime(shocks["meeting_date"], errors="coerce")
    return {
        "preds": preds,
        "eval_df": eval_df,
        "segment_df": segment_df,
        "panel": panel,
        "shocks": shocks,
        "retrieval": retrieval,
        "config": config,
        "default_event_id": frontend_data.latest_event_id(preds),
    }


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[\.\?!;])\s+", " ".join(str(text or "").split()))
    return [p.strip() for p in parts if p.strip()]


def _find_evidence(text: str, keywords: list[str]) -> str:
    lower_keywords = [k.lower() for k in keywords]
    for sent in _split_sentences(text):
        lower = sent.lower()
        if any(k in lower for k in lower_keywords):
            return sent
    return ""


def _keyword_score(text: str, positive_terms: list[str], negative_terms: list[str]) -> float:
    lower = str(text or "").lower()
    pos = sum(lower.count(term) for term in positive_terms)
    neg = sum(lower.count(term) for term in negative_terms)
    return float(pos - neg)


def _shock_direction_from_delta(delta: float) -> str:
    if delta >= 0.75:
        return "hawkish"
    if delta <= -0.75:
        return "dovish"
    return "neutral"


def _shock_strength_from_delta(delta: float) -> float:
    mag = abs(delta)
    if mag >= 2.0:
        return 3.0
    if mag >= 0.75:
        return 2.0
    return 1.0


def _shock_confidence_from_delta(delta: float) -> str:
    mag = abs(delta)
    if mag >= 2.0:
        return "high"
    if mag >= 0.75:
        return "medium"
    return "low"


def _heuristic_shock_specs() -> dict[str, dict[str, list[str]]]:
    return {
        "interest_rate_path": {
            "hawkish": [
                "raise the target range", "increase the target range", "higher for longer",
                "restrictive", "preferred to raise", "further firming",
            ],
            "dovish": [
                "lower the target range", "reduce the target range", "cut the target range",
                "preferred to lower", "policy easing", "adjust downward",
            ],
        },
        "inflation_concern": {
            "hawkish": [
                "inflation remains elevated", "inflation remains somewhat elevated",
                "highly attentive to inflation risks", "inflation pressures",
            ],
            "dovish": [
                "inflation has eased", "moving sustainably toward 2 percent",
                "inflation has declined", "inflation expectations remain well anchored",
            ],
        },
        "growth_concern": {
            "hawkish": [
                "economic activity has been expanding at a solid pace",
                "economic activity has continued to expand at a solid pace",
                "uncertainty has diminished",
            ],
            "dovish": [
                "uncertainty remains elevated", "outlook remains elevated", "growth moderated",
                "economic outlook is uncertain", "risks to the outlook", "slowed",
                "developments in the middle east", "weakened",
            ],
        },
        "labor_market": {
            "hawkish": [
                "labor market conditions remain solid", "unemployment rate remains low",
                "job gains have been solid", "labor market remains strong",
            ],
            "dovish": [
                "job gains have remained low", "job gains have slowed", "unemployment rate has risen",
                "labor market has softened", "little changed in recent months",
            ],
        },
        "financial_stability": {
            "hawkish": [
                "financial system is sound", "banking system is sound and resilient",
                "financial conditions have eased",
            ],
            "dovish": [
                "tighter financial conditions", "credit conditions", "banking stress",
                "financial developments are likely to weigh", "strains in the banking system",
            ],
        },
    }


def build_dynamic_shock_vector(
    current_text: str,
    previous_text: str,
    base_event_id: str,
    shocks: pd.DataFrame,
) -> list[dict]:
    base_row = shocks[shocks["event_id"] == base_event_id]
    current_clean = " ".join(str(current_text or "").split())
    previous_clean = " ".join(str(previous_text or "").split())

    if not base_row.empty:
        same_current = current_clean == " ".join(str(base_row.iloc[0].get("text_diff_full", "")).split())
        # shock 表无法还原完整原始声明文本；后续仅在文本未变时复用已存 shock。
        del same_current  # 保留显式分支，便于后续扩展

    specs = _heuristic_shock_specs()
    vector = []

    for key, label in frontend_data.SHOCK_LABELS.items():
        rules = specs[key]
        cur_score = _keyword_score(current_clean, rules["hawkish"], rules["dovish"])
        prev_score = _keyword_score(previous_clean, rules["hawkish"], rules["dovish"])
        delta = cur_score - prev_score
        if not previous_clean:
            delta = cur_score

        direction = _shock_direction_from_delta(delta)
        strength = _shock_strength_from_delta(delta)
        confidence = _shock_confidence_from_delta(delta)

        evidence = _find_evidence(current_clean, rules["hawkish"] + rules["dovish"])
        if not evidence and previous_clean:
            evidence = _find_evidence(previous_clean, rules["hawkish"] + rules["dovish"])
        if not evidence:
            evidence = "No material phrase-level signal found; heuristic extractor defaults to neutral/low-confidence."

        vector.append({
            "key": key,
            "label": label,
            "direction": direction,
            "strength": float(strength),
            "confidence": confidence,
            "evidence": evidence,
        })

    return vector


def build_shock_vector(
    current_text: str,
    previous_text: str,
    base_event_id: str,
    panel: pd.DataFrame,
    shocks: pd.DataFrame,
) -> list[dict]:
    panel_row = panel[panel["event_id"] == base_event_id]
    if not panel_row.empty:
        stored_current = " ".join(str(panel_row.iloc[0].get("statement_text", "")).split())
        stored_previous = " ".join(str(panel_row.iloc[0].get("previous_statement_text", "")).split())
        if (
            " ".join(str(current_text or "").split()) == stored_current
            and " ".join(str(previous_text or "").split()) == stored_previous
        ):
            return frontend_data.build_shock_vector(shocks, base_event_id)
    return build_dynamic_shock_vector(current_text, previous_text, base_event_id, shocks)


def _shock_vector_to_numeric(shock_vector: list[dict]) -> np.ndarray:
    vals = []
    for item in shock_vector:
        vals.append(
            modeling.DIRECTION_MAP.get(str(item["direction"]), 0)
            * float(item["strength"])
            * modeling.CONF_MAP.get(str(item["confidence"]), 0.5)
        )
    return np.asarray(vals, dtype=float)


def _shock_vector_to_row(shock_vector: list[dict], base_event_id: str, base_date: pd.Timestamp, meeting_type: str) -> dict:
    row = {
        "event_id": QUERY_EVENT_ID,
        "meeting_date": str(base_date.date()) if pd.notna(base_date) else "",
        "document_type": meeting_type,
        "model": "heuristic_online",
        "extraction_status": "online_inference",
        "api_error": "",
        "parse_error": "",
        "text_diff_full": "",
        "text_diff_for_prompt": "",
        "text_diff_prompt_truncated": False,
        "keyword_cosine_alignment": "",
        "text_change_summary": f"Online heuristic shock extraction based on {base_event_id}.",
    }
    for item in shock_vector:
        key = item["key"]
        row[f"{key}_direction"] = item["direction"]
        row[f"{key}_strength"] = item["strength"]
        row[f"{key}_confidence"] = item["confidence"]
        row[f"{key}_evidence"] = item["evidence"]
    return row


def _evidence_text_from_vector(shock_vector: list[dict]) -> str:
    return " ".join(str(item.get("evidence", "")) for item in shock_vector if item.get("evidence"))


def _historical_evidence_text(shocks: pd.DataFrame) -> pd.Series:
    cols = [f"{base}_evidence" for base in modeling.SHOCK_BASES if f"{base}_evidence" in shocks.columns]
    return shocks[cols].fillna("").agg(" ".join, axis=1)


def retrieve_similar_cases(
    current_text: str,
    previous_text: str,
    shock_vector: list[dict],
    base_event_id: str,
    panel: pd.DataFrame,
    shocks: pd.DataFrame,
    market_state_override: dict[str, float] | None = None,
    top_k: int = TOP_K_DEFAULT,
) -> pd.DataFrame:
    panel_lookup = panel.set_index("event_id", drop=False)
    base_row = panel_lookup.loc[base_event_id]
    meeting_type = str(base_row.get("meeting_type", ""))
    base_date = pd.to_datetime(base_row.get("date"), errors="coerce")

    shock_lookup = shocks.set_index("event_id", drop=False)
    hist = panel.copy()
    hist = hist[hist["event_id"] != base_event_id].copy()
    if meeting_type and "meeting_type" in hist.columns:
        hist = hist[hist["meeting_type"] == meeting_type].copy()
    if pd.notna(base_date):
        hist = hist[pd.to_datetime(hist["date"], errors="coerce") < base_date].copy()
    hist = hist[hist["event_id"].isin(shock_lookup.index)].copy()
    hist = hist.dropna(subset=["statement_text"])
    hist = hist.sort_values("date").reset_index(drop=True)

    if hist.empty:
        return pd.DataFrame()

    current_statement = " ".join(str(current_text or "").split())
    current_evidence = _evidence_text_from_vector(shock_vector)
    current_shock_numeric = _shock_vector_to_numeric(shock_vector).reshape(1, -1)

    hist_statement_texts = hist["statement_text"].fillna("").astype(str).tolist()
    stmt_vec = TfidfVectorizer(max_features=4000, ngram_range=(1, 2))
    stmt_mat = stmt_vec.fit_transform([current_statement] + hist_statement_texts)
    stmt_cos = cosine_similarity(stmt_mat[0:1], stmt_mat[1:]).ravel()

    hist_evidence_texts = _historical_evidence_text(shock_lookup.loc[hist["event_id"]]).tolist()
    ev_vec = TfidfVectorizer(max_features=3000, ngram_range=(1, 2))
    ev_mat = ev_vec.fit_transform([current_evidence] + hist_evidence_texts)
    evidence_cos = cosine_similarity(ev_mat[0:1], ev_mat[1:]).ravel()

    hist_shock_numeric = []
    for event_id in hist["event_id"]:
        row = shock_lookup.loc[event_id]
        items = []
        for base in modeling.SHOCK_BASES:
            items.append(
                modeling.DIRECTION_MAP.get(str(row.get(f"{base}_direction", "")), 0)
                * float(pd.to_numeric(row.get(f"{base}_strength"), errors="coerce") or 0)
                * modeling.CONF_MAP.get(str(row.get(f"{base}_confidence", "")), 0.5)
            )
        hist_shock_numeric.append(items)
    hist_shock_numeric = np.asarray(hist_shock_numeric, dtype=float)
    shock_cos = cosine_similarity(current_shock_numeric, hist_shock_numeric).ravel()
    shock_l2 = np.sqrt(((hist_shock_numeric - current_shock_numeric) ** 2).sum(axis=1))

    macro_frame = panel[["event_id"] + [c for c in MACRO_COLS if c in panel.columns]].copy()
    macro_frame = macro_frame.dropna(subset=[c for c in MACRO_COLS if c in macro_frame.columns], how="all")
    macro_cols = [c for c in MACRO_COLS if c in macro_frame.columns]
    macro_hist = macro_frame.set_index("event_id").loc[hist["event_id"], macro_cols].astype(float)
    macro_query = macro_frame.set_index("event_id").loc[base_event_id, macro_cols].astype(float).copy()
    for col, value in (market_state_override or {}).items():
        if col in macro_query.index and value is not None and np.isfinite(float(value)):
            macro_query.loc[col] = float(value)
    macro_mean = macro_frame[macro_cols].astype(float).mean()
    macro_std = macro_frame[macro_cols].astype(float).std().replace(0, 1.0)
    macro_hist_z = (macro_hist - macro_mean) / macro_std
    macro_query_z = (macro_query - macro_mean) / macro_std
    macro_diff = (macro_hist_z.sub(macro_query_z, axis=1).abs()).mean(axis=1).to_numpy(float)
    macro_score = np.exp(-macro_diff)

    similarity = 0.45 * stmt_cos + 0.25 * shock_cos + 0.15 * evidence_cos + 0.15 * macro_score
    shock_combo = 0.65 * shock_cos + 0.35 * evidence_cos

    out = hist[["event_id", "date"] + [c for c in modeling.TARGETS if c in hist.columns]].copy()
    out.insert(0, "query_event_id", QUERY_EVENT_ID)
    out.insert(1, "query_index", 0)
    out.insert(2, "semantic_embedding_backend", "tfidf_online")
    out["neighbor_rank"] = (
        pd.Series(similarity, index=out.index)
        .rank(method="first", ascending=False)
        .astype(int)
    )
    out["hard_filter_z_threshold_used"] = 1.5
    out["hard_filter_pool_size"] = int(len(hist))
    out["shock_combo_score"] = shock_combo
    out["shock_cosine"] = shock_cos
    out["shock_l2_distance"] = shock_l2
    out["macro_mean_abs_z_diff"] = macro_diff
    out["evidence_cosine"] = evidence_cos
    out["embedding_cosine_semantic"] = stmt_cos
    out["similarity_for_baseline"] = similarity
    out["neighbor_event_id"] = out["event_id"]
    out["neighbor_date"] = out["date"]

    for target in modeling.TARGETS:
        if target in out.columns:
            asset = target.replace("_ret", "")
            out[f"neighbor_{asset}_ret"] = out[target]

    keep_cols = [
        "query_event_id",
        "query_index",
        "semantic_embedding_backend",
        "neighbor_rank",
        "neighbor_event_id",
        "hard_filter_z_threshold_used",
        "hard_filter_pool_size",
        "shock_combo_score",
        "shock_cosine",
        "shock_l2_distance",
        "macro_mean_abs_z_diff",
        "evidence_cosine",
        "embedding_cosine_semantic",
        "similarity_for_baseline",
        "neighbor_date",
    ] + [f"neighbor_{asset}_ret" for asset in modeling.ASSETS]

    out = out.sort_values("similarity_for_baseline", ascending=False).head(top_k).reset_index(drop=True)
    out["neighbor_rank"] = np.arange(1, len(out) + 1)
    return out[keep_cols]


def build_query_event(
    panel: pd.DataFrame,
    base_event_id: str,
    current_text: str,
    previous_text: str,
    market_state_override: dict[str, float] | None = None,
) -> dict:
    base_row = panel[panel["event_id"] == base_event_id].iloc[0]
    text = " ".join(str(current_text or "").split())
    prev = " ".join(str(previous_text or "").split())
    market_state = {
        col: frontend_data.clean_number(base_row.get(col), 3)
        for col in frontend_data.MARKET_STATE_COLUMNS
        if col in base_row.index
    }
    for col, value in (market_state_override or {}).items():
        if col in market_state and value is not None and np.isfinite(float(value)):
            market_state[col] = frontend_data.clean_number(float(value), 3)
    return {
        "event_id": base_event_id,
        "date": str(pd.to_datetime(base_row["date"]).date()),
        "meeting_type": str(base_row.get("meeting_type", "")),
        "statement_excerpt": compact_text(text, 780),
        "statement_text": compact_text(text, 4000),
        "previous_statement_text": compact_text(prev, 2200),
        "market_state": market_state,
    }


def build_similar_case_payload(
    retrieval_rows: pd.DataFrame,
    panel: pd.DataFrame,
    shocks: pd.DataFrame,
) -> list[dict]:
    if retrieval_rows.empty:
        return []

    panel_lookup = panel.set_index("event_id", drop=False)
    shock_lookup = shocks.set_index("event_id", drop=False)
    rows = []

    for _, row in retrieval_rows.sort_values("neighbor_rank").iterrows():
        event_id = str(row["neighbor_event_id"])
        panel_row = panel_lookup.loc[event_id]
        previous_text = panel_row.get("previous_statement_text", "")
        rows.append({
            "rank": int(row["neighbor_rank"]),
            "event_id": event_id,
            "date": str(pd.to_datetime(row["neighbor_date"]).date()),
            "similarity": frontend_data.clean_number(row.get("similarity_for_baseline"), 4),
            "shock_cosine": frontend_data.clean_number(row.get("shock_cosine"), 4),
            "evidence_cosine": frontend_data.clean_number(row.get("evidence_cosine"), 4),
            "semantic_similarity": frontend_data.clean_number(row.get("embedding_cosine_semantic"), 4),
            "macro_mean_abs_z_diff": frontend_data.clean_number(row.get("macro_mean_abs_z_diff"), 4),
            "statement_excerpt": compact_text(panel_row.get("statement_text"), 1300),
            "previous_statement_excerpt": compact_text(previous_text, 900),
            "shock_evidence": frontend_data.shock_evidence_map(shocks, event_id),
            "returns_pct": {
                "SPY": frontend_data.pct(row.get("neighbor_SPY_ret"), 2),
                "QQQ": frontend_data.pct(row.get("neighbor_QQQ_ret"), 2),
                "GLD": frontend_data.pct(row.get("neighbor_GLD_ret"), 2),
                "UUP": frontend_data.pct(row.get("neighbor_UUP_ret"), 2),
            },
        })

    return rows


def _load_tuned_params() -> dict[tuple[str, str], dict]:
    if not TUNED_PARAMS_FILE.exists():
        return {}
    params_df = pd.read_csv(TUNED_PARAMS_FILE)
    params_map: dict[tuple[str, str], dict] = {}
    for _, row in params_df.iterrows():
        if str(row.get("task")) != "regression":
            continue
        params_map[(str(row["target"]), str(row["model_family"]))] = json.loads(row["params"])
    return params_map


TUNED_PARAMS = _load_tuned_params()


def make_tuned_regressor(target: str, model_family: str, feature_set_name: str, seed: int):
    model = modeling.make_regressor(seed=seed, model_family=model_family, feature_set_name=feature_set_name)
    params = TUNED_PARAMS.get((target, model_family), {})
    if params:
        model.set_params(**params)
    return model


def _ensemble_predict_with_residuals(
    train_df: pd.DataFrame,
    query_df: pd.DataFrame,
    target: str,
    feature_cols: list[str],
    model_family: str,
    feature_set_name: str,
) -> dict:
    y_train = pd.to_numeric(train_df[target], errors="coerce")
    valid = y_train.notna()
    X_train = train_df.loc[valid, feature_cols].copy()
    y_train = y_train.loc[valid].copy()
    X_query = query_df[feature_cols].copy()

    seeds = [42] if model_family in ("ridge", "lasso", "elasticnet") else modeling.SEEDS
    query_preds = []
    train_preds = []

    for seed in seeds:
        reg = make_tuned_regressor(target, model_family, feature_set_name, seed)
        reg.fit(X_train, y_train)
        query_preds.append(float(reg.predict(X_query)[0]))
        train_preds.append(np.asarray(reg.predict(X_train), dtype=float))

    query_preds_arr = np.asarray(query_preds, dtype=float)
    pred_reg = float(np.mean(query_preds_arr))
    pred_std = float(np.std(query_preds_arr)) if len(query_preds_arr) > 1 else float(np.nanstd(y_train.tail(60)) * 0.20)
    train_pred_mean = np.mean(np.vstack(train_preds), axis=0)
    residuals = (y_train.to_numpy(float) - train_pred_mean).astype(float)
    residuals = residuals[np.isfinite(residuals)]
    tail_resid = residuals[-80:] if len(residuals) > 80 else residuals

    sigma = float(np.nanstd(tail_resid, ddof=1)) if len(tail_resid) >= 2 else pred_std
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = float(np.nanstd(y_train.tail(60), ddof=1)) if len(y_train) >= 2 else 0.0
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = max(pred_std, 1e-8)

    train_std = float(np.nanstd(y_train.tail(60)))
    pred = modeling.calibrated_regression_return(pred_reg, target=target, train_target_std=train_std)
    prob_up = modeling.normal_approx_prob_up(pred, sigma)
    confidence = float(1.0 / (1.0 + sigma / (abs(pred) + 1e-8)))

    abs_resid = np.abs(tail_resid)
    if len(abs_resid) >= 20:
        q = min(1.0, np.ceil((len(abs_resid) + 1) * 0.90) / len(abs_resid))
        try:
            half_width = float(np.quantile(abs_resid, q, method="higher"))
        except TypeError:
            half_width = float(np.quantile(abs_resid, q, interpolation="higher"))
    else:
        half_width = float(1.64 * sigma)

    return {
        "pred_reg": pred_reg,
        "pred": pred,
        "pred_std": pred_std,
        "predictive_sigma": sigma,
        "prob_up": prob_up,
        "confidence": confidence,
        "interval_low": float(pred - half_width),
        "interval_high": float(pred + half_width),
        "interval_half_width": half_width,
        "interval_width": float(2 * half_width),
    }


def predict_event(
    panel: pd.DataFrame,
    shocks: pd.DataFrame,
    retrieval_static: pd.DataFrame,
    query_event: dict,
    shock_vector: list[dict],
    retrieval_rows: pd.DataFrame,
    market_state_override: dict[str, float] | None = None,
    model_family: str = "hgbdt",
) -> pd.DataFrame:
    base_event_id = query_event["event_id"]
    base_row = panel[panel["event_id"] == base_event_id].iloc[0].copy()
    query_row = base_row.copy()
    query_row["event_id"] = QUERY_EVENT_ID
    query_row["statement_text"] = query_event["statement_text"]
    query_row["previous_statement_text"] = query_event["previous_statement_text"]
    for col, value in (market_state_override or {}).items():
        if col in query_row.index and value is not None and np.isfinite(float(value)):
            query_row[col] = float(value)
    for target in modeling.TARGETS + modeling.OPTIONAL_YIELD_TARGETS:
        if target in query_row.index:
            query_row[target] = np.nan

    panel_aug = pd.concat([panel.copy(), pd.DataFrame([query_row])], ignore_index=True)
    shocks_aug = pd.concat(
        [
            shocks.copy(),
            pd.DataFrame([
                _shock_vector_to_row(
                    shock_vector,
                    base_event_id=base_event_id,
                    base_date=pd.to_datetime(base_row["date"], errors="coerce"),
                    meeting_type=str(base_row.get("meeting_type", "")),
                )
            ]),
        ],
        ignore_index=True,
    )
    retrieval_aug = pd.concat([retrieval_static.copy(), retrieval_rows.copy()], ignore_index=True)
    cases = modeling.build_case_features(retrieval_aug)
    model_df = modeling.build_model_dataset(panel_aug, shocks_aug, cases)
    query_df = model_df[model_df["event_id"] == QUERY_EVENT_ID].copy()

    rows = []
    for target in modeling.TARGETS:
        if target not in model_df.columns:
            continue

        train_df = model_df[(model_df["event_id"] != QUERY_EVENT_ID) & model_df[target].notna()].copy()
        train_df = train_df.sort_values("date").reset_index(drop=True)
        if len(train_df) < 35 or query_df.empty:
            continue

        row = {
            "event_id": query_event["event_id"],
            "query_event_id": QUERY_EVENT_ID,
            "date": query_event["date"],
            "asset_target": target,
        }

        case_col = f"case_pred_{target}"
        case_std_col = f"case_std_{target}"
        pred_case = float(query_df[case_col].iloc[0]) if case_col in query_df.columns and pd.notna(query_df[case_col].iloc[0]) else np.nan
        row["pred_case_model"] = pred_case
        row["case_direction"] = np.nan if np.isnan(pred_case) else int(pred_case > 0)

        feature_sets = modeling.get_feature_sets(model_df, target)
        for name, cols in feature_sets:
            if not cols:
                continue
            out = _ensemble_predict_with_residuals(train_df, query_df, target, cols, model_family, name)
            row[f"pred_{name}_reg"] = out["pred_reg"]
            row[f"pred_{name}"] = out["pred"]
            row[f"prob_up_{name}"] = out["prob_up"]
            row[f"pred_std_{name}"] = out["pred_std"]
            row[f"predictive_sigma_{name}"] = out["predictive_sigma"]
            row[f"confidence_{name}"] = out["confidence"]
            row[f"{name}_direction"] = int(out["pred"] > 0)
            row[f"pred_interval_low_90_{name}"] = out["interval_low"]
            row[f"pred_interval_high_90_{name}"] = out["interval_high"]
            row[f"pred_interval_half_width_90_{name}"] = out["interval_half_width"]
            row[f"pred_interval_width_90_{name}"] = out["interval_width"]
            row[f"pred_interval_source_90_{name}"] = "online_train_residual"

        sim = float(query_df.get("case_avg_similarity", pd.Series([0.0])).iloc[0] or 0.0)
        row["case_avg_similarity"] = sim
        row["case_neighbor_count"] = float(query_df.get("case_neighbor_count", pd.Series([0.0])).iloc[0] or 0.0)

        supervised_pred = row.get("pred_fusion", np.nan)
        supervised_std = row.get("predictive_sigma_fusion", np.nan)
        case_std = float(query_df[case_std_col].iloc[0]) if case_std_col in query_df.columns and pd.notna(query_df[case_std_col].iloc[0]) else np.nan

        if not np.isnan(pred_case) and not np.isnan(supervised_pred):
            sim_component = np.clip((sim - 0.85) / 0.15, 0.0, 1.0)
            uncertainty_component = 1.0 / (1.0 + case_std / (abs(pred_case) + 1e-8)) if not np.isnan(case_std) else 0.5
            if "SPY" in target:
                max_case_weight = 0.25
            elif "GLD" in target:
                max_case_weight = 0.30
            elif "UUP" in target:
                max_case_weight = 0.35
            else:
                max_case_weight = 0.45
            case_weight = float(np.clip(0.08 + 0.25 * sim_component + 0.10 * uncertainty_component, 0.03, max_case_weight))
            pred_final = (1 - case_weight) * supervised_pred + case_weight * pred_case
        else:
            case_weight = 0.0
            pred_final = supervised_pred

        pred_final = pred_final * modeling.ASSET_SCALE.get(target, 1.10)
        total_sigma = float(np.nanmean([supervised_std, case_std]))
        if not np.isfinite(total_sigma) or total_sigma <= 0:
            total_sigma = float(supervised_std if np.isfinite(supervised_std) else 0.0)
        half_width = 1.64 * total_sigma if total_sigma > 0 else 0.0

        row["case_weight_final"] = case_weight
        row["pred_final"] = float(pred_final)
        row["final_direction"] = int(pred_final > 0)
        row["bayesian_std_final"] = total_sigma
        row["bayesian_confidence_final"] = float(1.0 / (1.0 + total_sigma / (abs(pred_final) + 1e-8)))
        row["pred_interval_low_90_fusion_case"] = float(pred_final - half_width)
        row["pred_interval_high_90_fusion_case"] = float(pred_final + half_width)
        row["pred_interval_half_width_90_fusion_case"] = float(half_width)
        row["pred_interval_width_90_fusion_case"] = float(2 * half_width)
        row["pred_interval_source_90_fusion_case"] = "online_final_sigma"

        rows.append(row)

    return pd.DataFrame(rows)


def build_prediction_payload(preds: pd.DataFrame) -> list[dict]:
    rows = []
    order = {"SPY_ret": 0, "QQQ_ret": 1, "GLD_ret": 2, "UUP_ret": 3}
    preds = preds.copy()
    preds["asset_order"] = preds["asset_target"].map(order).fillna(999)
    for _, row in preds.sort_values(["asset_order", "asset_target"]).iterrows():
        target = str(row["asset_target"])
        meta = frontend_data.TARGET_LABELS.get(target, {"asset": target, "label": target})
        pred = float(row["pred_fusion"])
        low = float(row["pred_interval_low_90_fusion"])
        high = float(row["pred_interval_high_90_fusion"])
        prob_up = float(row["prob_up_fusion"])
        confidence = float(row["confidence_fusion"])
        rows.append({
            "asset": meta["asset"],
            "target": target,
            "label": meta["label"],
            "predicted_return": frontend_data.clean_number(pred, 6),
            "predicted_return_pct": frontend_data.pct(pred, 2),
            "direction": "up" if pred > 0 else "down",
            "direction_label": "上涨" if pred > 0 else "下跌",
            "prob_up": frontend_data.clean_number(prob_up, 4),
            "prob_up_pct": frontend_data.pct(prob_up, 1),
            "confidence": frontend_data.clean_number(confidence, 4),
            "confidence_pct": frontend_data.pct(confidence, 1),
            "interval_90_low": frontend_data.clean_number(low, 6),
            "interval_90_high": frontend_data.clean_number(high, 6),
            "interval_90_low_pct": frontend_data.pct(low, 2),
            "interval_90_high_pct": frontend_data.pct(high, 2),
            "interval_width_pct": frontend_data.pct(high - low, 2),
            "case_avg_similarity": frontend_data.clean_number(row.get("case_avg_similarity"), 4),
            "case_neighbor_count": frontend_data.clean_number(row.get("case_neighbor_count"), 0),
        })
    return rows


def build_frontend_payload(
    user_question: str,
    current_text: str,
    previous_text: str,
    market_state_override: dict[str, float] | None = None,
    base_event_id: str | None = None,
    top_k_cases: int = TOP_K_DEFAULT,
    model_family: str = "hgbdt",
) -> dict:
    ctx = load_static_context()
    base_event_id = base_event_id or ctx["default_event_id"]
    base_panel_row = ctx["panel"][ctx["panel"]["event_id"] == base_event_id].iloc[0]
    if not str(current_text or "").strip():
        current_text = str(base_panel_row.get("statement_text", ""))
    if not str(previous_text or "").strip():
        previous_text = str(base_panel_row.get("previous_statement_text", ""))
    panel = ctx["panel"]
    shocks = ctx["shocks"]

    clean_market_state = {}
    for col, value in (market_state_override or {}).items():
        try:
            clean_market_state[col] = float(value)
        except (TypeError, ValueError):
            continue

    query_event = build_query_event(
        panel,
        base_event_id,
        current_text,
        previous_text,
        market_state_override=clean_market_state,
    )
    shock_vector = build_shock_vector(current_text, previous_text, base_event_id, panel, shocks)
    retrieval_rows = retrieve_similar_cases(
        current_text=current_text,
        previous_text=previous_text,
        shock_vector=shock_vector,
        base_event_id=base_event_id,
        panel=panel,
        shocks=shocks,
        market_state_override=clean_market_state,
        top_k=top_k_cases,
    )
    similar_cases = build_similar_case_payload(retrieval_rows, panel, shocks)
    preds = predict_event(
        panel=panel,
        shocks=shocks,
        retrieval_static=ctx["retrieval"],
        query_event=query_event,
        shock_vector=shock_vector,
        retrieval_rows=retrieval_rows,
        market_state_override=clean_market_state,
        model_family=model_family,
    )
    prediction_payload = build_prediction_payload(preds)
    evaluation = frontend_data.build_evaluation(ctx["eval_df"], ctx["segment_df"])
    rag_logic = frontend_data.build_rag_logic(similar_cases)

    return {
        "metadata": {
            "title": "FOMC 多资产预测用户报告工作台",
            "model_family": model_family,
            "feature_set": "fusion",
            "model_label": f"{model_family}/fusion",
            "parameter_source": "baseline_tuning_20260525_221743/baseline_best_params.csv",
            "experiment_name": ctx["config"]["experiment_name"],
            "experiment_created_at": ctx["config"]["created_at"],
            "generated_from": "online_inference",
        },
        "default_user_question": user_question,
        "current_fomc_event": query_event,
        "policy_shock_vector": shock_vector,
        "historical_similar_cases": similar_cases,
        "rag_retrieval_logic": rag_logic,
        "llm_logic_chain_report": {
            "status": "not_generated",
            "content": "",
            "source_file": str(frontend_data.LLM_LOGIC_CHAIN_FILE.relative_to(PROJECT_ROOT)),
            "message": "在线推理已完成，等待 LLM 逻辑链报告生成。",
        },
        "multi_asset_predictions": prediction_payload,
        "model_evaluation": evaluation,
        "risk_disclosures": [
            "本页面用于研究展示，不构成投资建议。",
            f"{model_family}/fusion 的单事件在线预测使用历史样本重新拟合同一模型族，不等同于静态实验表中的离线逐步回测。",
            "90% 区间由训练样本残差近似校准，极端市场状态下可能低估尾部风险。",
            "RAG case-memory 已包含 shock-aware 检索信息，不能解释为完全独立于 shock 的纯文本检索。",
            "若你修改了当前声明文本但未同步提供新的宏观变量，本次在线预测仍沿用当前展示事件的宏观市场状态。",
        ],
        "report_contract": frontend_data.build_report_contract(),
        "materials": {
            "research_report_md": str(frontend_data.REPORT_FILE.relative_to(PROJECT_ROOT)),
            "frontend_readme": "src/frontend/fomc_report_app/README.md",
        },
    }


def build_llm_payload(frontend_payload: dict) -> dict:
    llm_predictions = []
    for item in frontend_payload["multi_asset_predictions"]:
        llm_predictions.append({
            "asset": item["asset"],
            "target": item["target"],
            "label": item["label"],
            "predicted_return": item["predicted_return"],
            "predicted_return_pct": item["predicted_return_pct"],
            "direction": item["direction"],
            "direction_label": item["direction_label"],
            "interval_90_low": item.get("interval_90_low"),
            "interval_90_high": item.get("interval_90_high"),
            "interval_90_low_pct": item.get("interval_90_low_pct"),
            "interval_90_high_pct": item.get("interval_90_high_pct"),
            "case_avg_similarity": item.get("case_avg_similarity"),
            "case_neighbor_count": item.get("case_neighbor_count"),
        })

    return {
        "task": "生成完整 RAG 历史案例逻辑链分析报告",
        "analysis_date": str(date.today()),
        "user_question": frontend_payload["default_user_question"],
        "model_setting": {
            "model_family": frontend_payload["metadata"]["model_family"],
            "feature_set": "fusion",
            "experiment_name": frontend_payload["metadata"]["experiment_name"],
            "prediction_model_note": (
                "在线推理使用当前声明文本、shock 主效应、shock 交互项和 RAG case-memory 特征，"
                "以 hgbdt/fusion 回归模型生成多资产预测。"
            ),
        },
        "current_fomc_event": frontend_payload["current_fomc_event"],
        "policy_shock_vector": frontend_payload["policy_shock_vector"],
        "rag_retrieval_logic": frontend_payload["rag_retrieval_logic"],
        "historical_similar_cases": frontend_payload["historical_similar_cases"],
        "multi_asset_predictions": llm_predictions,
        "model_evaluation": frontend_payload["model_evaluation"],
        "required_report_structure": [
            "一、核心预测结果",
            "二、政策冲击与资产价格传导链",
            "三、Top 历史案例的文本相似点、差异点与资产反应",
            "四、当前预测的证据强弱与不确定性",
            "五、模型边界与风险提示",
            "附录：方法说明",
            "附录 A：hgbdt/fusion 如何把传导链转化为预测",
            "附录 B：RAG 检索历史事件的依据",
        ],
        "writing_constraints": [
            "只基于本 JSON 写作。",
            "报告开头必须明确写出分析日期，并直接使用 analysis_date 字段，不得写成“基于输入 JSON 数据生成”等占位表达。",
            "先输出预测结果表，再解释政策传导链和历史案例细节，方法性说明统一放到最后的附录。",
            "必须优先完整回答用户问题，不得在历史案例细节处截断。",
            "核心预测结果表必须展示方向、预测收益和90%区间。",
            "核心预测结果表格不得展示除“资产”“预测方向”“预测收益 (%)”“90% 预测区间 (%)”以外的任何列或额外说明。",
            "必须说明当前在线检索与在线预测的输入边界。",
            "必须引用相似度指标和历史资产收益。",
            "必须说明文本相似点与差异点。",
            "不得比较预测结果与真实事后资产表现，不得写任何事后验证或复盘式分析。",
            "必须说明风险边界，不得给投资建议。",
        ],
    }
