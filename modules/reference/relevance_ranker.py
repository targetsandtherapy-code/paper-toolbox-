"""相关性排序模块 — 使用 LLM 对候选文献与段落内容打分"""
import json
from openai import OpenAI
from modules.reference.searcher.base import Paper
from modules.reference.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from modules.reference.core_journals import is_core_journal


class RelevanceRanker:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def rank(self, context: str, claim: str, candidates: list[Paper], top_k: int = 3,
             paper_title: str = "", min_score: int = 4) -> list[Paper]:
        if not candidates:
            return []

        if len(candidates) <= top_k:
            return candidates

        candidates_text = ""
        for i, p in enumerate(candidates):
            abstract_preview = (p.abstract or "无摘要")[:150]
            core_tag = "★核心期刊" if is_core_journal(p.journal or "") else "普通期刊"
            candidates_text += (
                f"\n{i+1}. 标题: {p.title}"
                f"\n   摘要: {abstract_preview}"
                f"\n   期刊: {p.journal or 'N/A'} [{core_tag}] | 年份: {p.year} | 被引: {p.citation_count or 0}\n"
            )

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
- 8-10分: 论文直接研究该论点涉及的核心变量/概念/方法，属于实证研究或系统综述
- 5-7分: 论文研究领域相同，且涉及该论点的部分关键概念（实证研究）
- 3-4分: 仅领域相关，但未涉及该论点的核心概念
- 1-2分: 与该具体论点无实质关联
- 0分: 教学论文、教材编写、课程设计、综述教材章节等非研究性论文，一律给0分

重要排除规则（以下论文必须给0分）：
- 标题含"教学""课程""教材""教育改革"等的教学类论文
- 研究对象完全不同的论文（如该论点关于护士，但论文研究的是学生/教师/银行员工等非医护人员）
- 预印本(preprint)中无摘要且标题模糊的论文

期刊质量加分：
- ★核心期刊：+2 分（上限10分）
- 普通期刊：不加分
- 相关性仍是第一优先级

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
            return [p for s, p in scored[:top_k] if s >= min_score]

        except Exception as e:
            print(f"[RelevanceRanker] 排序失败，返回原始顺序: {e}")
            return candidates[:top_k]
