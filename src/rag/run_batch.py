#!/usr/bin/env python3
"""
批量调用 OpenAI 兼容 Chat API（HTTP POST + Beare）
抽取 FOMC 政策冲击。
默认读取 data/interim/fomc_events.csv（或 --input 指定路径），
写出展开后的 data/processed/fomc_policy_shocks.csv。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import unified_diff
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from sentence_align import alignment_to_json_str, build_keyword_cosine_alignment

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "interim" / "fomc_events.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "fomc_policy_shocks.csv"
PROMPT_DIR = PROJECT_ROOT / "src" / "rag" / "prompts"
SYSTEM_PROMPT_PATH = PROMPT_DIR / "system.txt"
USER_TEMPLATE_PATH = PROMPT_DIR / "user_template.txt"

SHOCK_KEYS = [
    "interest_rate_path",
    "inflation_concern",
    "growth_concern",
    "labor_market",
    "financial_stability",
]

MAX_CHARS_PER_STATEMENT = 14_000
MAX_DIFF_LINES = 220


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def unified_diff_strings(prev: str, curr: str) -> tuple[str, str, bool]:
    """
    返回 (完整 unified diff, 注入 prompt 的 diff, prompt 是否因行数被截断)。
    与 prompts/user_template 中 {unified_diff} 一致的是第二个返回值。
    """
    a = (prev or "").splitlines(keepends=True)
    b = (curr or "").splitlines(keepends=True)
    lines = list(
        unified_diff(
            a,
            b,
            fromfile="previous",
            tofile="current",
            lineterm="",
        )
    )
    full = (
        "".join(lines)
        if lines
        else "(no line-level changes detected; texts may be identical or whitespace-only)"
    )
    if len(lines) <= MAX_DIFF_LINES:
        return full, full, False
    head = lines[: MAX_DIFF_LINES - 1]
    head.append(f"... [{len(lines) - MAX_DIFF_LINES + 1} more diff lines truncated]\n")
    prompt = "".join(head)
    return full, prompt, True


def truncate_statement(label: str, text: str) -> tuple[str, bool]:
    """截断文本"""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return "", False
    s = str(text)
    if len(s) <= MAX_CHARS_PER_STATEMENT:
        return s, False
    return s[: MAX_CHARS_PER_STATEMENT] + f"\n\n[{label} TRUNCATED at {MAX_CHARS_PER_STATEMENT} chars]", True


def extract_json_object(raw: str) -> dict[str, Any] | None:
    s = raw.strip()
    # 去除可选的 Markdown 代码块围栏。
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", s, re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # 兜底解析：通过括号计数提取第一个 JSON 对象片段。
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start : i + 1])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    return None
    return None


def normalize_shock(s: dict[str, Any]) -> dict[str, Any]:
    out = dict(s)
    d = str(out.get("direction", "neutral")).lower().strip()
    if d not in ("hawkish", "dovish", "neutral"):
        out["direction"] = "neutral"
    else:
        out["direction"] = d
    try:
        st = int(out.get("strength", 1))
    except (TypeError, ValueError):
        st = 1
    out["strength"] = max(1, min(5, st))
    c = str(out.get("confidence", "low")).lower().strip()
    if c not in ("high", "medium", "low"):
        out["confidence"] = "low"
    else:
        out["confidence"] = c
    out["evidence"] = str(out.get("evidence", "")).strip()
    return out


def coerce_payload(obj: dict[str, Any]) -> None:
    shocks = obj.get("shocks")
    if not isinstance(shocks, dict):
        return
    for k in SHOCK_KEYS:
        s = shocks.get(k)
        if not isinstance(s, dict):
            continue
        st = s.get("strength")
        if isinstance(st, str):
            st = st.strip()
            if st.isdigit():
                s["strength"] = int(st)
            else:
                try:
                    s["strength"] = int(float(st))
                except ValueError:
                    pass


def validate_and_normalize(obj: dict[str, Any], event_id: str) -> tuple[dict[str, Any] | None, str | None]:
    coerce_payload(obj)
    if str(obj.get("event_id")) != str(event_id):
        return None, f"event_id mismatch: got {obj.get('event_id')!r}, expected {event_id!r}"
    shocks = obj.get("shocks")
    if not isinstance(shocks, dict):
        return None, "missing or invalid shocks object"
    errs: list[str] = []
    for k in SHOCK_KEYS:
        if k not in shocks or not isinstance(shocks[k], dict):
            errs.append(f"missing shock {k}")
    if errs:
        return None, "; ".join(errs)
    for k in SHOCK_KEYS:
        shocks[k] = normalize_shock(shocks[k])
    if "text_change_summary" not in obj:
        obj["text_change_summary"] = ""
    elif obj["text_change_summary"] is None:
        obj["text_change_summary"] = ""
    else:
        obj["text_change_summary"] = str(obj["text_change_summary"])
    return obj, None


def flat_row(
    event_id: str,
    meeting_date: Any,
    document_type: Any,
    text_diff_full: str,
    text_diff_for_prompt: str,
    text_diff_prompt_truncated: bool,
    keyword_cosine_alignment: str,
    parsed: dict[str, Any] | None,
    model: str,
    api_error: str | None,
    parse_error: str | None,
    extraction_status: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "event_id": event_id,
        "meeting_date": meeting_date,
        "document_type": document_type,
        "model": model,
        "extraction_status": extraction_status,
        "api_error": api_error or "",
        "parse_error": parse_error or "",
        "text_diff_full": text_diff_full,
        "text_diff_for_prompt": text_diff_for_prompt,
        "text_diff_prompt_truncated": text_diff_prompt_truncated,
        "keyword_cosine_alignment": keyword_cosine_alignment,
        "text_change_summary": "",
    }
    if parsed:
        row["text_change_summary"] = str(parsed.get("text_change_summary", "") or "")
        for key in SHOCK_KEYS:
            s = parsed["shocks"][key]
            prefix = key
            row[f"{prefix}_direction"] = s["direction"]
            row[f"{prefix}_strength"] = s["strength"]
            row[f"{prefix}_confidence"] = s["confidence"]
            row[f"{prefix}_evidence"] = s["evidence"]
    else:
        for key in SHOCK_KEYS:
            row[f"{key}_direction"] = ""
            row[f"{key}_strength"] = ""
            row[f"{key}_confidence"] = ""
            row[f"{key}_evidence"] = ""
    return row


def call_llm(
    messages: list[dict[str, str]],
    model: str,
    api_url: str,
    bearer_token: str,
    max_retries: int,
    temperature: float,
    max_tokens: int,
) -> tuple[str | None, str | None]:
    """
    OpenAI 兼容 POST /v1/chat/completions；请求头、timeout、重试与打印风格与 test.py 对齐。
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token}",
    }
    data = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_err: str | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(api_url, headers=headers, json=data, timeout=(30, 600))
        except requests.RequestException as e:
            last_err = f"request error: {e}"
            print(f"请求异常(第{attempt}次): {e}")
            time.sleep(2)
            continue

        if resp.status_code == 200:
            try:
                text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
            except (KeyError, IndexError, TypeError) as e:
                last_err = f"bad response shape: {e}"
                time.sleep(2)
                continue
            if not text:
                last_err = "empty completion"
                time.sleep(2)
                continue
            return text, None

        last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
        print(f"HTTP {resp.status_code} (第{attempt}次): {resp.text[:500]}")
        if 400 <= resp.status_code < 500 and resp.status_code != 429:
            break
        time.sleep(2)

    return None, last_err


