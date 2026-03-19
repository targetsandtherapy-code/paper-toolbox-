"""开题报告生成模块"""
import json
from openai import OpenAI
from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


class ProposalGenerator:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(self, title: str, field: str = "", method: str = "",
                 paper_type: str = "硕士论文", extra: str = "") -> dict:
        prompt = f"""你是学术论文开题报告写作专家。请为以下研究题目生成一份详细的开题报告。

论文标题：{title}
论文类型：{paper_type}
{f"学科领域：{field}" if field else ""}
{f"研究方法：{method}" if method else ""}
{f"额外要求：{extra}" if extra else ""}

请生成包含以下部分的开题报告：

1. 选题背景与意义（研究背景、理论意义、实践意义）
2. 国内外研究现状（国外研究现状、国内研究现状、研究述评）
3. 研究目标与内容（研究目标、研究内容、拟解决的关键问题）
4. 研究方法与技术路线（研究方法、技术路线、实施方案）
5. 研究创新点
6. 研究进度安排（按学期/月份规划）
7. 参考文献方向建议

请严格按以下 JSON 格式返回：
{{
  "title": "论文标题",
  "sections": [
    {{
      "heading": "一、选题背景与意义",
      "subsections": [
        {{"subheading": "（一）研究背景", "content": "详细内容..."}},
        {{"subheading": "（二）理论意义", "content": "详细内容..."}},
        {{"subheading": "（三）实践意义", "content": "详细内容..."}}
      ]
    }}
  ],
  "timeline": [
    {{"period": "第1-2个月", "task": "文献综述与理论框架搭建"}},
    {{"period": "第3-4个月", "task": "研究设计与数据收集"}}
  ],
  "innovations": ["创新点1", "创新点2", "创新点3"],
  "reference_directions": ["推荐检索的文献方向1", "推荐检索的文献方向2"]
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是学术论文开题报告写作专家，请生成详细的开题报告内容。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)
