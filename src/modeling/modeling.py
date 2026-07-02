# -*- coding: utf-8 -*-
"""
FOMC 多资产收益预测建模脚本。

本脚本读取 FOMC 事件面板、政策冲击抽取结果和 RAG 历史案例检索结果，
构造宏观市场特征、政策冲击特征、冲击交互特征和 case-memory 特征，
并在滚动时间序列回测框架下训练多类监督学习模型，预测 SPY、QQQ、
GLD 和 UUP 等资产在 FOMC 事件后的短期收益方向与收益幅度。

脚本会输出建模数据集、逐事件预测结果、资产级评估指标、分阶段评估指标、
增量价值汇总表和可视化图表，用于比较 baseline、shock、RAG case-memory
和 fusion 特征组合对多资产预测性能的贡献。
"""

from pathlib import Path
from datetime import datetime
import argparse
import json
import os
import warnings

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------
# Windows 和 Jupyter 稳定性设置
# ---------------------------------------------------------------------
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import ElasticNet, Lasso, Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    accuracy_score,
    balanced_accuracy_score,
)

try:
    from xgboost import XGBRegressor
    HAS_XGB = True
except Exception:
    HAS_XGB = False


# ---------------------------------------------------------------------
# 0. 路径与配置
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS_DIR = PROJECT_ROOT / "outputs" / "modeling" / "experiments"

B_FILE = PROJECT_ROOT / "data" / "raw" / "data_for_text_diff.xlsx"
SHOCK_FILE = PROJECT_ROOT / "data" / "processed" / "fomc_policy_shocks.csv"
RETRIEVAL_FILE = PROJECT_ROOT / "outputs" / "retrieval" / "fomc_retrieval_pipeline_topk.csv"
BASELINE_BEST_PARAMS_FILE = (
    PROJECT_ROOT
    / "outputs"
    / "modeling"
    / "tuning"
    / "baseline_tuning_20260525_221743"
    / "baseline_best_params.csv"
)

ASSETS = ["SPY", "QQQ", "GLD", "UUP"]
TARGETS = [f"{a}_ret" for a in ASSETS]
OPTIONAL_YIELD_TARGETS = ["DGS2_change_1d", "DGS10_change_1d", "DGS2_ret", "DGS10_ret"]

MACRO_MARKET_FEATURES = [
    "DX-Y.NYB", "^VIX", "DGS2", "DGS10", "CPIAUCSL", "UNRATE", "PAYEMS",
    "T10Y2Y", "BAA10Y", "UUP_volume", "SPY_volume", "GLD_volume", "QQQ_volume"
]

DERIVED_MARKET_STATE_FEATURES = [
    "high_vix_regime",
    "curve_inversion",
]

SHOCK_BASES = [
    "interest_rate_path", "inflation_concern", "growth_concern",
    "labor_market", "financial_stability"
]

DIRECTION_MAP = {"hawkish": 1, "neutral": 0, "dovish": -1}
CONF_MAP = {"low": 0.33, "medium": 0.66, "high": 1.0}

SEEDS = [7, 21, 42, 63, 99]

FAST_TARGETS_ONLY = True

# 反均值回归缩放系数
ASSET_SCALE = {
    "SPY_ret": 1.15,
    "QQQ_ret": 1.25,
    "GLD_ret": 1.20,
    "UUP_ret": 1.10,
}

MODEL_FAMILIES = ("current", "ridge", "lasso", "elasticnet", "xgboost", "hgbdt")

TIME_SEGMENTS = [
    ("2008_2015", "2008-01-01", "2015-12-31"),
    ("2016_2019", "2016-01-01", "2019-12-31"),
    ("2020_2021", "2020-01-01", "2021-12-31"),
    ("2022_2026", "2022-01-01", "2026-12-31"),
]

PERMUTATION_REPEATS = 5
PERMUTATION_VALIDATION_FRACTION = 0.30

MODEL_PRED_COLS = {
    "baseline": "pred_baseline",
    "shock_main": "pred_shock_main",
    "shock_interactions": "pred_shock_interactions",
    "rag_memory": "pred_rag_memory",
    "shock_rag": "pred_shock_rag",
    "case_model": "pred_case_model",
    "fusion": "pred_fusion",
    "fusion_case": "pred_final",
}

def load_baseline_best_params() -> dict[tuple[str, str, str], dict]:
    if not BASELINE_BEST_PARAMS_FILE.exists():
        return {}

    params_df = pd.read_csv(BASELINE_BEST_PARAMS_FILE)
    params_map = {}

    for _, row in params_df.iterrows():
        key = (str(row["target"]), str(row["model_family"]), str(row["task"]))
        params = json.loads(row["params"]) if pd.notna(row.get("params")) else {}
        params_map[key] = params

    return params_map


BASELINE_BEST_PARAMS = load_baseline_best_params()


def get_tuned_params(target: str | None, model_family: str, task: str) -> dict:
    if target is None:
        return {}

    return BASELINE_BEST_PARAMS.get((target, model_family, task), {})


def apply_tuned_params(model: Pipeline, target: str | None, model_family: str, task: str) -> Pipeline:
    params = get_tuned_params(target, model_family, task)

    if params:
        model.set_params(**params)

    return model


# ---------------------------------------------------------------------
# 1. 数据读取
# ---------------------------------------------------------------------
def read_inputs():
    b = pd.read_excel(B_FILE, sheet_name="Sheet1")
    shocks = pd.read_csv(SHOCK_FILE)
    retrieval = pd.read_csv(RETRIEVAL_FILE)

    b["date"] = pd.to_datetime(b["date"], errors="coerce")
    shocks["meeting_date"] = pd.to_datetime(shocks["meeting_date"], errors="coerce")

    return b, shocks, retrieval


# ---------------------------------------------------------------------
# 2. 历史案例记忆特征
# ---------------------------------------------------------------------
def _weighted_std(values, weights):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)

    if len(values) == 0 or np.nansum(weights) <= 0:
        return np.nan

    avg = np.average(values, weights=weights)
    return float(np.sqrt(np.average((values - avg) ** 2, weights=weights)))


