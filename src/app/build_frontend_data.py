#!/usr/bin/env python3
"""为 FOMC 用户报告工作台生成静态前端数据。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "src" / "frontend" / "fomc_report_app"
EXPERIMENT_DIR = FRONTEND_DIR / "demo_data"
TUNING_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "modeling"
    / "tuning"
    / "baseline_tuning_20260525_221743"
)

PREDICTIONS_FILE = EXPERIMENT_DIR / "predictions_anti_mean_reversion.csv"
EVALUATION_FILE = EXPERIMENT_DIR / "evaluation_summary_anti_mean_reversion.csv"
SEGMENT_EVALUATION_FILE = EXPERIMENT_DIR / "segment_evaluation_summary_anti_mean_reversion.csv"
CONFIG_FILE = EXPERIMENT_DIR / "experiment_config.json"
TUNED_PARAMS_FILE = TUNING_DIR / "baseline_best_params.csv"
PANEL_FILE = PROJECT_ROOT / "data" / "raw" / "data_for_text_diff.xlsx"
SHOCK_FILE = PROJECT_ROOT / "data" / "processed" / "fomc_policy_shocks.csv"
RETRIEVAL_FILE = PROJECT_ROOT / "outputs" / "retrieval" / "fomc_retrieval_pipeline_topk.csv"
REPORT_FILE = PROJECT_ROOT / "README.md"
LLM_LOGIC_CHAIN_FILE = FRONTEND_DIR / "llm_logic_chain_report.md"

TARGET_LABELS = {
    "SPY_ret": {"asset": "SPY", "label": "S&P 500 ETF"},
    "QQQ_ret": {"asset": "QQQ", "label": "Nasdaq 100 ETF"},
    "GLD_ret": {"asset": "GLD", "label": "Gold ETF"},
    "UUP_ret": {"asset": "UUP", "label": "US Dollar Index ETF"},
}

MARKET_STATE_COLUMNS = [
    "DX-Y.NYB",
    "^VIX",
    "DGS2",
    "DGS10",
    "CPIAUCSL",
    "UNRATE",
    "PAYEMS",
    "T10Y2Y",
    "BAA10Y",
    "UUP_volume",
    "SPY_volume",
    "GLD_volume",
    "QQQ_volume",
]

SHOCK_LABELS = {
    "interest_rate_path": "Interest Rate Path",
    "inflation_concern": "Inflation Concern",
    "growth_concern": "Growth Concern",
    "labor_market": "Labor Market",
    "financial_stability": "Financial Stability",
}


def clean_number(value, digits=4):
    if pd.isna(value):
        return None

    return round(float(value), digits)


def pct(value, digits=2):
    if pd.isna(value):
        return None

    return round(float(value) * 100, digits)


def normalize_model_name(name: str) -> str:
    return {
        "fusion_supervised": "fusion",
        "final_confidence_fusion": "fusion_case",
    }.get(str(name), str(name))


def latest_event_id(preds: pd.DataFrame) -> str:
    latest_date = pd.to_datetime(preds["date"]).max()
    latest = preds[pd.to_datetime(preds["date"]) == latest_date]
    return str(latest["event_id"].iloc[0])


def build_current_event(panel: pd.DataFrame, event_id: str) -> dict:
    row = panel[panel["event_id"] == event_id].iloc[0]
    text = str(row.get("statement_text", ""))
    previous_text = str(row.get("previous_statement_text", ""))

    return {
        "event_id": event_id,
        "date": str(pd.to_datetime(row["date"]).date()),
        "meeting_type": str(row.get("meeting_type", "")),
        "statement_excerpt": text[:780] + ("..." if len(text) > 780 else ""),
        "statement_text": text,
        "previous_statement_text": previous_text,
        "market_state": {
            col: clean_number(row.get(col), 3)
            for col in MARKET_STATE_COLUMNS
            if col in row.index
        },
    }


def build_shock_vector(shocks: pd.DataFrame, event_id: str) -> list[dict]:
    row = shocks[shocks["event_id"] == event_id].iloc[0]
    records = []

    for key, label in SHOCK_LABELS.items():
        records.append({
            "key": key,
            "label": label,
            "direction": str(row.get(f"{key}_direction", "")),
            "strength": clean_number(row.get(f"{key}_strength"), 2),
            "confidence": str(row.get(f"{key}_confidence", "")),
            "evidence": str(row.get(f"{key}_evidence", "")),
        })

    return records


def build_predictions(preds: pd.DataFrame, event_id: str) -> list[dict]:
    event_preds = preds[preds["event_id"] == event_id].copy()
    event_preds["asset_order"] = event_preds["asset_target"].map(
        {"SPY_ret": 0, "QQQ_ret": 1, "GLD_ret": 2, "UUP_ret": 3}
    )
    event_preds = event_preds.sort_values("asset_order")

    rows = []
    for _, row in event_preds.iterrows():
        target = str(row["asset_target"])
        meta = TARGET_LABELS.get(target, {"asset": target, "label": target})
        pred = float(row["pred_fusion"])
        low = float(row["pred_interval_low_90_fusion"])
        high = float(row["pred_interval_high_90_fusion"])
        prob_up = float(row["prob_up_fusion"])
        confidence = float(row["confidence_fusion"])

        rows.append({
            "asset": meta["asset"],
            "target": target,
            "label": meta["label"],
            "predicted_return": clean_number(pred, 6),
            "predicted_return_pct": pct(pred, 2),
            "direction": "up" if pred > 0 else "down",
            "direction_label": "上涨" if pred > 0 else "下跌",
            "prob_up": clean_number(prob_up, 4),
            "prob_up_pct": pct(prob_up, 1),
            "confidence": clean_number(confidence, 4),
            "confidence_pct": pct(confidence, 1),
            "interval_90_low": clean_number(low, 6),
            "interval_90_high": clean_number(high, 6),
            "interval_90_low_pct": pct(low, 2),
            "interval_90_high_pct": pct(high, 2),
            "interval_width_pct": pct(row["pred_interval_width_90_fusion"], 2),
            "case_avg_similarity": clean_number(row.get("case_avg_similarity"), 4),
            "case_neighbor_count": clean_number(row.get("case_neighbor_count"), 0),
        })

    return rows


def compact_text(value, limit=1100) -> str:
    if pd.isna(value):
        return ""

    text = " ".join(str(value).split())
    return text[:limit] + ("..." if len(text) > limit else "")


def shock_evidence_map(shocks: pd.DataFrame, event_id: str) -> dict:
    matched = shocks[shocks["event_id"] == event_id]

    if matched.empty:
        return {}

    row = matched.iloc[0]
    return {
        key: {
            "direction": str(row.get(f"{key}_direction", "")),
            "strength": clean_number(row.get(f"{key}_strength"), 2),
            "confidence": str(row.get(f"{key}_confidence", "")),
            "evidence": str(row.get(f"{key}_evidence", "")),
        }
        for key in SHOCK_LABELS
    }


def build_similar_cases(
    retrieval: pd.DataFrame,
    panel: pd.DataFrame,
    shocks: pd.DataFrame,
    event_id: str,
) -> list[dict]:
    cases = retrieval[retrieval["query_event_id"] == event_id].copy()
    cases = cases.sort_values("neighbor_rank").head(3)
    rows = []

    for _, row in cases.iterrows():
        neighbor_event_id = str(row["neighbor_event_id"])
        neighbor_panel = panel[panel["event_id"] == neighbor_event_id]
        neighbor_statement = ""
        neighbor_previous = ""

        if not neighbor_panel.empty:
            neighbor_statement = compact_text(neighbor_panel.iloc[0].get("statement_text"), 1300)
            neighbor_previous = compact_text(
                neighbor_panel.iloc[0].get("previous_statement_text"),
                900,
            )

        rows.append({
            "rank": int(row["neighbor_rank"]),
            "event_id": neighbor_event_id,
            "date": str(pd.to_datetime(row["neighbor_date"]).date()),
            "similarity": clean_number(row.get("similarity_for_baseline"), 4),
            "shock_cosine": clean_number(row.get("shock_cosine"), 4),
            "evidence_cosine": clean_number(row.get("evidence_cosine"), 4),
            "semantic_similarity": clean_number(row.get("embedding_cosine_semantic"), 4),
            "macro_mean_abs_z_diff": clean_number(row.get("macro_mean_abs_z_diff"), 4),
            "statement_excerpt": neighbor_statement,
            "previous_statement_excerpt": neighbor_previous,
            "shock_evidence": shock_evidence_map(shocks, neighbor_event_id),
            "returns_pct": {
                "SPY": pct(row.get("neighbor_SPY_ret"), 2),
                "QQQ": pct(row.get("neighbor_QQQ_ret"), 2),
                "GLD": pct(row.get("neighbor_GLD_ret"), 2),
                "UUP": pct(row.get("neighbor_UUP_ret"), 2),
            },
        })

    return rows


def load_llm_logic_chain_report() -> dict:
    if not LLM_LOGIC_CHAIN_FILE.exists():
        return {
            "status": "not_generated",
            "content": "",
            "source_file": str(LLM_LOGIC_CHAIN_FILE.relative_to(PROJECT_ROOT)),
            "message": (
                "尚未生成 LLM 逻辑链分析报告。运行 "
                "`python src/app/generate_logic_chain_report.py --model <MODEL_NAME>` "
                "后再执行 `python src/app/build_frontend_data.py`。"
            ),
        }

    return {
        "status": "generated",
        "content": LLM_LOGIC_CHAIN_FILE.read_text(encoding="utf-8"),
        "source_file": str(LLM_LOGIC_CHAIN_FILE.relative_to(PROJECT_ROOT)),
        "message": "已加载 LLM 生成的 RAG 逻辑链分析报告。",
    }


def build_rag_logic(similar_cases: list[dict]) -> dict:
    return {
        "title": "RAG 历史案例检索逻辑链",
        "method_summary": (
            "当前事件先被表示为政策 shock 数值向量、shock evidence 文本、声明语义向量和宏观市场状态；"
            "检索阶段在历史 FOMC 事件中寻找这些维度同时相近的案例，再将相似案例的资产收益分布转化为 case-memory 特征。"
        ),
        "retrieval_signals": [
            {
                "name": "shock_cosine",
                "meaning": "当前事件与历史事件在五类政策冲击向量上的余弦相似度。",
            },
            {
                "name": "evidence_cosine",
                "meaning": "当前 shock evidence 句与历史 evidence 文本的语义相似度。",
            },
            {
                "name": "embedding_cosine_semantic",
                "meaning": "FOMC 声明文本整体语义相似度。",
            },
            {
                "name": "macro_mean_abs_z_diff",
                "meaning": "宏观市场状态的平均标准化距离，数值越低代表宏观状态越接近。",
            },
            {
                "name": "similarity_for_baseline",
                "meaning": "综合相似度，用于排序并计算相似案例加权收益。",
            },
        ],
        "case_memory_features": [
            "case_pred_{asset}_ret：相似案例加权平均历史收益",
            "case_up_prob_{asset}：相似案例中该资产上涨的加权概率",
            "case_std_{asset}：相似案例收益离散度",
            "case_direction_agreement_{asset}：相似案例方向一致性",
            "case_avg_similarity / case_max_similarity / case_similarity_std：案例集合相似度结构",
        ],
        "fusion_usage": (
            "hgbdt/fusion 不直接把相似案例文本写入预测结论，而是把上述 case-memory 数值特征与宏观变量、shock 主效应、"
            "shock 交互项一起输入 HistGradientBoosting 模型，生成每个资产的方向概率、收益幅度和 90% 预测区间。"
        ),
        "current_case_reading": [
            (
                f"Top {case['rank']} 历史案例 {case['event_id']}：综合相似度 {case['similarity']}，"
                f"shock 相似度 {case['shock_cosine']}，evidence 相似度 {case['evidence_cosine']}，"
                f"宏观距离 {case['macro_mean_abs_z_diff']}。"
            )
            for case in similar_cases
        ],
        "interpretation_boundary": (
            "由于检索本身已经使用 shock 信息，rag/case-memory 不是完全不含 shock 的对照；"
            "它解释的是“与当前政策冲击和宏观状态相似的历史事件，其后资产反应如何”。"
        ),
    }


def build_evaluation(eval_df: pd.DataFrame, segment_df: pd.DataFrame) -> dict:
    eval_df = eval_df.copy()
    eval_df["model"] = eval_df["model"].map(normalize_model_name)
    fusion = eval_df[eval_df["model"] == "fusion"]

    by_asset = []
    for _, row in fusion.sort_values("asset_target").iterrows():
        target = str(row["asset_target"])
        by_asset.append({
            "asset": TARGET_LABELS.get(target, {"asset": target})["asset"],
            "n_test": int(row["n_test"]),
            "direction_accuracy": clean_number(row["direction_accuracy"], 4),
            "balanced_direction_accuracy": clean_number(row["balanced_direction_accuracy"], 4),
            "MAE": clean_number(row["MAE"], 5),
            "RMSE": clean_number(row["RMSE"], 5),
            "coverage_90": clean_number(row["interval_90pct_coverage"], 4),
            "avg_interval_width": clean_number(row["interval_90pct_avg_width"], 5),
        })

    summary = {
        "model": "hgbdt/fusion",
        "direction_accuracy": clean_number(fusion["direction_accuracy"].mean(), 4),
        "balanced_direction_accuracy": clean_number(
            fusion["balanced_direction_accuracy"].mean(), 4
        ),
        "MAE": clean_number(fusion["MAE"].mean(), 5),
        "RMSE": clean_number(fusion["RMSE"].mean(), 5),
        "coverage_90": clean_number(fusion["interval_90pct_coverage"].mean(), 4),
        "avg_interval_width": clean_number(fusion["interval_90pct_avg_width"].mean(), 5),
    }

    segment_df = segment_df.copy()
    segment_df["model"] = segment_df["model"].map(normalize_model_name)
    segment_rows = []
    segment_col = "time_segment" if "time_segment" in segment_df.columns else "segment"
    for _, row in segment_df[segment_df["model"] == "fusion"].iterrows():
        segment_rows.append({
            "segment": str(row[segment_col]),
            "asset": str(row["asset_target"]).replace("_ret", ""),
            "n_test": int(row["n_test"]),
            "direction_accuracy": clean_number(row["direction_accuracy"], 4),
            "MAE": clean_number(row["MAE"], 5),
            "coverage_90": clean_number(row["interval_90pct_coverage"], 4),
        })

    return {
        "summary": summary,
        "by_asset": by_asset,
        "segments": segment_rows,
    }


def build_tuned_params(params_df: pd.DataFrame) -> dict:
    if params_df.empty:
        return {}

    params_df = params_df[params_df["model_family"] == "hgbdt"].copy()
    result: dict[str, dict] = {}

    for _, row in params_df.iterrows():
        target = str(row["target"])
        task = str(row["task"])
        result.setdefault(target, {})[task] = {
            "selection_metric": str(row["selection_metric"]),
            "params": json.loads(row["params"]),
        }

    return result


def build_report_contract() -> dict:
    return {
        "required_inputs": [
            "user_question",
            "current_fomc_event",
            "policy_shock_vector",
            "historical_similar_cases",
            "rag_retrieval_logic",
            "llm_logic_chain_report",
            "multi_asset_predictions",
            "quantitative_metrics",
            "model_evaluation",
            "risk_disclosures",
        ],
        "report_sections": [
            "问题理解",
            "核心预测结论",
            "多资产量化预测表",
            "政策冲击分解",
            "预测逻辑链",
            "历史相似案例支撑",
            "不确定性、风险因素和模型边界",
        ],
        "generation_rules": [
            "只能依据结构化输入、模型输出、相似案例原文摘录和 evidence 句生成解释。",
            "不得编造 FOMC 表述、资产收益、宏观数据、相似案例或模型指标。",
            "若证据不足，必须明确写出证据不足，而不是补充外部推测。",
            "所有方向、幅度、区间和置信度必须与 multi_asset_predictions 一致。",
            "报告必须包含模型边界说明，且不得写成投资建议。",
        ],
    }


def main() -> int:
    preds = pd.read_csv(PREDICTIONS_FILE)
    eval_df = pd.read_csv(EVALUATION_FILE)
    segment_df = pd.read_csv(SEGMENT_EVALUATION_FILE)
    panel = pd.read_excel(PANEL_FILE)
    shocks = pd.read_csv(SHOCK_FILE)
    retrieval = pd.read_csv(RETRIEVAL_FILE)
    params = pd.read_csv(TUNED_PARAMS_FILE) if TUNED_PARAMS_FILE.exists() else pd.DataFrame()
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

    event_id = latest_event_id(preds)
    current_event = build_current_event(panel, event_id)
    predictions = build_predictions(preds, event_id)
    shock_vector = build_shock_vector(shocks, event_id)
    similar_cases = build_similar_cases(retrieval, panel, shocks, event_id)
    evaluation = build_evaluation(eval_df, segment_df)
    rag_logic = build_rag_logic(similar_cases)

    data = {
        "metadata": {
            "title": "FOMC 多资产预测用户报告工作台",
            "model_family": "hgbdt",
            "feature_set": "fusion",
            "model_label": "hgbdt/fusion",
            "parameter_source": "baseline_tuning_20260525_221743/baseline_best_params.csv",
            "experiment_name": config["experiment_name"],
            "experiment_created_at": config["created_at"],
            "generated_from": str(EXPERIMENT_DIR.relative_to(PROJECT_ROOT)),
        },
        "default_user_question": "本次 FOMC 事件后，SPY、QQQ、GLD 和 UUP 的短期收益方向和风险如何？",
        "current_fomc_event": current_event,
        "policy_shock_vector": shock_vector,
        "historical_similar_cases": similar_cases,
        "rag_retrieval_logic": rag_logic,
        "llm_logic_chain_report": load_llm_logic_chain_report(),
        "multi_asset_predictions": predictions,
        "model_evaluation": evaluation,
        "tuned_parameters": build_tuned_params(params),
        "risk_disclosures": [
            "本页面用于研究展示，不构成投资建议。",
            "hgbdt/fusion 是基于历史 FOMC 事件的监督学习模型，无法保证未来事件符合历史分布。",
            "90% 区间来自滚动 conformal calibration，极端市场状态下可能低估尾部风险。",
            "RAG case-memory 已包含 shock-aware 检索信息，不能解释为完全独立于 shock 的纯文本检索。",
        ],
        "report_contract": build_report_contract(),
        "materials": {
            "research_report_md": str(REPORT_FILE.relative_to(PROJECT_ROOT)),
            "frontend_readme": "src/frontend/fomc_report_app/README.md",
        },
    }

    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    out = FRONTEND_DIR / "app_data.js"
    out.write_text(
        "window.FOMC_REPORT_DATA = "
        + json.dumps(data, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
