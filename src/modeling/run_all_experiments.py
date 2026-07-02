#!/usr/bin/env python3
"""批量实验的统一入口。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_FAMILIES = ["ridge", "lasso", "elasticnet", "hgbdt", "xgboost"]


def main() -> int:
    script = PROJECT_ROOT / "src" / "modeling" / "modeling.py"

    for model_family in MODEL_FAMILIES:
        cmd = [sys.executable, str(script), "--model-family", model_family]
        print("\n" + "=" * 80)
        print(f"Running model_family={model_family}")
        print("Command:", " ".join(cmd))
        print("=" * 80)

        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            print(f"\nExperiment failed for model_family={model_family}", file=sys.stderr)
            return result.returncode

    print("\nAll experiments finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
