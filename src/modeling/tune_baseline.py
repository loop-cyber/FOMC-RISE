#!/usr/bin/env python3
"""在初始扩展窗口训练集上调优基准模型。"""
from __future__ import annotations

import argparse
import itertools
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    mean_absolute_error,
    mean_squared_error,
)

import modeling


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TUNING_DIR = PROJECT_ROOT / "outputs" / "modeling" / "tuning"
MODEL_FAMILIES = ["ridge", "lasso", "elasticnet", "hgbdt", "xgboost"]


def expand_grid(grid: dict) -> list[dict]:
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


REGRESSION_GRIDS = {
    "ridge": {
        "model__alpha": [0.01, 0.1, 1.0, 5.0, 10.0, 20.0],
    },
    "lasso": {
        "model__alpha": [0.0001, 0.0005, 0.001, 0.005, 0.01],
        "model__max_iter": [5000],
    },
    "elasticnet": {
        "model__alpha": [0.0001, 0.0005, 0.001, 0.005],
        "model__l1_ratio": [0.2, 0.5, 0.8],
        "model__max_iter": [5000],
    },
    "hgbdt": {
        "model__max_iter": [40, 60, 100],
        "model__max_leaf_nodes": [4, 8, 16],
        "model__learning_rate": [0.03, 0.06],
        "model__l2_regularization": [0.0, 0.1, 1.0],
        "model__min_samples_leaf": [5, 10, 20],
    },
    "xgboost": {
        "model__n_estimators": [30, 40, 80],
        "model__max_depth": [1, 2, 3],
        "model__learning_rate": [0.03, 0.06],
        "model__subsample": [0.7, 0.9, 1.0],
        "model__colsample_bytree": [0.7, 0.9, 1.0],
        "model__reg_alpha": [0.0, 0.1, 0.5],
        "model__reg_lambda": [1.0, 3.0, 5.0],
        "model__min_child_weight": [1, 3],
    },
}


CLASSIFICATION_GRIDS = {
    "ridge": {
        "model__C": [0.05, 0.1, 0.5, 1.0, 2.0],
    },
    "lasso": {
        "model__C": [0.05, 0.1, 0.5, 1.0, 2.0],
    },
    "elasticnet": {
        "model__C": [0.05, 0.1, 0.5, 1.0],
        "model__l1_ratio": [0.2, 0.5, 0.8],
        "model__max_iter": [3000],
    },
    "hgbdt": {
        "model__max_iter": [40, 60, 100],
        "model__max_leaf_nodes": [4, 8, 16],
        "model__learning_rate": [0.03, 0.06],
        "model__l2_regularization": [0.0, 0.1, 1.0],
        "model__min_samples_leaf": [5, 10, 20],
    },
    "xgboost": {
        "model__n_estimators": [30, 40, 80],
        "model__max_depth": [1, 2, 3],
        "model__learning_rate": [0.03, 0.06],
        "model__subsample": [0.7, 0.9, 1.0],
        "model__colsample_bytree": [0.7, 0.9, 1.0],
        "model__reg_alpha": [0.0, 0.1, 0.5],
        "model__reg_lambda": [1.0, 3.0, 5.0],
        "model__min_child_weight": [1, 3],
    },
}


def create_output_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = TUNING_DIR / f"baseline_tuning_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=False)
    return out_dir


def build_dataset() -> pd.DataFrame:
    b, shocks, retrieval = modeling.read_inputs()
    cases = modeling.build_case_features(retrieval)
    return modeling.build_model_dataset(b, shocks, cases)


def get_baseline_features(df: pd.DataFrame, target: str) -> list[str]:
    for name, cols in modeling.get_feature_sets(df, target):
        if name == "baseline":
            return cols
    return []


