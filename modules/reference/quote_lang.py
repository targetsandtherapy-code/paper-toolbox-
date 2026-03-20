"""角标句中书名号《…》内题名语种，用于限定检索源（中文→知网，英文→英文学术库）。"""
from __future__ import annotations

import re
from typing import Optional


def quoted_title_source_lang(context_before: str) -> Optional[str]:
    """若含《…》，按书名号内汉字与拉丁字母数量对比返回 ``\"cn\"`` | ``\"en\"``，否则 ``None``。"""
    if not context_before or "《" not in context_before or "》" not in context_before:
        return None
    m = re.search(r"《([^》]*)》", context_before)
    if not m:
        return None
    inner = (m.group(1) or "").strip()
    if not inner:
        return None
    han = sum(1 for c in inner if "\u4e00" <= c <= "\u9fff")
    latin = sum(1 for c in inner if ("a" <= c <= "z") or ("A" <= c <= "Z"))
    if han == 0 and latin == 0:
        return None
    return "cn" if han >= latin else "en"
