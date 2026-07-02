#!/usr/bin/env python3
"""为前端生成由 LLM 撰写的 RAG 逻辑链报告。"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from requests.exceptions import ReadTimeout, RequestException

import build_frontend_data as frontend_data


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "src" / "frontend" / "fomc_report_app"
OUT_FILE = FRONTEND_DIR / "llm_logic_chain_report.md"
PROMPT_OUT_FILE = FRONTEND_DIR / "llm_logic_chain_payload.json"

DEFAULT_BASE_URL = "https://models.sjtu.edu.cn/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek-reasoner"


SYSTEM_PROMPT = """你是一名严谨的金融文本事件研究分析师。

你的任务是基于当前 FOMC 文本、政策冲击分解、RAG 检索到的历史事件文本、相似度指标、历史资产反应和 hgbdt/fusion 模型输出，写一篇完整的“RAG 历史案例逻辑链分析报告”。

必须遵守：
1. 只能依据输入 JSON 中的信息写作，不得补充外部宏观背景、新闻、市场观点或未提供的 FOMC 内容。
2. 必须先输出“预测结果”和“政策传导逻辑链”，再输出 RAG 检索事件细节；不得把关键预测结论放到报告后半部分。
3. 必须引用当前事件文本摘录、shock evidence、历史事件文本摘录和相似度指标来解释为什么这些历史事件被检索出来。
4. 必须解释“当前事件 -> shock 分解 -> 政策传导路径 -> RAG 检索信号 -> 历史案例反应 -> case-memory 特征 -> hgbdt/fusion 预测”的链条。
5. 必须说明 RAG case-memory 是 shock-aware 检索结果，不是完全独立于 shock 的纯文本检索。
6. 预测方向和收益幅度必须与输入中的 multi_asset_predictions 一致。
7. 如果历史文本证据不足以支持某个解释，必须明确写“当前输入不足以支持该判断”。
8. 不得输出投资建议，不得使用“必然”“确定”等确定性表达。
9. 使用中文，结构完整，适合研究展示和最终用户报告引用。
10. 严禁在表格中途或句子中途停止。若篇幅不足，压缩历史案例细节和风险讨论，也要完整输出结论、传导链和结尾。
11. 全文建议控制在 2500-3500 个中文字符内，优先保证结构完整，而不是展开所有细节。
"""


def compact_text(value, limit=1200) -> str:
    if pd.isna(value):
        return ""

    text = " ".join(str(value).split())
    return text[:limit] + ("..." if len(text) > limit else "")


def trim_case_for_llm(case: dict, text_limit: int) -> dict:
    trimmed = dict(case)
    trimmed["statement_excerpt"] = compact_text(trimmed.get("statement_excerpt"), text_limit)
    trimmed["previous_statement_excerpt"] = compact_text(
        trimmed.get("previous_statement_excerpt"),
        max(300, text_limit // 2),
    )
    return trimmed


def build_logic_chain_input(
    user_question: str | None = None,
    current_text_limit: int = 1400,
    previous_text_limit: int = 700,
    case_text_limit: int = 900,
    top_k_cases: int = 3,
) -> dict:
    preds = pd.read_csv(frontend_data.PREDICTIONS_FILE)
    eval_df = pd.read_csv(frontend_data.EVALUATION_FILE)
    segment_df = pd.read_csv(frontend_data.SEGMENT_EVALUATION_FILE)
    panel = pd.read_excel(frontend_data.PANEL_FILE)
    shocks = pd.read_csv(frontend_data.SHOCK_FILE)
    retrieval = pd.read_csv(frontend_data.RETRIEVAL_FILE)
    config = json.loads(frontend_data.CONFIG_FILE.read_text(encoding="utf-8"))

    event_id = frontend_data.latest_event_id(preds)
    event_row = panel[panel["event_id"] == event_id].iloc[0]

    current_event = frontend_data.build_current_event(panel, event_id)
    current_event["statement_text"] = compact_text(
        event_row.get("statement_text"),
        current_text_limit,
    )
    current_event["previous_statement_text"] = compact_text(
        event_row.get("previous_statement_text"),
        previous_text_limit,
    )

    shock_vector = frontend_data.build_shock_vector(shocks, event_id)
    similar_cases = frontend_data.build_similar_cases(retrieval, panel, shocks, event_id)
    similar_cases = [
        trim_case_for_llm(case, case_text_limit)
        for case in similar_cases[:top_k_cases]
    ]
    predictions = frontend_data.build_predictions(preds, event_id)
    evaluation = frontend_data.build_evaluation(eval_df, segment_df)
    rag_logic = frontend_data.build_rag_logic(similar_cases)

    return {
        "task": "生成完整 RAG 历史案例逻辑链分析报告",
        "analysis_date": str(date.today()),
        "user_question": user_question or "本次 FOMC 事件后，多资产预测结果如何由政策冲击和历史相似案例共同解释？",
        "model_setting": {
            "model_family": "hgbdt",
            "feature_set": "fusion",
            "experiment_name": config["experiment_name"],
            "prediction_model_note": (
                "hgbdt/fusion 使用宏观市场变量、派生市场状态、shock 主效应、shock 交互项和 RAG case-memory 特征。"
            ),
        },
        "current_fomc_event": current_event,
        "policy_shock_vector": shock_vector,
        "rag_retrieval_logic": rag_logic,
        "historical_similar_cases": similar_cases,
        "multi_asset_predictions": [
            {
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
            }
            for item in predictions
        ],
        "model_evaluation": evaluation,
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
            "报告开头必须明确写出分析日期，并直接使用 analysis_date 字段。",
            "先输出预测结果表，再解释政策传导链和历史案例细节，方法性说明统一放到最后的附录。",
            "必须优先完整回答用户问题，不得在历史案例细节处截断。",
            "核心预测结果表必须展示方向、预测收益和90%区间。",
            "核心预测结果表格不得展示除“资产”“预测方向”“预测收益 (%)”“90% 预测区间 (%)”以外的任何列或额外说明。",
            "历史案例可以压缩分析，但不能省略 RAG 检索依据。",
            "必须引用相似度指标和历史资产收益。",
            "必须说明文本相似点与差异点。",
            "不得比较预测结果与真实事后资产表现，不得写任何事后验证或复盘式分析。",
            "必须说明风险边界，不得给投资建议。",
        ],
    }


def build_messages(payload: dict) -> list[dict]:
    user_prompt = (
        "请根据以下 JSON 输入，围绕 user_question 写一篇完整的 RAG 历史案例逻辑链分析报告。\n\n"
        "输出必须使用 Markdown，必须包含 required_report_structure 中的所有章节。\n"
        "报告开头必须显示分析日期，并直接使用 analysis_date 字段。\n"
        "请严格按以下优先级组织内容：先给多资产预测结果表和一句话核心结论；"
        "该表必须且只能包含“资产”“预测方向”“预测收益 (%)”“90% 预测区间 (%)”四列；"
        "再解释政策冲击如何传导到 SPY、QQQ、GLD、UUP，并分析历史案例的相似点、差异点和风险边界；"
        "方法性的说明（模型如何把传导链转化为预测、RAG 检索依据）统一放到文末附录。\n"
        "不得比较预测结果与真实事后资产表现，也不得写复盘式结论。\n"
        "如果输出长度受限，必须压缩历史案例细节，不得截断预测结果、政策传导链或结论。\n\n"
        "JSON 输入：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def call_llm(
    base_url: str,
    api_key: str | None,
    model: str,
    messages: list[dict],
    timeout: int,
    retries: int,
    max_tokens: int | None,
) -> str:
    headers = {"Content-Type": "application/json"}

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "top_p": 0.9,
        "stream": False,
    }

    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    last_error = None

    for attempt in range(1, retries + 2):
        try:
            print(f"Calling LLM attempt {attempt}/{retries + 1}, timeout={timeout}s...")
            response = requests.post(base_url, headers=headers, json=body, timeout=timeout)
            response.raise_for_status()
            break
        except ReadTimeout as exc:
            last_error = exc
            if attempt > retries:
                raise RuntimeError(
                    "LLM request timed out. Try increasing --timeout, lowering "
                    "--case-text-limit/--current-text-limit, or using --top-k-cases 1."
                ) from exc
            sleep_seconds = min(10, 2 * attempt)
            print(f"Read timed out; retrying in {sleep_seconds}s...")
            time.sleep(sleep_seconds)
        except RequestException:
            raise
    else:
        raise RuntimeError(f"LLM request failed: {last_error}")

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LLM response schema: {data}") from exc


def parse_args():
    parser = argparse.ArgumentParser(
        description="Call an LLM to generate the RAG logic-chain report."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SJTU_API_BASE_URL", DEFAULT_BASE_URL),
        help="Chat completions endpoint.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("SJTU_MODEL", DEFAULT_MODEL),
        help="Model name. Can also be set via SJTU_MODEL.",
    )
    parser.add_argument(
        "--api-key-env",
        default="SJTU_API_KEY",
        help="Environment variable that stores the API key.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only write the request payload, do not call the API.",
    )
    parser.add_argument(
        "--user-question",
        default="",
        help="User question that the logic-chain report should answer.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Read timeout in seconds for the LLM request.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retries after read timeouts.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=5000,
        help="Optional max_tokens sent to the chat completion API.",
    )
    parser.add_argument(
        "--current-text-limit",
        type=int,
        default=1400,
        help="Maximum characters of current FOMC statement text sent to LLM.",
    )
    parser.add_argument(
        "--previous-text-limit",
        type=int,
        default=700,
        help="Maximum characters of previous FOMC statement text sent to LLM.",
    )
    parser.add_argument(
        "--case-text-limit",
        type=int,
        default=900,
        help="Maximum characters of each historical case statement text sent to LLM.",
    )
    parser.add_argument(
        "--top-k-cases",
        type=int,
        default=3,
        help="Number of retrieved historical cases sent to LLM.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.model:
        raise SystemExit("Missing model name. Use --model <MODEL_NAME> or set SJTU_MODEL.")

    payload = build_logic_chain_input(
        user_question=args.user_question,
        current_text_limit=args.current_text_limit,
        previous_text_limit=args.previous_text_limit,
        case_text_limit=args.case_text_limit,
        top_k_cases=args.top_k_cases,
    )
    messages = build_messages(payload)
    prompt_chars = sum(len(m["content"]) for m in messages)
    PROMPT_OUT_FILE.write_text(
        json.dumps(
            {
                "base_url": args.base_url,
                "model": args.model,
                "timeout": args.timeout,
                "retries": args.retries,
                "max_tokens": args.max_tokens,
                "prompt_chars": prompt_chars,
                "messages": messages,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Payload written: {PROMPT_OUT_FILE}")
    print(f"Prompt characters: {prompt_chars}")

    if args.dry_run:
        return 0

    api_key = os.environ.get(args.api_key_env) or os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise SystemExit(
            f"Missing API key. Set {args.api_key_env} or OPENAI_API_KEY before calling the API."
        )

    content = call_llm(
        args.base_url,
        api_key,
        args.model,
        messages,
        timeout=args.timeout,
        retries=args.retries,
        max_tokens=args.max_tokens,
    )
    OUT_FILE.write_text(content.strip() + "\n", encoding="utf-8")
    print(OUT_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