def compute_alignment_json(prev: str, curr: str, min_cosine: float, skip: bool) -> str:
    if skip:
        return json.dumps(
            {"skipped": True, "reason": "--skip-alignment"},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    try:
        obj = build_keyword_cosine_alignment(prev, curr, min_cosine=min_cosine)
        return alignment_to_json_str(obj)
    except ImportError as e:
        return json.dumps(
            {"error": "import_error", "detail": str(e)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except Exception as e:  # noqa: BLE001
        return json.dumps(
            {"error": "alignment_failed", "detail": str(e)},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def write_alignment_appendix(path: Path, rows: list[dict[str, Any]]) -> None:
    """将 keyword_cosine_alignment 展开为 Markdown，便于答辩/附录。"""
    parts: list[str] = [
        "# 关键词筛选 + TF-IDF 余弦句对附录\n\n",
        "对应 CSV 列 `keyword_cosine_alignment` 的易读展开。\n\n---\n",
    ]
    for r in rows:
        eid = r.get("event_id", "")
        parts.append(f"\n## {eid}\n\n")
        raw = r.get("keyword_cosine_alignment") or ""
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parts.append("*(无法解析 JSON)*\n\n")
            continue
        if data.get("skipped"):
            parts.append(f"*(已跳过: {data.get('reason', '')})*\n\n")
            continue
        if data.get("error"):
            parts.append(f"**错误** (`{data.get('error')}`): {data.get('detail', '')}\n\n")
            continue
        parts.append(
            f"- 方法: `{data.get('method')}`，min_cosine={data.get('min_cosine')}，"
            f"句数 prev={data.get('prev_sentence_count')} / curr={data.get('curr_sentence_count')}\n\n"
        )
        for sk in SHOCK_KEYS:
            block = (data.get("by_shock") or {}).get(sk) or {}
            pairs = block.get("matched_pairs") or []
            parts.append(f"### {sk}\n\n")
            parts.append(
                f"- 关键词预览: {block.get('keywords_preview', [])}\n"
                f"- 筛后句数: previous={block.get('prev_filtered_count')}, "
                f"current={block.get('curr_filtered_count')}\n\n"
            )
            for k, p in enumerate(pairs, 1):
                ps = p.get("previous_sentence") or ""
                cs = p.get("current_sentence") or ""
                parts.append(f"- **对 {k}** (cosine={p.get('cosine')})\n")
                parts.append(
                    f"  - 上一稿: {ps[:800]}{'…' if len(ps) > 800 else ''}\n"
                    f"  - 当前稿: {cs[:800]}{'…' if len(cs) > 800 else ''}\n\n"
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")


def process_row(
    args_tuple: tuple[Any, ...],
) -> dict[str, Any]:
    (
        row,
        system_prompt,
        user_template,
        model,
        max_retries,
        api_url,
        bearer_token,
        temperature,
        max_tokens,
        dry_run,
        min_cosine,
        skip_alignment,
    ) = args_tuple
    event_id = str(row["event_id"])
    meeting_date = row.get("meeting_date", "")
    document_type = row.get("document_type", "")
    prev_raw = row.get("previous_statement_text", "")
    curr_raw = row.get("statement_text", "")

    prev, _ = truncate_statement("PREVIOUS", prev_raw)
    curr, _ = truncate_statement("CURRENT", curr_raw)
    text_diff_full, text_diff_for_prompt, text_diff_prompt_truncated = unified_diff_strings(
        prev, curr
    )
    align_json = compute_alignment_json(prev, curr, min_cosine, skip_alignment)

    user_content = user_template.format(
        event_id=event_id,
        meeting_date=meeting_date,
        document_type=document_type,
        unified_diff=text_diff_for_prompt,
        previous_statement_text=prev or "(empty)",
        statement_text=curr or "(empty)",
    )

    if dry_run:
        return flat_row(
            event_id,
            meeting_date,
            document_type,
            text_diff_full,
            text_diff_for_prompt,
            text_diff_prompt_truncated,
            align_json,
            None,
            model,
            None,
            None,
            "dry_run",
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw, api_err = call_llm(
        messages, model, api_url, bearer_token, max_retries, temperature, max_tokens
    )
    if api_err:
        return flat_row(
            event_id,
            meeting_date,
            document_type,
            text_diff_full,
            text_diff_for_prompt,
            text_diff_prompt_truncated,
            align_json,
            None,
            model,
            api_err,
            None,
            "api_failed",
        )

    obj = extract_json_object(raw or "")
    if not obj:
        return flat_row(
            event_id,
            meeting_date,
            document_type,
            text_diff_full,
            text_diff_for_prompt,
            text_diff_prompt_truncated,
            align_json,
            None,
            model,
            None,
            "json_parse_failed",
            "parse_failed",
        )

    normalized, verr = validate_and_normalize(obj, event_id)
    if verr:
        return flat_row(
            event_id,
            meeting_date,
            document_type,
            text_diff_full,
            text_diff_for_prompt,
            text_diff_prompt_truncated,
            align_json,
            None,
            model,
            None,
            verr,
            "parse_failed",
        )

    return flat_row(
        event_id,
        meeting_date,
        document_type,
        text_diff_full,
        text_diff_for_prompt,
        text_diff_prompt_truncated,
        align_json,
        normalized,
        model,
        None,
        None,
        "ok",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="FOMC policy shock extraction batch runner")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=os.environ.get("SHOCK_MODEL", "deepseek-chat"), help="与网关一致，如 deepseek-chat")
    parser.add_argument("--api-url", default=os.environ.get("CHAT_COMPLETIONS_URL", "https://models.sjtu.edu.cn/api/v1/chat/completions"), help="OpenAI 兼容 chat completions 完整 URL")
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("SHOCK_TEMPERATURE", "0")), help="温度")
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("SHOCK_MAX_TOKENS", "8192")), help="最大 token 数")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("SHOCK_WORKERS", "3")))
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("SHOCK_MAX_RETRIES", "5")))
    parser.add_argument("--limit", type=int, default=0, help="process only first N rows (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="no API calls; empty shock columns")
    parser.add_argument(
        "--min-cosine",
        type=float,
        default=float(os.environ.get("ALIGN_MIN_COSINE", "0.12")),
        help="句级 TF-IDF 余弦匹配阈值（第 10 行显式对齐）",
    )
    parser.add_argument(
        "--skip-alignment",
        action="store_true",
        help="不计算关键词+余弦句对（仅写占位 JSON）",
    )
    parser.add_argument(
        "--alignment-appendix",
        type=Path,
        default=None,
        help="可选：将句对展开写入 Markdown 附录（如 outputs/alignment_appendix.md）",
    )
    args = parser.parse_args()

    bearer_token = (
        os.environ.get("SJTU_API_KEY")
        or os.environ.get("CHAT_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    if not args.dry_run and not bearer_token:
        raise SystemExit(
            "设置 SJTU_API_KEY 或 CHAT_API_KEY 或 OPENAI_API_KEY（Bearer token，不含 'Bearer ' 前缀），与 test.py 所用网关一致；或使用 --dry-run"
        )

    df = pd.read_csv(args.input)
    needed = {"event_id", "statement_text", "previous_statement_text"}
    missing = needed - set(df.columns)
    if missing:
        raise SystemExit(f"Input CSV missing columns: {sorted(missing)}")

    if args.limit and args.limit > 0:
        df = df.head(args.limit)

    system_prompt = load_text(SYSTEM_PROMPT_PATH)
    user_template = load_text(USER_TEMPLATE_PATH)

    work_args = [
        (
            row,
            system_prompt,
            user_template,
            args.model,
            args.max_retries,
            args.api_url,
            bearer_token,
            args.temperature,
            args.max_tokens,
            args.dry_run,
            args.min_cosine,
            args.skip_alignment,
        )
        for _, row in df.iterrows()
    ]

    rows_out: list[dict[str, Any]] = []
    if args.workers <= 1:
        for wa in work_args:
            rows_out.append(process_row(wa))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process_row, wa): wa for wa in work_args}
            for fut in as_completed(futs):
                rows_out.append(fut.result())

    # 按输入文件中的 event_id 顺序恢复原始 CSV 顺序。
    order = {str(e): i for i, e in enumerate(df["event_id"].tolist())}
    rows_out.sort(key=lambda r: order.get(str(r["event_id"]), 10**9))

    out_df = pd.DataFrame(rows_out)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)
    if args.alignment_appendix:
        write_alignment_appendix(args.alignment_appendix, rows_out)
        print(f"Wrote alignment appendix: {args.alignment_appendix}")
    st = out_df["extraction_status"]
    n_ok = int((st == "ok").sum())
    n_dry = int((st == "dry_run").sum())
    n_fail = int(len(out_df) - n_ok - n_dry)
    print(f"Wrote {args.output} rows={len(out_df)} ok={n_ok} dry_run={n_dry} failed={n_fail}")


if __name__ == "__main__":
    main()
