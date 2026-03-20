"""角标句中出现《…》时，按 GB/T 7714 使用非期刊类型著录（[EB/OL]、[M] 等），避免强行匹配 [J] 论文。"""
from __future__ import annotations

from typing import Optional

from modules.reference.searcher.base import Paper

try:
    from config import REFERENCE_CANONICAL_POLICY_EB
except Exception:
    REFERENCE_CANONICAL_POLICY_EB = False

def _last_guillemet_inner(context_before: str) -> Optional[str]:
    if not context_before or "《" not in context_before:
        return None
    last_open = context_before.rfind("《")
    if last_open < 0:
        return None
    close = context_before.find("》", last_open)
    if close < 0:
        return None
    inner = context_before[last_open + 1 : close].strip()
    return inner or None


def _looks_like_journal_title(inner: str) -> bool:
    """与学科无关：仅凭题名结构判断「更像连续出版物题名」则仍走论文检索，不误标专著。"""
    s = (inner or "").strip()
    if not s:
        return False
    suffixes = ("杂志", "学报", "期刊", "季刊", "月刊", "双月刊", "周刊", "年刊", "通报", "简报")
    if any(s.endswith(x) for x in suffixes):
        return True
    # 「中国××」类连续出版物常带「中国」+ 领域名 + 杂志/学报，已由后缀覆盖；其余专著、文件、法规书名不判为期刊
    return False


def try_resolve_quoted_citation(
    context_before: str,
    key_claim: str,
    claim_type: str,
) -> Optional[Paper]:
    """书名号《…》优先解析为规范电子文献或专著条目；无法解析则返回 None（继续论文检索）。"""
    ctx = context_before or ""

    if REFERENCE_CANONICAL_POLICY_EB:
        from modules.reference.canonical_policy_refs import try_match_canonical_policy

        eb = try_match_canonical_policy(ctx, key_claim or "", claim_type)
        if eb is not None:
            return eb

    inner = _last_guillemet_inner(ctx)
    if inner is None:
        return None
    if _looks_like_journal_title(inner):
        return None

    # 专著/文件类题名：先按 [M] 著录（出版项可后续人工补全）；题名保留书名号便于与正文一致
    display = f"《{inner}》"
    return Paper(
        title=display,
        authors=[],
        year=None,
        journal=None,
        doi=None,
        abstract=None,
        citation_count=None,
        url=None,
        source="quoted_title_monograph",
        reference_type="M",
        eb_publish_date=None,
        access_date=None,
    )
