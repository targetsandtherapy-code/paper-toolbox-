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

    def analyze(self, marker_id: str, paragraph: str, context_before: str = "", paper_title: str = "") -> AnalysisResult:
        title_hint = f"\n本论文标题：{paper_title}" if paper_title else ""
        prompt = f"""你是一位学术论文引用分析专家。请分析以下论文段落中角标[{marker_id}]处引用想要支撑的核心论点。
{title_hint}
论文段落：
{paragraph}

{f"角标前上下文（引用紧跟在这段文字之后）：{context_before}" if context_before else ""}

分析要求：
1. 仔细阅读角标[{marker_id}]紧邻的前文，判断该引用具体要支撑什么论点
2. 关键词需同时兼顾：(a) 论文标题所涉及的研究领域/主题，(b) 该角标处的具体论点
3. 搜索查询语句要尽可能具体，包含该论点涉及的核心概念、变量、方法等，同时限定在论文标题所属的研究领域内

请严格按以下 JSON 格式返回（不要添加任何其他文字）：
{{
  "core_topic": "该引用支撑的核心主题（1句话，既要体现论文领域又要具体到角标处论点）",
  "research_method": "涉及的研究方法/技术（如有）",
  "key_claim": "该引用想要证明的关键论点（必须是角标前文字的精确论点，但需限定在论文研究领域内）",
  "cn_keywords": ["中文关键词1", "中文关键词2", "中文关键词3", "中文关键词4", "中文关键词5"],
  "en_keywords": ["English keyword 1", "English keyword 2", "English keyword 3", "English keyword 4", "English keyword 5"],
  "search_query_cn": "针对该具体论点的中文学术搜索查询（限定在论文研究领域内）",
  "search_query_en": "Specific English academic search query for this exact claim within the paper's domain"
}}"""

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
            print(f"  原始返回: {content[:200]}")
            raise
        except Exception as e:
            print(f"[ContentAnalyzer] 分析失败: {e}")
            raise

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
