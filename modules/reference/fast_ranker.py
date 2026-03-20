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


def fast_rank(context: str, keywords: list[str], candidates: list[Paper], top_k: int = 3) -> list[Paper]:
    """基于关键词重叠度 + 被引量的快速排序

    评分 = 关键词匹配得分(0-70) + 被引量得分(0-20) + 摘要匹配得分(0-10)
    """
    if not candidates:
        return []

    context_tokens = _tokenize(context)
    keyword_tokens = set()
    for kw in keywords:
        keyword_tokens.update(_tokenize(kw))

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

        # 核心期刊加分 (0-15分)
        if is_core_journal(p.journal or ""):
            score += 15

        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_k]]
