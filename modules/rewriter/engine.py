"""降重改写模块 — 在保持语义的前提下改写高重复段落"""
import json
from openai import OpenAI
from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


class Rewriter:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def rewrite(self, text: str, style: str = "学术改写", field: str = "") -> dict:
        style_instructions = {
            "学术改写": "保持学术用语，调整句式结构、同义词替换、段落重组，使表述不同但意思完全一致",
            "精简压缩": "在保留核心信息的前提下精简文字，删除冗余表述",
            "扩展丰富": "在保留原意的基础上增加过渡句、补充解释、丰富论述",
        }

        instruction = style_instructions.get(style, style_instructions["学术改写"])
        field_hint = f"\n学科领域：{field}（请使用该领域的专业术语）" if field else ""

        prompt = f"""你是论文降重改写专家。请改写以下学术文本。
{field_hint}

改写要求：{instruction}

重要规则：
1. 语义必须与原文完全一致，不得改变任何事实或论点
2. 改写幅度要足够大，确保与原文的文字重复率低于 20%
3. 保留原文中的引用角标（如 [1], [2,3]）
4. 保持学术正式用语
5. 不要出现"本文认为"等主观表述（除非原文有）

原文：
{text}

请严格按以下 JSON 格式返回：
{{
  "rewritten": "改写后的文本",
  "changes": ["修改说明1: 将...改为...", "修改说明2: 调整了...的句式"],
  "estimated_similarity": "预估与原文的相似度（如 15%）"
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是论文降重改写专家。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)

    def batch_rewrite(self, paragraphs: list[str], style: str = "学术改写", field: str = "") -> list[dict]:
        results = []
        for p in paragraphs:
            if len(p.strip()) < 20:
                results.append({"rewritten": p, "changes": [], "estimated_similarity": "N/A"})
                continue
            try:
                result = self.rewrite(p, style=style, field=field)
                results.append(result)
            except Exception as e:
                results.append({"rewritten": p, "changes": [f"改写失败: {e}"], "estimated_similarity": "N/A"})
        return results
