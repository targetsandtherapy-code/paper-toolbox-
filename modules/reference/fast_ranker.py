"""快速本地相关性排序 — 无需 LLM 调用，基于关键词匹配 + 被引量 + 核心期刊"""
import re
from modules.reference.searcher.base import Paper
from modules.reference.core_journals import is_core_journal


def _tokenize(text: str) -> set[str]:
    """简单分词：英文按空格，中文按字符"""
    text = text.lower()
    text = re.sub(r'[^\w\u4e00-\u9fff]', ' ', text)
    tokens = set()
    for word in text.split():
        tokens.add(word)
        if len(word) > 2:
            for i in range(len(word) - 1):
                if '\u4e00' <= word[i] <= '\u9fff':
                    tokens.add(word[i:i+2])
    return tokens


def fast_rank(
    context: str,
    keywords: list[str],
    candidates: list[Paper],
    top_k: int = 3,
    field_cores: set[str] | None = None,
    claim: str = "",
) -> list[Paper]:
    """基于关键词重叠度 + 被引量 + 核心期刊的快速排序

    评分 = 关键词匹配得分(0-70) + 被引量得分(0-20) + 摘要匹配得分(0-10) + 期刊加分
    claim: 角标论点全文，参与分词以提升与标题/摘要的语义重叠（轻量「语义」proxy）
    """
    if not candidates:
        return []

    context_tokens = _tokenize(context)
    keyword_tokens = set()
    for kw in keywords:
        keyword_tokens.update(_tokenize(kw))
    if claim:
        keyword_tokens.update(_tokenize(claim))

    all_tokens = context_tokens | keyword_tokens

    max_citations = max((p.citation_count or 0) for p in candidates) or 1

    scored = []
    for p in candidates:
        score = 0.0

        # 标题关键词匹配 (0-40分)
        title_tokens = _tokenize(p.title or "")
        title_overlap = len(title_tokens & all_tokens)
        title_total = max(len(all_tokens), 1)
        score += min(40, (title_overlap / title_total) * 80)

        # 摘要关键词匹配 (0-30分)
        if p.abstract:
            abs_tokens = _tokenize(p.abstract[:300])
            abs_overlap = len(abs_tokens & all_tokens)
            score += min(30, (abs_overlap / title_total) * 60)

        # 被引量得分 (0-20分)
        if p.citation_count:
            score += (p.citation_count / max_citations) * 20

        # 年份新近性 (0-10分)
        if p.year and p.year >= 2022:
            score += min(10, (p.year - 2020) * 2)

        # 领域核心期刊加分 (0-20分)
        j = p.journal or ""
        if field_cores and any(c.lower() in j.lower() or j.lower() in c.lower() for c in field_cores if c):
            score += 20
        elif is_core_journal(j):
            score += 12

        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_k]]
