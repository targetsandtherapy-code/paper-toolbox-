"""论文审稿助手 — 逐段分析论文的逻辑、论述、用词问题"""
import json
from openai import OpenAI
from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


class PaperReviewer:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def review_paragraph(self, paragraph: str, context: str = "", paper_title: str = "") -> dict:
        context_hint = f"\n论文标题：{paper_title}" if paper_title else ""
        context_hint += f"\n段落上下文：{context[:300]}" if context else ""

        prompt = f"""你是严格的学术论文审稿专家。请对以下论文段落进行详细审阅。
{context_hint}

待审阅段落：
{paragraph}

请从以下维度逐一检查：
1. 逻辑性：论点之间是否有逻辑跳跃、因果关系是否成立
2. 论述充分性：论点是否有足够的论据支撑、是否需要补充
3. 学术规范：用语是否规范、是否有口语化表达、主观判断是否有依据
4. 引用规范：引用是否充分、是否缺少必要引用
5. 语言表达：是否有语病、表述不清、用词不当

请严格按以下 JSON 格式返回：
{{
  "overall_score": 8,
  "issues": [
    {{
      "type": "逻辑问题",
      "severity": "严重",
      "location": "第X句",
      "description": "问题描述",
      "suggestion": "修改建议"
    }}
  ],
  "strengths": ["优点1", "优点2"],
  "overall_comment": "总体评价（2-3句话）"
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是严格的学术论文审稿专家。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)

    def review_structure(self, paragraphs: list[str], paper_title: str = "") -> dict:
        text_preview = "\n\n".join(f"[段落{i+1}] {p[:100]}..." for i, p in enumerate(paragraphs[:20]))

        prompt = f"""你是学术论文结构审查专家。请审查以下论文的整体结构。

论文标题：{paper_title or '未提供'}
段落概览（共{len(paragraphs)}段）：
{text_preview}

请从以下维度评估：
1. 整体结构是否完整（是否包含引言、文献综述、方法、结果、讨论、结论等）
2. 各部分篇幅是否合理
3. 论文逻辑链是否连贯
4. 是否存在明显的结构缺陷

请严格按以下 JSON 格式返回：
{{
  "structure_score": 7,
  "detected_sections": ["引言", "文献综述", "研究方法", "结果分析", "讨论", "结论"],
  "missing_sections": ["可能缺少的部分"],
  "structure_issues": [
    {{"issue": "问题描述", "suggestion": "建议"}}
  ],
  "overall_assessment": "整体结构评价（3-5句话）"
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是学术论文结构审查专家。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)
