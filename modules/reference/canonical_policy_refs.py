"""国家层面权威政策电子文献：与 GB/T 7714 [EB/OL] 著录一致，避免用知网期刊替代国务院文件。"""
from __future__ import annotations

from datetime import date
from typing import Optional

from modules.reference.searcher.base import Paper


def _blob(ctx: str, claim: str) -> str:
    return f"{ctx or ''} {claim or ''}"


def try_match_canonical_policy(
    context_before: str,
    key_claim: str,
    claim_type: str,
) -> Optional[Paper]:
    """若论点与上下文明确指向国务院《“健康中国2030”规划纲要》，返回政府网规范条目。"""
    if claim_type != "policy_macro":
        return None
    t = _blob(context_before, key_claim)
    t_compact = t.replace(" ", "").replace("\u3000", "")
    # 避免仅凭「健康中国」泛表述误命中：须带 2030 规划/纲要语义
    hits_2030 = (
        "健康中国2030" in t_compact
        or "健康中国２０３０" in t_compact
        or ("2030" in t and "健康中国" in t)
    )
    hits_plan = "规划纲要" in t or ("规划" in t and "纲要" in t) or "规划纲要" in t_compact
    if not hits_2030:
        return None
    if not hits_plan and "规划" not in t:
        return None

    today = date.today().isoformat()
    return Paper(
        title="中共中央 国务院印发《“健康中国2030”规划纲要》",
        authors=[],
        year=2016,
        journal="中国政府网",
        doi=None,
        abstract=None,
        citation_count=None,
        url="https://www.gov.cn/zhengce/2016-10/25/content_5124174.htm",
        source="canonical_policy_eb",
        reference_type="EB/OL",
        eb_publish_date="2016-10-25",
        access_date=today,
    )