def tune_regression_family(
    model_family: str,
    target: str,
    feature_cols: list[str],
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
) -> list[dict]:
    y_train = pd.to_numeric(train_df[target], errors="coerce")
    y_valid = pd.to_numeric(valid_df[target], errors="coerce")
    train_mask = y_train.notna()
    valid_mask = y_valid.notna()

    if train_mask.sum() < 20 or valid_mask.sum() < 5:
        return []

    rows = []

    for params in expand_grid(REGRESSION_GRIDS[model_family]):
        try:
            model = modeling.make_regressor(
                seed=42,
                model_family=model_family,
                feature_set_name="baseline",
            )
            model.set_params(**params)
            model.fit(train_df.loc[train_mask, feature_cols], y_train.loc[train_mask])
            pred = model.predict(valid_df.loc[valid_mask, feature_cols])

            mae = float(mean_absolute_error(y_valid.loc[valid_mask], pred))
            rmse = float(mean_squared_error(y_valid.loc[valid_mask], pred) ** 0.5)

            rows.append({
                "target": target,
                "model_family": model_family,
                "task": "regression",
                "n_train": int(train_mask.sum()),
                "n_validation": int(valid_mask.sum()),
                "MAE": mae,
                "RMSE": rmse,
                "params": json.dumps(params, ensure_ascii=False, sort_keys=True),
            })
        except Exception as exc:
            rows.append({
                "target": target,
                "model_family": model_family,
                "task": "regression",
                "n_train": int(train_mask.sum()),
                "n_validation": int(valid_mask.sum()),
                "MAE": np.nan,
                "RMSE": np.nan,
                "params": json.dumps(params, ensure_ascii=False, sort_keys=True),
                "error": str(exc),
            })

    return rows


def tune_classification_family(
    model_family: str,
    target: str,
    feature_cols: list[str],
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
) -> list[dict]:
    y_train_reg = pd.to_numeric(train_df[target], errors="coerce")
    y_valid_reg = pd.to_numeric(valid_df[target], errors="coerce")
    train_mask = y_train_reg.notna()
    valid_mask = y_valid_reg.notna()

    if train_mask.sum() < 20 or valid_mask.sum() < 5:
        return []

    y_train = (y_train_reg.loc[train_mask] > 0).astype(int)
    y_valid = (y_valid_reg.loc[valid_mask] > 0).astype(int)

    if y_train.nunique() < 2 or y_valid.nunique() < 2:
        return []

    rows = []

    for params in expand_grid(CLASSIFICATION_GRIDS[model_family]):
        try:
            model = modeling.make_classifier(
                seed=42,
                model_family=model_family,
                feature_set_name="baseline",
            )
            model.set_params(**params)
            model.fit(train_df.loc[train_mask, feature_cols], y_train)
            pred = model.predict(valid_df.loc[valid_mask, feature_cols])

            acc = float(accuracy_score(y_valid, pred))
            bal_acc = float(balanced_accuracy_score(y_valid, pred))

            rows.append({
                "target": target,
                "model_family": model_family,
                "task": "classification",
                "n_train": int(train_mask.sum()),
                "n_validation": int(valid_mask.sum()),
                "direction_accuracy": acc,
                "balanced_accuracy": bal_acc,
                "params": json.dumps(params, ensure_ascii=False, sort_keys=True),
            })
        except Exception as exc:
            rows.append({
                "target": target,
                "model_family": model_family,
                "task": "classification",
                "n_train": int(train_mask.sum()),
                "n_validation": int(valid_mask.sum()),
                "direction_accuracy": np.nan,
                "balanced_accuracy": np.nan,
                "params": json.dumps(params, ensure_ascii=False, sort_keys=True),
                "error": str(exc),
            })

    return rows


