"""LLM 内容分析模块 — 使用通义千问分析段落并生成搜索关键词"""
import json
from openai import OpenAI
from dataclasses import dataclass
from modules.reference.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


@dataclass
class AnalysisResult:
    marker_id: str
    core_topic: str
    research_method: str
    key_claim: str
    cn_keywords: list[str]
    en_keywords: list[str]
    search_query_cn: str
    search_query_en: str


class ContentAnalyzer:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def analyze(self, marker_id: str, paragraph: str, context_before: str = "",
                paper_title: str = "", max_retries: int = 3) -> AnalysisResult:
        title_hint = f"\n本论文标题：{paper_title}" if paper_title else ""
        prompt = f"""你是一位学术论文引用分析专家。请分析以下论文段落中角标[{marker_id}]处引用想要支撑的核心论点。
{title_hint}
论文段落：
{paragraph}

{f"角标前上下文（引用紧跟在这段文字之后）：{context_before}" if context_before else ""}

分析要求：
1. 仔细阅读角标[{marker_id}]紧邻的前文，判断该引用具体要支撑什么论点
2. 关键词要具体到该论点涉及的核心变量/概念，必须能搜到**实证研究论文**（不是教学论文、综述教材）
3. 搜索查询语句用2-3个最核心的词，不要用冷僻术语或人名

关键词生成规则：
- 中文关键词必须是知网能搜到的常用学术术语
- 不要包含人名（如Cooper、Maslach、骆宏等）
- 不要包含具体量表名缩写（如SPS-6、MBI-GS等），改用通俗描述
- 每个关键词2-4个字，不要太长
- 搜索查询用空格分隔2-3个核心词即可

请严格按以下 JSON 格式返回（不要添加任何其他文字）：
{{
  "core_topic": "该引用支撑的核心主题（1句话）",
  "research_method": "涉及的研究方法/技术（如有）",
  "key_claim": "该引用想要证明的关键论点（必须是角标前文字的精确论点）",
  "cn_keywords": ["中文关键词1", "中文关键词2", "中文关键词3", "中文关键词4", "中文关键词5"],
  "en_keywords": ["English keyword 1", "English keyword 2", "English keyword 3", "English keyword 4", "English keyword 5"],
  "search_query_cn": "2-3个核心中文词，空格分隔（如：隐性缺勤 护士 影响因素）",
  "search_query_en": "2-3 core English terms, space separated (e.g., presenteeism nurses burnout)"
}}"""

        import time as _time
        last_err = None
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是学术论文引用分析专家，擅长从论文段落中提取核心论点并生成精准的学术搜索关键词。只返回 JSON，不要返回其他内容。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    extra_body={"enable_thinking": False},
                )

                content = response.choices[0].message.content.strip()
                data = json.loads(content)

                return AnalysisResult(
                    marker_id=marker_id,
                    core_topic=data.get("core_topic", ""),
                    research_method=data.get("research_method", ""),
                    key_claim=data.get("key_claim", ""),
                    cn_keywords=data.get("cn_keywords", []),
                    en_keywords=data.get("en_keywords", []),
                    search_query_cn=data.get("search_query_cn", ""),
                    search_query_en=data.get("search_query_en", ""),
                )
            except json.JSONDecodeError as e:
                print(f"[ContentAnalyzer] JSON 解析失败: {e}")
                raise
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"[ContentAnalyzer] 第{attempt+1}次失败，{wait}s后重试: {e}")
                    _time.sleep(wait)
        print(f"[ContentAnalyzer] {max_retries}次均失败: {last_err}")
        raise last_err

    def broaden_query(self, original: AnalysisResult, paper_title: str = "") -> AnalysisResult:
        """当原始搜索无结果时，用 LLM 生成更宽泛的搜索词。"""
        title_hint = f"\n论文标题：{paper_title}" if paper_title else ""
        prompt = f"""在知网(CNKI)搜索以下论点未找到文献，请生成能在知网搜到结果的替代搜索词。
{title_hint}
原始论点：{original.key_claim}
原始搜索词（搜不到）：{original.search_query_cn}

知网搜索技巧：
- 搜索词要用**日常学术用语**，不要用太专业的术语（如"行为觉察性"改为"行为改变"）
- 去掉所有人名（如"Cooper""骆宏""Maslach"等）
- 去掉具体量表名（如"SPS-6""MBI-GS"等），用通俗描述替代
- 每组搜索词只用2-3个常见中文词，用空格分隔
- 必须包含论文的核心主题词（如"护士"或"护理人员"或"正念"或"隐性缺勤"等）

示例：
- 原始："隐性缺勤 Cooper 正念训练" → 改为："隐性缺勤 护士 影响因素"
- 原始："心理资本量表 骆宏版 中国护理情境" → 改为："护士 心理资本量表 信效度"
- 原始："组织支持感 社会交换理论 员工忠诚度" → 改为："组织支持感 护士 工作投入"

返回 JSON（3组搜索词，从具体到宽泛）：
{{
  "cn_queries": ["搜索词1", "搜索词2", "搜索词3"],
  "en_queries": ["English query 1", "English query 2", "English query 3"],
  "cn_keywords": ["关键词1", "关键词2", "关键词3"],
  "en_keywords": ["keyword1", "keyword2", "keyword3"]
}}"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是学术搜索专家，擅长调整搜索策略。只返回 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            data = json.loads(resp.choices[0].message.content.strip())
            return AnalysisResult(
                marker_id=original.marker_id,
                core_topic=original.core_topic,
                research_method=original.research_method,
                key_claim=original.key_claim,
                cn_keywords=data.get("cn_keywords", original.cn_keywords),
                en_keywords=data.get("en_keywords", original.en_keywords),
                search_query_cn=data.get("cn_queries", [original.search_query_cn])[0],
                search_query_en=data.get("en_queries", [original.search_query_en])[0],
            )
        except Exception:
            return original

    def batch_analyze(self, markers: list[dict], paper_title: str = "") -> list[AnalysisResult]:
        """批量分析多个角标
        markers: [{"id": "1", "paragraph": "...", "context_before": "..."}, ...]
        """
        results = []
        for m in markers:
            try:
                result = self.analyze(
                    marker_id=m["id"],
                    paragraph=m["paragraph"],
                    context_before=m.get("context_before", ""),
                    paper_title=paper_title,
                )
                results.append(result)
            except Exception as e:
                print(f"[ContentAnalyzer] 跳过角标[{m['id']}]: {e}")
        return results
