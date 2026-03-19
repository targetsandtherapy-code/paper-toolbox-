"""大纲生成模块 — 使用 LLM 生成论文结构化大纲"""
import json
from openai import OpenAI
from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


class OutlineGenerator:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(self, title: str, keywords: str = "", paper_type: str = "硕士论文",
                 extra_requirements: str = "") -> dict:
        prompt = f"""你是学术论文写作专家。请为以下论文生成一份详细的结构化大纲。

论文标题：{title}
论文类型：{paper_type}
{f"关键词：{keywords}" if keywords else ""}
{f"额外要求：{extra_requirements}" if extra_requirements else ""}

要求：
1. 大纲必须符合{paper_type}的标准结构
2. 每个章节需包含 2-4 个小节
3. 每个小节需简要说明其内容要点（1-2句话）
4. 确保逻辑连贯，章节之间有递进关系

请严格按以下 JSON 格式返回：
{{
  "title": "论文标题",
  "chapters": [
    {{
      "number": "第一章",
      "title": "绪论",
      "sections": [
        {{
          "number": "1.1",
          "title": "研究背景",
          "description": "阐述该领域的发展现状和存在的问题..."
        }}
      ]
    }}
  ],
  "estimated_word_count": "预计总字数（如3万字）",
  "suggestions": ["写作建议1", "写作建议2"]
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是学术论文写作专家，擅长规划论文结构。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)