def build_case_features(retrieval: pd.DataFrame) -> pd.DataFrame:
    ret_cols = [
        c for c in retrieval.columns
        if c.startswith("neighbor_") and c.endswith("_ret")
    ]

    if not ret_cols:
        return pd.DataFrame({"event_id": retrieval["query_event_id"].unique()})

    df = retrieval.copy()

    if "similarity_for_baseline" in df.columns:
        sim = df["similarity_for_baseline"]
    elif "embedding_cosine_semantic" in df.columns:
        sim = df["embedding_cosine_semantic"]
    else:
        sim = 0

    df["_sim"] = pd.to_numeric(sim, errors="coerce").fillna(0)

    temperature = 5.0
    df["_w_raw"] = np.exp(
        temperature * (
            df["_sim"] - df.groupby("query_event_id")["_sim"].transform("max")
        )
    )
    df["_w"] = df["_w_raw"] / df.groupby("query_event_id")["_w_raw"].transform("sum")

    rows = []

    for event_id, g in df.groupby("query_event_id"):
        w = g["_w"].to_numpy(float)

        row = {
            "event_id": event_id,
            "case_neighbor_count": int(len(g)),
            "case_avg_similarity": float(np.average(g["_sim"], weights=w)),
            "case_max_similarity": float(np.nanmax(g["_sim"])),
            "case_similarity_std": _weighted_std(g["_sim"], w),
        }

        for col in ret_cols:
            asset = col.replace("neighbor_", "").replace("_ret", "")
            vals = pd.to_numeric(g[col], errors="coerce").fillna(0).to_numpy(float)

            case_mean = float(np.average(vals, weights=w))
            case_std = _weighted_std(vals, w)
            up_prob = float(np.average((vals > 0).astype(float), weights=w))

            row[f"case_pred_{asset}_ret"] = case_mean
            row[f"case_std_{asset}_ret"] = case_std
            row[f"case_up_prob_{asset}"] = up_prob
            row[f"case_abs_mean_{asset}_ret"] = float(np.average(np.abs(vals), weights=w))
            row[f"case_direction_agreement_{asset}"] = float(abs(up_prob - 0.5) * 2)

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# 3. 政策冲击特征工程与交互特征
# ---------------------------------------------------------------------
def build_shock_features(shocks: pd.DataFrame) -> pd.DataFrame:
    engineered = shocks[["event_id"]].copy()
    shock_cols = ["event_id"]

    for base in SHOCK_BASES:
        dir_col = f"{base}_direction"
        str_col = f"{base}_strength"
        conf_col = f"{base}_confidence"

        engineered[f"{base}_dir_num"] = shocks[dir_col].map(DIRECTION_MAP).fillna(0)
        engineered[f"{base}_strength_num"] = pd.to_numeric(
            shocks[str_col], errors="coerce"
        ).fillna(0)
        engineered[f"{base}_conf_num"] = shocks[conf_col].map(CONF_MAP).fillna(0.5)

        engineered[f"{base}_shock_score"] = (
            engineered[f"{base}_dir_num"]
            * engineered[f"{base}_strength_num"]
            * engineered[f"{base}_conf_num"]
        )

        engineered[f"{base}_hawkish_score"] = engineered[f"{base}_shock_score"].clip(lower=0)
        engineered[f"{base}_dovish_score"] = -engineered[f"{base}_shock_score"].clip(upper=0)

        shock_cols += [
            f"{base}_dir_num",
            f"{base}_strength_num",
            f"{base}_conf_num",
            f"{base}_shock_score",
            f"{base}_hawkish_score",
            f"{base}_dovish_score",
        ]

    return engineered[shock_cols]


def add_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    numeric_candidates = MACRO_MARKET_FEATURES + [
        c for c in df.columns if "shock_score" in c
    ]

    for c in numeric_candidates:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "^VIX" in df.columns:
        med_vix = df["^VIX"].median()
        df["high_vix_regime"] = (df["^VIX"] > med_vix).astype(int)
    else:
        df["high_vix_regime"] = 0

    if "T10Y2Y" in df.columns:
        df["curve_inversion"] = (df["T10Y2Y"] < 0).astype(int)
    else:
        df["curve_inversion"] = 0

    shock_score_cols = [c for c in df.columns if c.endswith("_shock_score")]

    for s in shock_score_cols:
        if "^VIX" in df.columns:
            df[f"{s}_x_vix"] = df[s] * df["^VIX"]

        if "T10Y2Y" in df.columns:
            df[f"{s}_x_curve"] = df[s] * df["T10Y2Y"]

        df[f"{s}_x_high_vix"] = df[s] * df["high_vix_regime"]
        df[f"{s}_x_inversion"] = df[s] * df["curve_inversion"]

        if "case_avg_similarity" in df.columns:
            df[f"{s}_x_case_similarity"] = df[s] * df["case_avg_similarity"].fillna(0)

        df[f"{s}_minus_rolling_mean"] = (
            df[s] - df[s].rolling(8, min_periods=4).mean().shift(1)
        )

    return df


def build_model_dataset(
    b: pd.DataFrame,
    shocks: pd.DataFrame,
    cases: pd.DataFrame
) -> pd.DataFrame:
    shock_features = build_shock_features(shocks)

    df = b.merge(shock_features, on="event_id", how="left")
    df = df.merge(cases, on="event_id", how="left")
    df = df.sort_values("date").reset_index(drop=True)

    df = add_interaction_features(df)

    for t in TARGETS + OPTIONAL_YIELD_TARGETS:
        if t in df.columns:
            df[t] = pd.to_numeric(df[t], errors="coerce")
            df[f"{t}_direction"] = (df[t] > 0).astype(int)
            df[f"{t}_vol20_event"] = df[t].rolling(20, min_periods=10).std().shift(1)
            df[f"{t}_scaled"] = df[t] / df[f"{t}_vol20_event"]

    return df


def get_available_targets(df: pd.DataFrame):
    targets = [t for t in TARGETS if t in df.columns]
    targets += [t for t in OPTIONAL_YIELD_TARGETS if t in df.columns]
    return targets


# ---------------------------------------------------------------------
# 4. 模型定义
# ---------------------------------------------------------------------
def make_regressor(seed=42, model_family="current", feature_set_name="fusion", target=None):
    if model_family == "current":
        model_family = "ridge" if feature_set_name == "baseline" else "xgboost"

    if model_family == "ridge":
        return apply_tuned_params(Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=1.0)),
        ]), target, model_family, "regression")

    if model_family == "lasso":
        return apply_tuned_params(Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", Lasso(alpha=0.001, max_iter=5000, random_state=seed)),
        ]), target, model_family, "regression")

    if model_family == "elasticnet":
        return apply_tuned_params(Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=5000, random_state=seed)),
        ]), target, model_family, "regression")

    if model_family == "xgboost":
        if not HAS_XGB:
            raise RuntimeError("model_family='xgboost' 需要安装 xgboost；可改用 --model-family hgbdt")
        model = XGBRegressor(
            n_estimators=40,
            max_depth=2,
            learning_rate=0.06,
            subsample=0.90,
            colsample_bytree=0.90,
            reg_alpha=0.5,
            reg_lambda=3.0,
            objective="reg:squarederror",
            tree_method="hist",
            random_state=seed,
            n_jobs=1,
            verbosity=0,
        )

        return apply_tuned_params(Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", model),
        ]), target, model_family, "regression")

    if model_family != "hgbdt":
        raise ValueError(f"Unknown model_family: {model_family}")

    return apply_tuned_params(Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingRegressor(
            max_iter=60,
            max_leaf_nodes=8,
            learning_rate=0.06,
            random_state=seed,
        )),
    ]), target, model_family, "regression")


