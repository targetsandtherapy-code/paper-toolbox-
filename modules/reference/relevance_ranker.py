"""相关性排序模块 — 使用 LLM 对候选文献与段落内容打分"""
import json
from openai import OpenAI
from modules.reference.searcher.base import Paper
from modules.reference.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


class RelevanceRanker:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def rank(self, context: str, claim: str, candidates: list[Paper], top_k: int = 3, paper_title: str = "") -> list[Paper]:
        if not candidates:
            return []

        if len(candidates) <= top_k:
            return candidates

        candidates_text = ""
        for i, p in enumerate(candidates):
            abstract_preview = (p.abstract or "无摘要")[:150]
            candidates_text += f"\n{i+1}. 标题: {p.title}\n   摘要: {abstract_preview}\n   期刊: {p.journal or 'N/A'} | 年份: {p.year} | 被引: {p.citation_count or 0}\n"

        title_hint = f"\n本论文标题：{paper_title}" if paper_title else ""
        prompt = f"""你是学术论文引用匹配专家。请严格评估以下候选文献与论文段落中特定论点的相关性。
{title_hint}
论文段落上下文：
{context}

该引用需要支撑的具体论点：
{claim}

候选文献：
{candidates_text}

评分规则（请严格执行，宁低勿高）：
- 8-10分: 论文直接研究该论点涉及的核心变量/概念/方法，可作为直接引用依据
- 5-7分: 论文研究领域相同，且涉及该论点的部分关键概念
- 3-4分: 仅领域相关，但未涉及该论点的核心概念
- 1-2分: 与该具体论点无实质关联（即使同属大领域也应低分）

注意：只看是否与上述"具体论点"相关，不要因为论文看起来学术质量高就给高分。一篇顶刊论文如果研究内容与该论点无关，也应给 1-2 分。

请严格按以下 JSON 格式返回（不要添加其他文字）：
{{
  "rankings": [
    {{"index": 1, "score": 9, "reason": "简短理由"}},
    {{"index": 2, "score": 5, "reason": "简短理由"}}
  ]
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是学术论文引用匹配专家，擅长评估文献与论文段落的相关性。只返回 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )

            content = response.choices[0].message.content.strip()
            data = json.loads(content)
            rankings = data.get("rankings", [])

            score_map = {}
            for r in rankings:
                idx = r.get("index", 0)
                score = r.get("score", 0)
                if 1 <= idx <= len(candidates):
                    score_map[idx - 1] = score

            scored = []
            for i, p in enumerate(candidates):
                scored.append((score_map.get(i, 0), p))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [p for s, p in scored[:top_k] if s >= 4]

        except Exception as e:
            print(f"[RelevanceRanker] 排序失败，返回原始顺序: {e}")
            return candidates[:top_k]
