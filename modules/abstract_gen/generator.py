"""摘要生成模块 — 使用 LLM 生成中英文学术摘要"""
import json
from openai import OpenAI
from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


class AbstractGenerator:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(self, content: str, title: str = "", max_words_cn: int = 300, max_words_en: int = 250) -> dict:
        title_hint = f"论文标题：{title}\n" if title else ""
        prompt = f"""{title_hint}以下是论文的主要内容（可能是全文或核心章节摘录）：

{content[:6000]}

请生成符合学术规范的中英文摘要，要求：

1. 中文摘要：
   - 结构：目的、方法、结果、结论（四要素，不需要写标签）
   - 字数：{max_words_cn}字以内
   - 语言：学术正式用语，第三人称
   - 不要出现"本文"以外的自称

2. 英文摘要（Abstract）：
   - 与中文摘要内容对应
   - 词数：{max_words_en}词以内
   - 学术英语，被动语态为主

请严格按以下 JSON 格式返回：
{{
  "abstract_cn": "中文摘要内容",
  "abstract_en": "English abstract content",
  "keywords_cn": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
  "keywords_en": ["Keyword 1", "Keyword 2", "Keyword 3", "Keyword 4", "Keyword 5"]
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是学术论文写作专家，擅长撰写规范的中英文摘要。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)