def predict_regression_ensemble(
    X_train,
    y_train,
    X_test,
    feature_cols,
    model_family="current",
    feature_set_name="fusion",
    target=None,
):
    preds = []
    seeds = [42] if model_family in ("ridge", "lasso", "elasticnet") else SEEDS

    for seed in seeds:
        model = make_regressor(
            seed=seed,
            model_family=model_family,
            feature_set_name=feature_set_name,
            target=target,
        )
        model.fit(X_train[feature_cols], y_train)
        preds.append(float(model.predict(X_test[feature_cols])[0]))

    mean_pred = float(np.mean(preds))

    if len(preds) > 1:
        std_pred = float(np.std(preds))
    else:
        std_pred = float(np.nanstd(y_train.tail(60)) * 0.20) if len(y_train) > 5 else 0.0

    return mean_pred, std_pred


# ---------------------------------------------------------------------
# 5. 滚动回测
# ---------------------------------------------------------------------
def get_feature_sets(df: pd.DataFrame, target: str):
    baseline_features = [
        c
        for c in MACRO_MARKET_FEATURES + DERIVED_MARKET_STATE_FEATURES
        if c in df.columns
    ]

    shock_main_features = [
        c for c in df.columns
        if c.endswith("_dir_num")
        or c.endswith("_strength_num")
        or c.endswith("_conf_num")
        or c.endswith("_shock_score")
        or c.endswith("_hawkish_score")
        or c.endswith("_dovish_score")
    ]

    shock_interaction_features = [
        c for c in df.columns
        if "_x_vix" in c
        or "_x_curve" in c
        or "_x_high_vix" in c
        or "_x_inversion" in c
        or "_x_case_similarity" in c
        or c.endswith("_minus_rolling_mean")
    ]

    asset = target.replace("_ret", "")

    case_features = [
        c for c in df.columns
        if c in [
            "case_neighbor_count",
            "case_avg_similarity",
            "case_max_similarity",
            "case_similarity_std",
        ]
        or c.startswith(f"case_pred_{asset}")
        or c.startswith(f"case_std_{asset}")
        or c.startswith(f"case_up_prob_{asset}")
        or c.startswith(f"case_abs_mean_{asset}")
        or c.startswith(f"case_direction_agreement_{asset}")
    ]

    def uniq(cols):
        seen, out = set(), []

        for c in cols:
            if c not in seen and c in df.columns:
                seen.add(c)
                out.append(c)

        return out

    baseline = uniq(baseline_features)
    shock_main = uniq(baseline_features + shock_main_features)
    shock_interactions = uniq(
        baseline_features + shock_main_features + shock_interaction_features
    )
    rag_memory = uniq(baseline_features + case_features)
    shock_rag = uniq(baseline_features + shock_main_features + case_features)
    fusion = uniq(
        baseline_features
        + shock_main_features
        + shock_interaction_features
        + case_features
    )

    return [
        ("baseline", baseline),
        ("shock_main", shock_main),
        ("shock_interactions", shock_interactions),
        ("rag_memory", rag_memory),
        ("shock_rag", shock_rag),
        ("fusion", fusion),
    ]


def rolling_conformal_half_width(
    pred_rows,
    target,
    pred_col,
    y_train,
    confidence=0.90,
    min_residuals=20,
    window=80,
):
    residuals = []

    for prev in pred_rows:
        if prev.get("asset_target") != target:
            continue

        pred = prev.get(pred_col, np.nan)
        actual = prev.get("actual", np.nan)

        if pd.notna(pred) and pd.notna(actual):
            residuals.append(abs(float(actual) - float(pred)))

    residuals = np.asarray(residuals[-window:], dtype=float)
    residuals = residuals[np.isfinite(residuals)]

    if len(residuals) >= min_residuals:
        q = min(1.0, np.ceil((len(residuals) + 1) * confidence) / len(residuals))

        try:
            return float(np.quantile(residuals, q, method="higher")), "rolling_conformal"
        except TypeError:
            return float(np.quantile(residuals, q, interpolation="higher")), "rolling_conformal"

    recent = pd.to_numeric(y_train.tail(60), errors="coerce").dropna()

    if len(recent) < 5:
        recent = pd.to_numeric(y_train, errors="coerce").dropna()

    fallback = float(1.64 * np.nanstd(recent)) if len(recent) else np.nan

    if not np.isfinite(fallback) or fallback <= 0:
        fallback = float(np.nanstd(y_train))

    if not np.isfinite(fallback) or fallback <= 0:
        fallback = 0.0

    return fallback, "recent_volatility_fallback"


def add_model_intervals(row, pred_rows, target, y_train):
    for model_name, pred_col in MODEL_PRED_COLS.items():
        pred = row.get(pred_col, np.nan)

        if pd.isna(pred):
            continue

        half_width, source = rolling_conformal_half_width(
            pred_rows,
            target,
            pred_col,
            y_train,
        )

        low = float(pred - half_width)
        high = float(pred + half_width)

        row[f"pred_interval_low_90_{model_name}"] = low
        row[f"pred_interval_high_90_{model_name}"] = high
        row[f"pred_interval_half_width_90_{model_name}"] = float(half_width)
        row[f"pred_interval_width_90_{model_name}"] = float(high - low)
        row[f"pred_interval_source_90_{model_name}"] = source

        if model_name == "fusion_case":
            row["pred_interval_low_90"] = low
            row["pred_interval_high_90"] = high
            row["pred_interval_half_width_90"] = float(half_width)
            row["pred_interval_width_90"] = float(high - low)
            row["pred_interval_source_90"] = source

    return row


