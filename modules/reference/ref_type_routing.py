"""角标文献类型 ref_type（J/M/R/D/C/EB/Z）与检索词、语种策略的统配路由。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

REF_TYPES = frozenset({"J", "M", "R", "D", "C", "EB", "Z"})

# P2/P3：按类型的检索画像（轮次、英文库负担）
LIGHT_ENGLISH_REF_TYPES = frozenset({"R", "EB", "D"})
"""降级到英文时仅用 OpenAlex+CrossRef，不请求 PubMed（非生物医学专论）。"""

SKIP_DECOMPOSE_REF_TYPES = frozenset({"R", "EB", "M"})
"""跳过第 2.5 轮论点分解（已有专类检索式或专著不宜硬拆）。"""

SKIP_DOMAIN_FALLBACK_REF_TYPES = frozenset({"R", "EB"})
"""跳过第三轮「领域级」宽泛检索，控制延迟与跑题风险。"""


def use_light_english_sources(ref_rt: str) -> bool:
    return ref_rt in LIGHT_ENGLISH_REF_TYPES


def should_skip_decompose_for_ref_type(ref_rt: str) -> bool:
    return ref_rt in SKIP_DECOMPOSE_REF_TYPES


def should_skip_domain_fallback(ref_rt: str) -> bool:
    return ref_rt in SKIP_DOMAIN_FALLBACK_REF_TYPES


def normalize_ref_type(raw: Optional[str]) -> str:
    if not raw:
        return "J"
    u = str(raw).strip().upper()
    if u in ("EB/OL", "EBOL") or u.startswith("EB"):
        return "EB"
    if u in REF_TYPES:
        return u
    return "J"


def _guillemet_inner(context: str) -> Optional[str]:
    if not context or "《" not in context:
        return None
    m = re.search(r"《([^》]*)》", context)
    return (m.group(1) or "").strip() or None


def infer_ref_type_fallback(
    claim_type: str,
    key_claim: str,
    context_before: str,
) -> str:
    """LLM 返回 Z 或缺失时的启发式。"""
    blob = f"{key_claim or ''} {context_before or ''}"
    if (claim_type or "") == "policy_macro":
        return "R"
    if any(
        k in blob
        for k in (
            "健康中国",
            "医疗卫生队伍",
            "卫生人才",
            "国家战略",
            "规划纲要",
            "白皮书",
        )
    ):
        return "R"
    if any(
        k in blob
        for k in ("学位论文", "硕士论文", "博士论文", "毕业论文", "dissertation", "thesis")
    ):
        return "D"
    if any(k in blob for k in ("会议论文", "学术会议", "研讨会", "proceedings", "conference")):
        return "C"
    if re.search(r"https?://|www\.|\.gov\.cn", blob, re.I):
        return "EB"
    inner = _guillemet_inner(context_before or "")
    if inner:
        if any(k in inner for k in ("纲要", "规划", "通知", "意见", "办法", "白皮书")):
            return "R"
        return "M"
    return "J"


def resolve_ref_type_for_marker(
    analysis,
    context_before: str,
) -> str:
    """综合 LLM ref_type 与启发式，得到最终单字母码。"""
    raw = normalize_ref_type(getattr(analysis, "ref_type", None))
    if raw == "Z":
        return infer_ref_type_fallback(
            getattr(analysis, "claim_type", "") or "",
            getattr(analysis, "key_claim", "") or "",
            context_before or "",
        )
    return raw


def adjust_queries_for_ref_type(
    cn_q: str,
    en_q: str,
    ref_rt: str,
    context_before: str,
) -> Tuple[str, str]:
    """按文献类型轻量改写检索式（在 claim_type enrich 之后调用）。"""
    cn = (cn_q or "").strip()
    en = (en_q or "").strip()
    inner = _guillemet_inner(context_before or "")

    if ref_rt == "M":
        if cn and "专著" not in cn and "图书" not in cn:
            cn = f"{cn} 专著".strip()
        if en and "book" not in en.lower():
            en = f"{en} monograph".strip()
    elif ref_rt == "R":
        if inner and inner not in cn:
            cn = f"{inner} {cn}".strip() if cn else inner
    elif ref_rt == "D":
        if cn and "学位论文" not in cn:
            cn = f"{cn} 学位论文".strip()
        if en and "dissertation" not in en.lower():
            en = f"{en} dissertation".strip()
    elif ref_rt == "C":
        if cn and "会议" not in cn:
            cn = f"{cn} 会议".strip()
        if en and "conference" not in en.lower():
            en = f"{en} conference".strip()
    elif ref_rt == "EB":
        if cn and "网络" not in cn and "电子" not in cn:
            cn = f"{cn} 网络".strip()
    # J 不追加后缀——「论文」「journal article」在知网/CrossRef 只引入噪声
    return cn, en


def lang_attempts_for_ref_type(
    ref_rt: str,
    assigned_lang: str,
    lf_on: bool,
    quote_src: Optional[str],
) -> list[str]:
    """在书名号语种策略之后：R/EB/D 优先中文（再按需英文降级）。"""
    if quote_src == "cn":
        return ["cn"]
    if quote_src == "en":
        return ["en"]
    if ref_rt in ("R", "EB", "D"):
        out = ["cn"]
        if lf_on:
            out.append("en")
        return out
    out = [assigned_lang]
    if lf_on:
        out.append("en" if assigned_lang == "cn" else "cn")
    return out
