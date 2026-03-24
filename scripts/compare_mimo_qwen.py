"""
一次性对比：通义千问 vs 小米 MiMo（OpenAI 兼容）。
用法（PowerShell）:
  $env:MIMO_API_KEY="你的小米sk"
  $env:QWEN_API_KEY="你的dashscope sk"   # 可选，缺省读 config
  python scripts/compare_mimo_qwen.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 保证能 import config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI

# 与 content_analyzer 相近的短任务（非全文献流水线）
USER_PROMPT = """你是一位学术论文引用分析专家。请根据角标所在句提取关键论点并给出检索词。
本论文标题：正念训练对护理人员隐性缺勤影响机制研究
角标所在句（含角标）：传统的人力资源管理研究主要聚焦于缺勤行为（absenteeism），即员工未按规定到岗工作的现象[3]，并围绕缺勤率的监测与控制开展了大量研究。

请严格按 JSON 返回（不要其它文字）：
{"key_claim":"一句中文","claim_type":"concept_definition|status_quo|mechanism|...","search_query_cn":"2-3个词空格分隔","search_query_en":"2-3 English words"}"""


def timed_chat(
    label: str,
    client: OpenAI,
    model: str,
    extra_body: dict | None = None,
) -> tuple[float, str]:
    kwargs = dict(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你是学术论文引用分析专家。只输出合法 JSON。",
            },
            {"role": "user", "content": USER_PROMPT},
        ],
        temperature=0.3,
    )
    if extra_body:
        kwargs["extra_body"] = extra_body
    try:
        kwargs["response_format"] = {"type": "json_object"}
    except Exception:
        pass

    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(**kwargs)
    except TypeError:
        kwargs.pop("response_format", None)
        resp = client.chat.completions.create(**kwargs)
    elapsed = time.perf_counter() - t0
    text = (resp.choices[0].message.content or "").strip()
    return elapsed, text


def main():
    mimo_key = os.environ.get("MIMO_API_KEY") or os.environ.get("XIAOMI_MIMO_API_KEY")
    if not mimo_key:
        print("请设置环境变量 MIMO_API_KEY 或 XIAOMI_MIMO_API_KEY")
        sys.exit(1)

    try:
        from config import QWEN_API_KEY as cfg_qwen
    except Exception:
        cfg_qwen = ""
    qwen_key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or cfg_qwen

    results = []

    # 小米 MiMo（官方平台 OpenAI 兼容）
    # 控制台文档常见为 api 子域；platform 子域在部分网络会 403
    mimo_base = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
    mimo_models = [
        m.strip()
        for m in os.environ.get("MIMO_MODELS", "mimo-v2-flash,mimo-v2-pro").split(",")
        if m.strip()
    ]
    mc = OpenAI(api_key=mimo_key, base_url=mimo_base)
    for mid in mimo_models:
        try:
            dt, txt = timed_chat(f"MiMo/{mid}", mc, mid, extra_body=None)
            ok = False
            try:
                json.loads(txt)
                ok = True
            except json.JSONDecodeError:
                pass
            results.append(
                {"provider": "mimo", "model": mid, "seconds": round(dt, 3), "json_ok": ok, "preview": txt[:280]}
            )
        except Exception as e:
            results.append({"provider": "mimo", "model": mid, "error": str(e)[:200]})

    # 通义千问
    if qwen_key:
        qwen_base = os.environ.get(
            "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        qmodel = os.environ.get("QWEN_MODEL", "qwen-turbo")
        qc = OpenAI(api_key=qwen_key, base_url=qwen_base)
        try:
            dt, txt = timed_chat(
                f"Qwen/{qmodel}",
                qc,
                qmodel,
                extra_body={"enable_thinking": False},
            )
            ok = False
            try:
                json.loads(txt)
                ok = True
            except json.JSONDecodeError:
                pass
            results.append(
                {
                    "provider": "qwen",
                    "model": qmodel,
                    "seconds": round(dt, 3),
                    "json_ok": ok,
                    "preview": txt[:280],
                }
            )
        except Exception as e:
            results.append({"provider": "qwen", "model": qmodel, "error": str(e)[:200]})
    else:
        results.append({"provider": "qwen", "skipped": "no QWEN_API_KEY"})

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