def choose_best(reg_df: pd.DataFrame, clf_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    if not reg_df.empty:
        usable = reg_df.dropna(subset=["MAE"]).copy()

        for (target, model_family), g in usable.groupby(["target", "model_family"]):
            best = g.sort_values(["MAE", "RMSE"]).iloc[0].to_dict()
            best["selection_metric"] = "MAE"
            rows.append(best)

    if not clf_df.empty:
        usable = clf_df.dropna(subset=["balanced_accuracy"]).copy()

        for (target, model_family), g in usable.groupby(["target", "model_family"]):
            best = (
                g.sort_values(
                    ["balanced_accuracy", "direction_accuracy"],
                    ascending=[False, False],
                )
                .iloc[0]
                .to_dict()
            )
            best["selection_metric"] = "balanced_accuracy"
            rows.append(best)

    return pd.DataFrame(rows)


def target_initial_split(
    df: pd.DataFrame,
    target: str,
    train_ratio: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    target_df = df[df[target].notna()].copy()
    target_df = target_df.sort_values("date").reset_index(drop=True)

    start_train = min(85, max(55, len(target_df) // 3))
    initial = target_df.iloc[:start_train].copy()
    split = int(len(initial) * train_ratio)
    train_df = initial.iloc[:split].copy()
    valid_df = initial.iloc[split:].copy()

    meta = {
        "target": target,
        "available_nonnull_rows": int(len(target_df)),
        "initial_window_size": int(len(initial)),
        "train_size": int(len(train_df)),
        "validation_size": int(len(valid_df)),
        "initial_start_date": str(pd.to_datetime(initial["date"]).min()) if len(initial) else "",
        "initial_end_date": str(pd.to_datetime(initial["date"]).max()) if len(initial) else "",
        "train_start_date": str(pd.to_datetime(train_df["date"]).min()) if len(train_df) else "",
        "train_end_date": str(pd.to_datetime(train_df["date"]).max()) if len(train_df) else "",
        "validation_start_date": str(pd.to_datetime(valid_df["date"]).min()) if len(valid_df) else "",
        "validation_end_date": str(pd.to_datetime(valid_df["date"]).max()) if len(valid_df) else "",
    }

    return train_df, valid_df, meta


def parse_args():
    parser = argparse.ArgumentParser(
        description="Tune baseline model hyperparameters on the initial expanding window."
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.60,
        help="Chronological train share inside the initial expanding window.",
    )
    parser.add_argument(
        "--model-family",
        nargs="+",
        choices=MODEL_FAMILIES + ["all"],
        default=["all"],
        help="Model families to tune. Default tunes all available families.",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=None,
        help="Optional target columns. Default uses available asset return targets.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not 0.1 < args.train_ratio < 0.9:
        raise SystemExit("--train-ratio must be between 0.1 and 0.9")

    model_families = MODEL_FAMILIES if "all" in args.model_family else args.model_family

    if "xgboost" in model_families and not modeling.HAS_XGB:
        print("xgboost is not installed in this environment; skipping xgboost.")
        model_families = [m for m in model_families if m != "xgboost"]

    out_dir = create_output_dir()
    df = build_dataset()

    targets = args.targets or modeling.get_available_targets(df)
    if modeling.FAST_TARGETS_ONLY:
        targets = [t for t in targets if t in modeling.TARGETS]

    reg_rows = []
    clf_rows = []
    split_metadata = []

    for target in targets:
        if target not in df.columns:
            continue

        feature_cols = get_baseline_features(df, target)

        if not feature_cols:
            continue

        train_df, valid_df, split_meta = target_initial_split(
            df,
            target,
            args.train_ratio,
        )
        split_metadata.append(split_meta)

        print(
            f"Tuning target={target}, baseline_features={len(feature_cols)}, "
            f"initial={split_meta['initial_window_size']}, "
            f"train={split_meta['train_size']}, validation={split_meta['validation_size']}"
        )

        for model_family in model_families:
            print(f"  model_family={model_family}")
            reg_rows.extend(tune_regression_family(
                model_family,
                target,
                feature_cols,
                train_df,
                valid_df,
            ))
            clf_rows.extend(tune_classification_family(
                model_family,
                target,
                feature_cols,
                train_df,
                valid_df,
            ))

    reg_df = pd.DataFrame(reg_rows)
    clf_df = pd.DataFrame(clf_rows)
    best_df = choose_best(reg_df, clf_df)

    reg_path = out_dir / "baseline_regression_grid.csv"
    clf_path = out_dir / "baseline_classification_grid.csv"
    best_path = out_dir / "baseline_best_params.csv"

    reg_df.to_csv(reg_path, index=False)
    clf_df.to_csv(clf_path, index=False)
    best_df.to_csv(best_path, index=False)

    config = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "train_ratio": args.train_ratio,
        "split_rule": "target-specific chronological split inside each target's non-missing initial expanding window",
        "target_splits": split_metadata,
        "feature_set": "baseline",
        "targets": targets,
        "model_families": model_families,
        "outputs": {
            "regression_grid": str(reg_path),
            "classification_grid": str(clf_path),
            "best_params": str(best_path),
        },
        "regression_selection_metric": "MAE",
        "classification_selection_metric": "balanced_accuracy",
    }
    (out_dir / "tuning_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nSaved tuning outputs:")
    print(reg_path)
    print(clf_path)
    print(best_path)
    print(out_dir / "tuning_config.json")

    if not best_df.empty:
        print("\nBest parameters:")
        print(best_df.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