def rolling_backtest(df: pd.DataFrame, targets, start_train=None, model_family="current"):
    if FAST_TARGETS_ONLY:
        targets = [t for t in targets if t in TARGETS]

    pred_rows = []
    target_windows = []

    for target in targets:
        if target not in df.columns:
            continue

        target_df = df[df[target].notna()].copy()
        target_df = target_df.sort_values("date").reset_index(drop=True)

        if start_train is None:
            target_start_train = min(85, max(55, len(target_df) // 3))
        else:
            target_start_train = int(start_train)

        target_windows.append({
            "target": target,
            "available_nonnull_rows": int(len(target_df)),
            "start_train": int(target_start_train),
            "prediction_rows_planned": int(max(len(target_df) - target_start_train, 0)),
            "sample_start_date": str(pd.to_datetime(target_df["date"]).min()) if len(target_df) else "",
            "sample_end_date": str(pd.to_datetime(target_df["date"]).max()) if len(target_df) else "",
        })

        if len(target_df) <= target_start_train:
            continue

        feature_sets = get_feature_sets(df, target)
        n_steps = len(target_df) - target_start_train

        for i in range(target_start_train, len(target_df)):
            train = target_df.iloc[:i].copy()
            test = target_df.iloc[[i]].copy()
            step_idx = i - target_start_train + 1

            print(
                f"Rolling target {target} step {step_idx}/{n_steps}",
                end="\r",
            )

            y_train = pd.to_numeric(train[target], errors="coerce")
            valid = y_train.notna()

            if valid.sum() < 35:
                continue

            row = {
                "event_id": test["event_id"].iloc[0],
                "date": test["date"].iloc[0],
                "asset_target": target,
                "actual": float(test[target].iloc[0]),
            }

            case_col = f"case_pred_{target}"
            pred_case = np.nan

            if case_col in df.columns and pd.notna(test[case_col].iloc[0]):
                pred_case = float(test[case_col].iloc[0])

            row["pred_case_model"] = pred_case

            for name, cols in feature_sets:
                if len(cols) == 0:
                    continue

                X_train = train.loc[valid].copy()
                y_reg = y_train[valid].copy()

                pred_reg, pred_std = predict_regression_ensemble(
                    X_train,
                    y_reg,
                    test,
                    cols,
                    model_family=model_family,
                    feature_set_name=name,
                    target=target,
                )

                row[f"pred_{name}_reg"] = pred_reg
                row[f"pred_{name}"] = pred_reg
                row[f"pred_std_{name}"] = pred_std
                row[f"confidence_{name}"] = float(
                    1.0 / (1.0 + pred_std / (abs(pred_reg) + 1e-8))
                )

            sim = float(test.get("case_avg_similarity", pd.Series([0])).iloc[0] or 0)

            row["case_avg_similarity"] = sim
            row["case_neighbor_count"] = float(
                test.get("case_neighbor_count", pd.Series([0])).iloc[0] or 0
            )

            supervised_pred = row.get("pred_fusion", np.nan)
            supervised_std = row.get("pred_std_fusion", 0.0)

            case_std_col = f"case_std_{target}"

            case_std = (
                float(test[case_std_col].iloc[0])
                if case_std_col in df.columns and pd.notna(test[case_std_col].iloc[0])
                else np.nan
            )

            if not np.isnan(pred_case) and not np.isnan(supervised_pred):
                sim_component = np.clip((sim - 0.85) / 0.15, 0.0, 1.0)

                if not np.isnan(case_std):
                    uncertainty_component = 1.0 / (1.0 + case_std / (abs(pred_case) + 1e-8))
                else:
                    uncertainty_component = 0.5

                if "SPY" in target:
                    max_case_weight = 0.25
                elif "GLD" in target:
                    max_case_weight = 0.30
                elif "UUP" in target:
                    max_case_weight = 0.35
                else:
                    max_case_weight = 0.45

                case_weight = float(
                    np.clip(
                        0.08 + 0.25 * sim_component + 0.10 * uncertainty_component,
                        0.03,
                        max_case_weight,
                    )
                )

                pred_final = (1 - case_weight) * supervised_pred + case_weight * pred_case

            else:
                case_weight = 0.0
                pred_final = supervised_pred

            # 恢复预测幅度，降低过度均值回归
            final_scale = ASSET_SCALE.get(target, 1.10)
            pred_final = pred_final * final_scale

            recent_std = float(np.nanstd(y_train[valid].tail(60)))

            if recent_std > 0:
                pred_final = float(np.clip(pred_final, -1.75 * recent_std, 1.75 * recent_std))

            resid_scale = float(np.nanstd(y_train[valid].tail(50)))
            total_std = float(np.nanmean([supervised_std, resid_scale]))

            if total_std == 0 or np.isnan(total_std):
                total_std = float(np.nanstd(y_train[valid]))

            row["case_weight_final"] = case_weight
            row["pred_final"] = float(pred_final)
            row["bayesian_std_final"] = total_std
            row["bayesian_confidence_final"] = float(
                1.0 / (1.0 + total_std / (abs(pred_final) + 1e-8))
            )

            row = add_model_intervals(row, pred_rows, target, y_train[valid])
            pred_rows.append(row)

    print("\nRolling backtest finished.")
    preds = pd.DataFrame(pred_rows)
    if not preds.empty and "date" in preds.columns:
        preds = preds.sort_values(["date", "asset_target"]).reset_index(drop=True)
    preds.attrs["target_windows"] = target_windows
    return preds


# ---------------------------------------------------------------------
# 6. 评估与图表
# ---------------------------------------------------------------------
def evaluate(preds: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for asset, g0 in preds.groupby("asset_target"):
        for model_name, col in MODEL_PRED_COLS.items():
            if col not in g0.columns:
                continue

            g = g0.dropna(subset=[col, "actual"]).copy()

            if g.empty:
                continue

            direction_actual = (g["actual"] > 0).astype(int)
            direction_pred = (g[col] > 0).astype(int)

            coverage = np.nan
            avg_width = np.nan
            median_width = np.nan
            avg_half_width = np.nan
            width_to_mae = np.nan

            low_col = f"pred_interval_low_90_{model_name}"
            high_col = f"pred_interval_high_90_{model_name}"

            if low_col in g.columns and high_col in g.columns:
                interval_rows = g.dropna(subset=[low_col, high_col]).copy()

                if not interval_rows.empty:
                    interval_width = interval_rows[high_col] - interval_rows[low_col]
                    coverage = (
                        (interval_rows["actual"] >= interval_rows[low_col])
                        & (interval_rows["actual"] <= interval_rows[high_col])
                    ).mean()
                    avg_width = float(interval_width.mean())
                    median_width = float(interval_width.median())
                    avg_half_width = float((interval_width / 2).mean())

            mae = float(mean_absolute_error(g["actual"], g[col]))

            if pd.notna(avg_width) and mae > 0:
                width_to_mae = float(avg_width / mae)

            rows.append({
                "asset_target": asset,
                "task": "regression",
                "model": model_name,
                "n_test": int(len(g)),
                "direction_accuracy": float(accuracy_score(direction_actual, direction_pred)),
                "balanced_direction_accuracy": float(
                    balanced_accuracy_score(direction_actual, direction_pred)
                ),
                "MAE": mae,
                "RMSE": float(mean_squared_error(g["actual"], g[col]) ** 0.5),
                "interval_90pct_coverage": coverage,
                "interval_90pct_avg_width": avg_width,
                "interval_90pct_median_width": median_width,
                "interval_90pct_avg_half_width": avg_half_width,
                "interval_width_to_mae": width_to_mae,
            })

    return pd.DataFrame(rows)


def evaluate_by_time_segment(preds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if "date" not in preds.columns or preds.empty:
        return pd.DataFrame(rows)

    dated = preds.copy()
    dated["date"] = pd.to_datetime(dated["date"], errors="coerce")

    for segment_name, start, end in TIME_SEGMENTS:
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        seg = dated[(dated["date"] >= start_dt) & (dated["date"] <= end_dt)].copy()
        if seg.empty:
            continue

        seg_eval = evaluate(seg)
        if seg_eval.empty:
            continue

        seg_eval.insert(0, "segment", segment_name)
        seg_eval.insert(1, "segment_start", start)
        seg_eval.insert(2, "segment_end", end)
        rows.extend(seg_eval.to_dict("records"))

    return pd.DataFrame(rows)


def incremental_summary(eval_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for (asset, task), g in eval_df.groupby(["asset_target", "task"]):
        base = g[g["model"] == "baseline"]

        if base.empty:
            continue

        base_acc = float(base["direction_accuracy"].iloc[0])
        base_bal_acc = float(base["balanced_direction_accuracy"].iloc[0])
        base_mae = float(base["MAE"].iloc[0])

        for _, r in g.iterrows():
            rows.append({
                "asset_target": asset,
                "task": task,
                "model": r["model"],
                "accuracy_increment_vs_baseline": float(r["direction_accuracy"] - base_acc),
                "balanced_accuracy_increment_vs_baseline": float(
                    r["balanced_direction_accuracy"] - base_bal_acc
                ),
                "MAE_change_vs_baseline": float(r["MAE"] - base_mae),
                "MAE_not_worse_than_baseline": (
                    bool(r["MAE"] <= base_mae)
                    if pd.notna(r["MAE"]) and pd.notna(base_mae)
                    else np.nan
                ),
            })

    return pd.DataFrame(rows)


def make_figures(preds: pd.DataFrame, eval_df: pd.DataFrame, fig_dir: Path):
    fig_dir.mkdir(parents=True, exist_ok=True)

    figure_specs = [
        ("direction_accuracy", "regression"),
        ("balanced_direction_accuracy", "regression"),
        ("MAE", "regression"),
        ("RMSE", "regression"),
    ]

    for metric, task in figure_specs:
        task_eval = eval_df[eval_df["task"] == task].copy()

        if task_eval.empty:
            continue

        pivot = task_eval.pivot(index="asset_target", columns="model", values=metric)

        ax = pivot.plot(kind="bar", figsize=(11, 5))
        ax.set_title(f"{task} {metric}")
        ax.set_xlabel("Asset target")
        ax.set_ylabel(metric)

        plt.xticks(rotation=25, ha="right")
        plt.tight_layout()
        plt.savefig(fig_dir / f"{task}_{metric}_anti_mean_reversion.png", dpi=200)
        plt.close()

    for asset, g in preds.groupby("asset_target"):
        g = g.sort_values("date")

        plt.figure(figsize=(11, 5))
        plt.plot(g["date"], g["actual"], label="Actual")
        plt.plot(g["date"], g["pred_final"], label="Fusion case")

        if "pred_interval_low_90" in g.columns:
            plt.fill_between(
                g["date"],
                g["pred_interval_low_90"],
                g["pred_interval_high_90"],
                alpha=0.15,
                label="90% interval",
            )

        plt.title(f"{asset}: actual vs fusion case")
        plt.xlabel("Date")
        plt.ylabel("1-day return / change")
        plt.legend()
        plt.tight_layout()

        safe = asset.replace("^", "").replace(".", "_")
        plt.savefig(fig_dir / f"{safe}_actual_vs_final_anti_mean_reversion.png", dpi=200)
        plt.close()


def _xgb_score_to_feature(score: dict, feature_cols: list[str]) -> dict[str, float]:
    mapped = {feature: 0.0 for feature in feature_cols}

    for key, value in score.items():
        feature = key

        if key.startswith("f") and key[1:].isdigit():
            idx = int(key[1:])

            if 0 <= idx < len(feature_cols):
                feature = feature_cols[idx]

        if feature in mapped:
            mapped[feature] = float(value)

    return mapped


def _xgb_importance_rows(model, feature_cols, meta):
    booster = model.named_steps["model"].get_booster()
    importance_types = ["weight", "gain", "cover", "total_gain", "total_cover"]
    scores = {
        importance_type: _xgb_score_to_feature(
            booster.get_score(importance_type=importance_type),
            feature_cols,
        )
        for importance_type in importance_types
    }

    rows = []

    for feature in feature_cols:
        row = {**meta, "feature": feature}

        for importance_type in importance_types:
            row[importance_type] = scores[importance_type].get(feature, 0.0)

        rows.append(row)

    return rows


def compute_xgboost_feature_importance(df: pd.DataFrame, targets: list[str]) -> pd.DataFrame:
    if not HAS_XGB:
        return pd.DataFrame()

    rows = []

    for target in targets:
        if target not in df.columns:
            continue

        y = pd.to_numeric(df[target], errors="coerce")
        valid = y.notna()

        if valid.sum() < 35:
            continue

        train = df.loc[valid].copy()
        y_reg = y.loc[valid].copy()

        for feature_set_name, feature_cols in get_feature_sets(df, target):
            if not feature_cols:
                continue

            output_feature_set = feature_set_name

            for seed in SEEDS:
                reg = make_regressor(
                    seed=seed,
                    model_family="xgboost",
                    feature_set_name=feature_set_name,
                    target=target,
                )
                reg.fit(train[feature_cols], y_reg)
                rows.extend(_xgb_importance_rows(
                    reg,
                    feature_cols,
                    {
                        "asset_target": target,
                        "feature_set": output_feature_set,
                        "task": "regression",
                        "seed": seed,
                    },
                ))

    if not rows:
        return pd.DataFrame()

    detailed = pd.DataFrame(rows)
    group_cols = ["asset_target", "feature_set", "task", "feature"]
    value_cols = ["weight", "gain", "cover", "total_gain", "total_cover"]

    summary = (
        detailed
        .groupby(group_cols, as_index=False)[value_cols]
        .mean()
    )

    for col in value_cols:
        total = summary.groupby(["asset_target", "feature_set", "task"])[col].transform("sum")
        summary[f"{col}_share"] = np.where(total > 0, summary[col] / total, 0.0)

    summary["rank_by_gain"] = (
        summary
        .groupby(["asset_target", "feature_set", "task"])["gain"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    return summary.sort_values(
        ["asset_target", "feature_set", "task", "rank_by_gain", "feature"]
    )


def compute_regression_permutation_importance(
    df: pd.DataFrame,
    targets: list[str],
    model_family: str,
    validation_fraction: float = PERMUTATION_VALIDATION_FRACTION,
    n_repeats: int = PERMUTATION_REPEATS,
) -> pd.DataFrame:
    if model_family == "xgboost" and not HAS_XGB:
        return pd.DataFrame()
    if model_family not in {"hgbdt", "xgboost"}:
        return pd.DataFrame()

    rows = []

    for target in targets:
        if target not in df.columns:
            continue

        y = pd.to_numeric(df[target], errors="coerce")
        valid = y.notna()

        if valid.sum() < 60:
            continue

        target_df = df.loc[valid].copy()
        y_reg = y.loc[valid].copy()

        split = int(len(target_df) * (1.0 - validation_fraction))

        if split < 35 or len(target_df) - split < 15:
            continue

        train = target_df.iloc[:split].copy()
        valid_df = target_df.iloc[split:].copy()
        y_train = y_reg.iloc[:split].copy()
        y_valid = y_reg.iloc[split:].copy()

        for feature_set_name, feature_cols in get_feature_sets(df, target):
            if not feature_cols:
                continue

            output_feature_set = feature_set_name

            X_valid_base = valid_df[feature_cols].copy()

            for seed in SEEDS:
                reg = make_regressor(
                    seed=seed,
                    model_family=model_family,
                    feature_set_name=feature_set_name,
                    target=target,
                )
                reg.fit(train[feature_cols], y_train)

                baseline_pred = reg.predict(X_valid_base)
                baseline_rmse = float(mean_squared_error(y_valid, baseline_pred) ** 0.5)
                baseline_mae = float(mean_absolute_error(y_valid, baseline_pred))

                for feature in feature_cols:
                    for repeat in range(n_repeats):
                        rng = np.random.default_rng(seed + 1009 * (repeat + 1))
                        X_perm = X_valid_base.copy()
                        values = X_perm[feature].to_numpy(copy=True)
                        rng.shuffle(values)
                        X_perm[feature] = values

                        perm_pred = reg.predict(X_perm)
                        perm_rmse = float(mean_squared_error(y_valid, perm_pred) ** 0.5)
                        perm_mae = float(mean_absolute_error(y_valid, perm_pred))

                        rows.append({
                            "asset_target": target,
                            "feature_set": output_feature_set,
                            "task": "regression",
                            "model_family": model_family,
                            "feature": feature,
                            "seed": seed,
                            "repeat": repeat,
                            "n_train": int(len(train)),
                            "n_validation": int(len(valid_df)),
                            "baseline_rmse": baseline_rmse,
                            "permuted_rmse": perm_rmse,
                            "rmse_increase": perm_rmse - baseline_rmse,
                            "baseline_mae": baseline_mae,
                            "permuted_mae": perm_mae,
                            "mae_increase": perm_mae - baseline_mae,
                        })

    if not rows:
        return pd.DataFrame()

    detailed = pd.DataFrame(rows)
    group_cols = ["asset_target", "feature_set", "task", "model_family", "feature"]
    value_cols = [
        "baseline_rmse",
        "permuted_rmse",
        "rmse_increase",
        "baseline_mae",
        "permuted_mae",
        "mae_increase",
    ]

    summary = (
        detailed
        .groupby(group_cols, as_index=False)
        .agg({
            **{col: "mean" for col in value_cols},
            "n_train": "first",
            "n_validation": "first",
        })
    )

    std_df = (
        detailed
        .groupby(group_cols, as_index=False)[
            ["rmse_increase", "mae_increase"]
        ]
        .std()
        .rename(columns={
            "rmse_increase": "rmse_increase_std",
            "mae_increase": "mae_increase_std",
        })
    )
    summary = summary.merge(std_df, on=group_cols, how="left")
    summary[["rmse_increase_std", "mae_increase_std"]] = (
        summary[["rmse_increase_std", "mae_increase_std"]]
        .fillna(0.0)
    )

    summary["rank_by_rmse_increase"] = (
        summary
        .groupby(["asset_target", "feature_set", "task", "model_family"])["rmse_increase"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    summary["rank_by_mae_increase"] = (
        summary
        .groupby(["asset_target", "feature_set", "task", "model_family"])["mae_increase"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    return summary.sort_values(
        [
            "asset_target",
            "feature_set",
            "task",
            "model_family",
            "rank_by_rmse_increase",
            "feature",
        ]
    )


def make_xgboost_feature_importance_figures(
    importance_df: pd.DataFrame,
    fig_dir: Path,
    top_n: int = 20,
) -> None:
    if importance_df.empty:
        return

    out_dir = fig_dir / "feature_importance"
    out_dir.mkdir(parents=True, exist_ok=True)

    regression = importance_df[importance_df["task"] == "regression"].copy()

    for (asset, feature_set), g in regression.groupby(["asset_target", "feature_set"]):
        top = g.sort_values("gain", ascending=False).head(top_n).copy()

        if top.empty or top["gain"].sum() <= 0:
            continue

        top = top.sort_values("gain", ascending=True)

        plt.figure(figsize=(9, 6))
        plt.barh(top["feature"], top["gain"])
        plt.title(f"{asset} / {feature_set}: XGBoost regression feature importance")
        plt.xlabel("Mean gain across seeds")
        plt.ylabel("Feature")
        plt.tight_layout()

        safe_asset = asset.replace("^", "").replace(".", "_")
        safe_set = feature_set.replace("/", "_")
        plt.savefig(
            out_dir / f"{safe_asset}_{safe_set}_regression_top{top_n}_gain.png",
            dpi=200,
        )
        plt.close()


def make_permutation_importance_figures(
    permutation_df: pd.DataFrame,
    fig_dir: Path,
    top_n: int = 20,
) -> None:
    if permutation_df.empty:
        return

    out_dir = fig_dir / "permutation_importance"
    out_dir.mkdir(parents=True, exist_ok=True)

    for (asset, feature_set), g in permutation_df.groupby(["asset_target", "feature_set"]):
        top = (
            g.sort_values("rmse_increase", ascending=False)
            .head(top_n)
            .copy()
        )

        if top.empty:
            continue

        top = top.sort_values("rmse_increase", ascending=True)
        model_family = str(g["model_family"].iloc[0]) if "model_family" in g.columns else "model"

        plt.figure(figsize=(9, 6))
        plt.barh(top["feature"], top["rmse_increase"])
        plt.title(f"{asset} / {feature_set}: {model_family} regression permutation importance")
        plt.xlabel("RMSE increase after permutation")
        plt.ylabel("Feature")
        plt.tight_layout()

        safe_asset = asset.replace("^", "").replace(".", "_")
        safe_set = feature_set.replace("/", "_")
        plt.savefig(
            out_dir / f"{safe_asset}_{safe_set}_regression_top{top_n}_rmse_increase.png",
            dpi=200,
        )
        plt.close()


def create_experiment_dir(model_family: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_dir = EXPERIMENTS_DIR / f"experiment_{timestamp}_{model_family}"
    suffix = 1

    while exp_dir.exists():
        exp_dir = EXPERIMENTS_DIR / f"experiment_{timestamp}_{model_family}_{suffix:02d}"
        suffix += 1

    (exp_dir / "figures").mkdir(parents=True, exist_ok=False)
    return exp_dir


def describe_model_family(model_family: str) -> dict[str, str]:
    if model_family == "current":
        return {
            "regressor": "baseline uses Ridge; shock/fusion use XGBRegressor if available else HistGradientBoostingRegressor",
            "comparison_note": "legacy mixed-model setup; use ridge/lasso/elasticnet/xgboost/hgbdt for clean feature-set comparisons",
        }
    if model_family == "ridge":
        return {
            "regressor": "Ridge(alpha=1.0)",
            "comparison_note": "same linear L2 model family for baseline/shock/fusion",
        }
    if model_family == "lasso":
        return {
            "regressor": "Lasso(alpha=0.001)",
            "comparison_note": "same sparse L1 model family for baseline/shock/fusion",
        }
    if model_family == "elasticnet":
        return {
            "regressor": "ElasticNet(alpha=0.001, l1_ratio=0.5)",
            "comparison_note": "same mixed L1/L2 model family for baseline/shock/fusion",
        }
    if model_family == "xgboost":
        return {
            "regressor": "XGBRegressor",
            "comparison_note": "same XGBoost model family for baseline/shock/fusion",
        }
    if model_family == "hgbdt":
        return {
            "regressor": "HistGradientBoostingRegressor",
            "comparison_note": "same sklearn gradient boosting model family for baseline/shock/fusion",
        }
    raise ValueError(f"Unknown model_family: {model_family}")


def write_experiment_config(
    exp_dir: Path,
    df: pd.DataFrame,
    targets: list[str],
    preds: pd.DataFrame,
    model_family: str,
) -> None:
    config = {
        "experiment_name": exp_dir.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "script": str(Path(__file__).resolve()),
        "inputs": {
            "panel_file": str(B_FILE),
            "shock_file": str(SHOCK_FILE),
            "retrieval_file": str(RETRIEVAL_FILE),
            "baseline_best_params_file": str(BASELINE_BEST_PARAMS_FILE),
        },
        "outputs": {
            "experiment_dir": str(exp_dir),
            "figures_dir": str(exp_dir / "figures"),
            "predictions": str(exp_dir / "predictions_anti_mean_reversion.csv"),
            "evaluation_summary": str(exp_dir / "evaluation_summary_anti_mean_reversion.csv"),
            "segment_evaluation_summary": str(exp_dir / "segment_evaluation_summary_anti_mean_reversion.csv"),
            "incremental_value_summary": str(exp_dir / "incremental_value_summary_anti_mean_reversion.csv"),
            "xgboost_feature_importance": str(exp_dir / "xgboost_feature_importance.csv") if model_family == "xgboost" else "",
            "xgboost_feature_importance_figures": str(exp_dir / "figures" / "feature_importance") if model_family == "xgboost" else "",
            "regression_permutation_importance": (
                str(exp_dir / f"{model_family}_permutation_importance.csv")
                if model_family in {"hgbdt", "xgboost"}
                else ""
            ),
            "regression_permutation_importance_figures": (
                str(exp_dir / "figures" / "permutation_importance")
                if model_family in {"hgbdt", "xgboost"}
                else ""
            ),
            "modeling_dataset": str(exp_dir / "modeling_dataset_anti_mean_reversion.csv"),
        },
        "targets": targets,
        "assets": ASSETS,
        "fast_targets_only": FAST_TARGETS_ONLY,
        "macro_market_features": MACRO_MARKET_FEATURES,
        "derived_market_state_features": DERIVED_MARKET_STATE_FEATURES,
        "shock_bases": SHOCK_BASES,
        "direction_map": DIRECTION_MAP,
        "confidence_map": CONF_MAP,
        "seeds": SEEDS,
        "time_segments": [
            {"name": name, "start": start, "end": end}
            for name, start, end in TIME_SEGMENTS
        ],
        "prediction_interval": {
            "level": 0.90,
            "method": "rolling conformal absolute residual by asset_target and model",
            "residual_window": 80,
            "min_residuals": 20,
            "fallback": "1.64 * rolling 60-observation target volatility",
            "applies_to_models": list(MODEL_PRED_COLS.keys()),
            "applies_to_task": "regression",
            "evaluation_metrics": [
                "interval_90pct_coverage",
                "interval_90pct_avg_width",
                "interval_90pct_median_width",
                "interval_90pct_avg_half_width",
                "interval_width_to_mae",
            ],
        },
        "asset_scale": ASSET_SCALE,
        "xgboost_available": HAS_XGB,
        "model_family": model_family,
        "feature_importance": {
            "enabled": model_family == "xgboost",
            "method": "XGBoost booster importance averaged across configured seeds",
            "tasks": ["regression"],
            "importance_types": ["weight", "gain", "cover", "total_gain", "total_cover"],
            "ranking_metric": "gain",
            "permutation_importance": {
                "enabled": model_family in {"hgbdt", "xgboost"},
                "method": "Regression permutation importance on the last 30% validation split",
                "task": "regression",
                "validation_split": "last 30% of each asset target after fitting on first 70%",
                "repeats": PERMUTATION_REPEATS,
                "primary_metric": "rmse_increase",
                "secondary_metric": "mae_increase",
            },
        },
        "model_setup": {
            **describe_model_family(model_family),
            "parameter_source": "Per target/model_family regression best params from baseline_best_params.csv",
            "task_separation": {
                "regression": "pred_* columns are pure return predictions from regression models and are evaluated with MAE/RMSE.",
                "direction_accuracy": "Direction accuracy is computed from the sign of regression predictions.",
            },
            "feature_sets": {
                "baseline": "macro_market_features + derived_market_state_features",
                "shock_main": "baseline + shock direction/strength/confidence/score features",
                "shock_interactions": "baseline + shock_main + shock x market-state interaction features",
                "rag_memory": "baseline + RAG case-memory features",
                "shock_rag": "baseline + shock_main + RAG case-memory features",
                "fusion": "baseline + shock_main + shock_interactions + RAG case-memory features",
                "case_model": "weighted average of RAG neighbor returns",
                "fusion_case": "fusion blended with case_model and confidence scaling",
            },
        },
        "backtest": {
            "start_train_rule": "per target after filtering non-missing target rows: min(85, max(55, len(target_df) // 3))",
            "n_modeling_rows": int(len(df)),
            "n_prediction_rows": int(len(preds)),
            "target_windows": preds.attrs.get("target_windows", []),
            "prediction_date_min": str(pd.to_datetime(preds["date"]).min()) if "date" in preds.columns and len(preds) else "",
            "prediction_date_max": str(pd.to_datetime(preds["date"]).max()) if "date" in preds.columns and len(preds) else "",
        },
    }

    (exp_dir / "experiment_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------
# 7. 主程序入口
# ---------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Run FOMC return prediction rolling backtest.")
    parser.add_argument(
        "--model-family",
        choices=MODEL_FAMILIES,
        default="current",
        help=(
            "Supervised model family used by baseline/shock/fusion. "
            "'current' keeps the legacy mixed setup; ridge/lasso/elasticnet/xgboost/hgbdt "
            "use one unified model family across feature sets."
        ),
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=SEEDS,
        help="Random seeds used for stochastic tree-model ensembling.",
    )
    return parser.parse_args()


def main():
    global SEEDS
    args = parse_args()
    SEEDS = list(args.seeds)

    if args.model_family == "xgboost" and not HAS_XGB:
        raise SystemExit("当前环境未安装 xgboost，不能使用 --model-family xgboost；请安装 xgboost 或改用 hgbdt。")

    exp_dir = create_experiment_dir(args.model_family)
    fig_dir = exp_dir / "figures"
    print(f"Experiment directory: {exp_dir}")
    print(f"Model family: {args.model_family}")
    print(f"Seeds: {SEEDS}")

    print("Loading inputs...")
    b, shocks, retrieval = read_inputs()

    print("Building case-memory features...")
    cases = build_case_features(retrieval)

    print("Building modeling dataset...")
    df = build_model_dataset(b, shocks, cases)

    targets = get_available_targets(df)

    if FAST_TARGETS_ONLY:
        targets = [t for t in targets if t in TARGETS]

    print("Targets:", targets)

    if len(targets) == 0:
        print("No target columns found.")
        return

    print("Running anti-mean-reversion rolling backtest...")
    preds = rolling_backtest(df, targets=targets, model_family=args.model_family)

    if preds is None or len(preds) == 0:
        print("No prediction rows produced.")
        return

    print("Evaluating...")
    eval_df = evaluate(preds)
    segment_eval_df = evaluate_by_time_segment(preds)
    inc_df = incremental_summary(eval_df)
    importance_df = pd.DataFrame()
    permutation_df = pd.DataFrame()

    if args.model_family == "xgboost":
        print("Computing XGBoost feature importance...")
        importance_df = compute_xgboost_feature_importance(df, targets)
    if args.model_family in {"hgbdt", "xgboost"}:
        print(f"Computing {args.model_family} regression permutation importance...")
        permutation_df = compute_regression_permutation_importance(
            df,
            targets,
            model_family=args.model_family,
        )

    print("Saving outputs...")

    preds.to_csv(exp_dir / "predictions_anti_mean_reversion.csv", index=False)
    eval_df.to_csv(exp_dir / "evaluation_summary_anti_mean_reversion.csv", index=False)
    segment_eval_df.to_csv(exp_dir / "segment_evaluation_summary_anti_mean_reversion.csv", index=False)
    inc_df.to_csv(exp_dir / "incremental_value_summary_anti_mean_reversion.csv", index=False)
    if args.model_family == "xgboost" and not importance_df.empty:
        importance_df.to_csv(exp_dir / "xgboost_feature_importance.csv", index=False)
    if args.model_family in {"hgbdt", "xgboost"} and not permutation_df.empty:
        permutation_df.to_csv(exp_dir / f"{args.model_family}_permutation_importance.csv", index=False)
    df.to_csv(exp_dir / "modeling_dataset_anti_mean_reversion.csv", index=False)
    write_experiment_config(exp_dir, df, targets, preds, args.model_family)

    make_figures(preds, eval_df, fig_dir)
    if args.model_family == "xgboost" and not importance_df.empty:
        make_xgboost_feature_importance_figures(importance_df, fig_dir)
    if args.model_family in {"hgbdt", "xgboost"} and not permutation_df.empty:
        make_permutation_importance_figures(permutation_df, fig_dir)

    print("\nSaved files:")
    print(exp_dir / "predictions_anti_mean_reversion.csv")
    print(exp_dir / "evaluation_summary_anti_mean_reversion.csv")
    print(exp_dir / "segment_evaluation_summary_anti_mean_reversion.csv")
    print(exp_dir / "incremental_value_summary_anti_mean_reversion.csv")
    if args.model_family == "xgboost" and not importance_df.empty:
        print(exp_dir / "xgboost_feature_importance.csv")
        print(fig_dir / "feature_importance")
    if args.model_family in {"hgbdt", "xgboost"} and not permutation_df.empty:
        print(exp_dir / f"{args.model_family}_permutation_importance.csv")
        print(fig_dir / "permutation_importance")
    print(exp_dir / "modeling_dataset_anti_mean_reversion.csv")
    print(exp_dir / "experiment_config.json")
    print(fig_dir)

    print("\nEvaluation summary:")
    if len(eval_df):
        print(eval_df.to_string(index=False))
    else:
        print("No evaluation rows produced.")

    print("\nSegment evaluation summary:")
    if len(segment_eval_df):
        print(segment_eval_df.to_string(index=False))
    else:
        print("No segment evaluation rows produced.")

    print("\nIncremental value summary:")
    if len(inc_df):
        print(inc_df.to_string(index=False))
    else:
        print("No incremental value rows produced.")

    if args.model_family == "xgboost":
        print("\nXGBoost feature importance summary:")
        if len(importance_df):
            top = (
                importance_df[importance_df["task"] == "regression"]
                .sort_values(["asset_target", "feature_set", "rank_by_gain"])
                .groupby(["asset_target", "feature_set"])
                .head(10)
            )
            print(top.to_string(index=False))
        else:
            print("No XGBoost feature importance rows produced.")

    if args.model_family in {"hgbdt", "xgboost"}:
        print(f"\n{args.model_family} regression permutation importance summary:")
        if len(permutation_df):
            top_perm = (
                permutation_df
                .sort_values([
                    "asset_target",
                    "feature_set",
                    "rank_by_rmse_increase",
                ])
                .groupby(["asset_target", "feature_set"])
                .head(10)
            )
            print(top_perm.to_string(index=False))
        else:
            print(f"No {args.model_family} regression permutation importance rows produced.")


if __name__ == "__main__":
    main()
