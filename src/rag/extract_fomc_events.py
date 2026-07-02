#!/usr/bin/env python3
"""
从项目本地 data/raw/data_for_text_diff.xlsx 抽取任务一所需列，
写入 data/interim/fomc_events.csv。

Excel 列 → 输出列：
  event_id              → event_id
  date                  → meeting_date
  meeting_type          → document_type
  statement_text        → statement_text
  previous_statement_text → previous_statement_text

默认源文件：项目根目录下的 data/raw/data_for_text_diff.xlsx。
读取 .xlsx 需要 openpyxl: pip install openpyxl
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "raw" / "data_for_text_diff.xlsx"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "interim" / "fomc_events.csv"

# 输出 CSV 列顺序（与 run_batch.py 输入一致）
OUTPUT_COLUMNS = [
    "event_id",
    "meeting_date",
    "document_type",
    "statement_text",
    "previous_statement_text",
]

# Excel 表头列名 → 输出列名
COLUMN_RENAME = {
    "event_id": "event_id",
    "date": "meeting_date",
    "meeting_type": "document_type",
    "statement_text": "statement_text",
    "previous_statement_text": "previous_statement_text",
}

REQUIRED_EXCEL_COLS = list(COLUMN_RENAME.keys())


def read_excel_source(path: Path, sheet_name: str | int = 0) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")

def main() -> None:
    parser = argparse.ArgumentParser(description="从 data/raw/data_for_text_diff.xlsx 抽取字段到 data/interim/fomc_events.csv")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help=f"Excel 路径（默认: {DEFAULT_SOURCE}）")
    parser.add_argument("--sheet", default=0, help="工作表名或索引（默认第一张表）")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出 CSV")
    args = parser.parse_args()

    src = args.source
    if not src.is_file():
        raise SystemExit(f"源文件不存在: {src.resolve()}\n" f"请将 data_for_text_diff.xlsx 放在: {DEFAULT_SOURCE.parent}")

    df = read_excel_source(src, sheet_name=args.sheet)
    missing = set(REQUIRED_EXCEL_COLS) - set(df.columns)
    if missing:
        raise SystemExit(f"Excel 缺少列: {sorted(missing)}；需要列: {REQUIRED_EXCEL_COLS}；当前列: {list(df.columns)}")

    out = df[REQUIRED_EXCEL_COLS].rename(columns=COLUMN_RENAME)
    out = out[OUTPUT_COLUMNS]
    n_prev_na = out["previous_statement_text"].isna().sum()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8")

    print(f"源文件: {src.resolve()}")
    print(f"输出:   {args.output.resolve()}")
    print(f"行数:   {len(out)}")
    print(f"列:     {OUTPUT_COLUMNS}")
    print(f"previous_statement_text 缺失行数: {int(n_prev_na)}")


if __name__ == "__main__":
    main()
