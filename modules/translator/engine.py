"""学术翻译模块 — 保持术语准确性的中英互译"""
import json
from openai import OpenAI
from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


class AcademicTranslator:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def translate(self, text: str, direction: str = "cn_to_en", field: str = "", glossary: str = "") -> dict:
        if direction == "cn_to_en":
            src_lang, tgt_lang = "中文", "英文"
        else:
            src_lang, tgt_lang = "英文", "中文"

        field_hint = f"\n学科领域：{field}" if field else ""
        glossary_hint = f"\n术语表（请严格使用以下术语翻译）：\n{glossary}" if glossary else ""

        prompt = f"""你是学术论文翻译专家。请将以下{src_lang}学术文本翻译为{tgt_lang}。
{field_hint}{glossary_hint}

翻译要求：
1. 保持学术用语的准确性和专业性
2. {tgt_lang}如果是英文，使用被动语态为主的学术英语风格
3. {tgt_lang}如果是中文，使用规范的学术中文表达
4. 保留原文中的引用标记（如 [1], [2,3]）
5. 专业术语翻译要统一、准确
6. 不要遗漏或添加原文没有的内容

原文：
{text}

请严格按以下 JSON 格式返回：
{{
  "translation": "翻译结果",
  "terminology": [
    {{"source": "原文术语", "target": "翻译术语"}},
    {{"source": "原文术语2", "target": "翻译术语2"}}
  ]
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": f"你是学术论文翻译专家，擅长{src_lang}到{tgt_lang}的学术翻译。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)
