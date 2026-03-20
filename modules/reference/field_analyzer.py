"""领域分析器 — 根据论文标题识别学科领域，推荐中英文核心期刊"""
import json
import logging
from openai import OpenAI
from modules.reference.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL

logger = logging.getLogger(__name__)


class FieldAnalyzer:
    def __init__(self, api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL, model=QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self._cache: dict[str, dict] = {}

    def analyze(self, paper_title: str) -> dict:
        """根据论文标题分析学科领域，返回推荐的核心期刊列表。

        Returns:
            {
                "field": "护理学/心理学/...",
                "subfields": ["正念干预", "职业健康", ...],
                "cn_core_journals": ["中华护理杂志", ...],
                "en_core_journals": ["Journal of Advanced Nursing", ...],
            }
        """
        if not paper_title:
            return {"field": "", "subfields": [], "cn_core_journals": [], "en_core_journals": []}

        cache_key = paper_title.strip()[:60]
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt = f"""你是学术期刊专家。根据以下论文标题，分析其所属学科领域，并推荐该领域最权威的核心期刊。

论文标题：{paper_title}

请返回 JSON 格式：
{{
  "field": "主学科（如：护理学、心理学、临床医学等）",
  "subfields": ["子领域1", "子领域2", "子领域3"],
  "cn_core_journals": [
    "推荐15-20个中文核心期刊名称（北大核心/CSSCI/CSCD/科技核心），按权威性排序"
  ],
  "en_core_journals": [
    "推荐15-20个英文SCI/SSCI期刊名称，按影响因子排序"
  ]
}}

要求：
1. 中文期刊必须是真实存在的北大核心、CSSCI、CSCD或科技核心期刊
2. 英文期刊必须是真实存在的SCI或SSCI收录期刊
3. 期刊要与论文的具体研究领域高度相关（不是泛泛的大类期刊）
4. 优先推荐该细分领域的顶级期刊"""

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是学术期刊专家，熟悉中英文核心期刊。只返回 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            content = resp.choices[0].message.content.strip()
            data = json.loads(content)
            result = {
                "field": data.get("field", ""),
                "subfields": data.get("subfields", []),
                "cn_core_journals": data.get("cn_core_journals", []),
                "en_core_journals": data.get("en_core_journals", []),
            }
            self._cache[cache_key] = result
            logger.info("[FieldAnalyzer] 领域: %s, 推荐中文核心 %d 个, 英文核心 %d 个",
                        result["field"], len(result["cn_core_journals"]), len(result["en_core_journals"]))
            return result
        except Exception as e:
            logger.warning("[FieldAnalyzer] 分析失败: %s", e)
            return {"field": "", "subfields": [], "cn_core_journals": [], "en_core_journals": []}


def build_journal_set(field_result: dict) -> tuple[set[str], set[str]]:
    """从领域分析结果构建中英文核心期刊集合（模糊匹配用）。"""
    cn_set = set()
    for j in field_result.get("cn_core_journals", []):
        cn_set.add(j.strip())
    en_set = set()
    for j in field_result.get("en_core_journals", []):
        en_set.add(j.strip().lower())
    return cn_set, en_set


def is_field_core_journal(journal_name: str, cn_cores: set[str], en_cores: set[str]) -> bool:
    """检查期刊是否在领域推荐的核心期刊中（模糊匹配）。"""
    if not journal_name:
        return False
    name = journal_name.strip()
    if name in cn_cores:
        return True
    name_lower = name.lower()
    if name_lower in en_cores:
        return True
    for core in cn_cores:
        if core in name or name in core:
            return True
    for core in en_cores:
        if core in name_lower or name_lower in core:
            return True
    return False
