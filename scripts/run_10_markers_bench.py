"""
真实角标小样本：处理前 N 个角标，统计耗时与匹配数。
用法（在项目根 paper-toolbox 下）:
  # 千问（读 config / 环境变量 QWEN_*）
  python scripts/run_10_markers_bench.py --provider qwen

  # 小米 MiMo（需 MIMO_API_KEY）
  python scripts/run_10_markers_bench.py --provider mimo-flash
  python scripts/run_10_markers_bench.py --provider mimo-pro
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--provider",
        choices=["qwen", "mimo-flash", "mimo-pro"],
        default="qwen",
    )
    ap.add_argument("--max-markers", type=int, default=10)
    ap.add_argument(
        "--docx",
        default=r"D:\论文\正念训练对护理人员隐性缺勤影响机制研究(1).docx",
    )
    ap.add_argument(
        "--nursing-hard-scope",
        action="store_true",
        help="启用护理课题专用硬过滤（默认通用模式，不加护士/nurse 限定）",
    )
    args = ap.parse_args()

    if args.provider != "qwen":
        os.environ["QWEN_BASE_URL"] = os.environ.get(
            "MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"
        )
        mk = os.environ.get("MIMO_API_KEY") or os.environ.get("XIAOMI_MIMO_API_KEY")
        if not mk:
            print("请设置 MIMO_API_KEY", file=sys.stderr)
            sys.exit(1)
        os.environ["QWEN_API_KEY"] = mk
        os.environ["QWEN_MODEL"] = (
            "mimo-v2-flash" if args.provider == "mimo-flash" else "mimo-v2-pro"
        )

    sys.path.insert(0, str(ROOT))
    from modules.reference.main import process_paper

    t0 = time.perf_counter()
    refs, md, plain = process_paper(
        args.docx,
        year_start=2020,
        year_end=2026,
        cn_ratio=0.3,
        paper_title="正念训练对护理人员隐性缺勤影响机制研究",
        fast_mode=True,
        max_markers=args.max_markers,
        callback=lambda m: print(m, flush=True),
        nursing_hard_scope=args.nursing_hard_scope,
    )
    elapsed = time.perf_counter() - t0

    out = {
        "provider": args.provider,
        "max_markers": args.max_markers,
        "nursing_hard_scope": args.nursing_hard_scope,
        "matched": len(refs),
        "seconds": round(elapsed, 2),
        "marker_ids": sorted(refs.keys()),
    }
    print("\n=== BENCH ===", flush=True)
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)
    print("\n--- PLAIN (preview) ---\n", plain[:2000], flush=True)


if __name__ == "__main__":
    main()
