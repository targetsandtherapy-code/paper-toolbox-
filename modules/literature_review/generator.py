"""文献综述生成模块 — 检索学术文献 + LLM 聚类总结"""
import json
import sys
from pathlib import Path
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from modules.reference.searcher.crossref import CrossRefSearcher
from modules.reference.searcher.openalex import OpenAlexSearcher
from modules.reference.searcher.base import Paper


class LiteratureReviewGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
        self.model = QWEN_MODEL
        self.crossref = CrossRefSearcher()
        self.openalex = OpenAlexSearcher()

    def search_papers(self, queries: list[str], year_start: int = 2019,
                      year_end: int = 2026, per_query: int = 10, callback=None) -> list[Paper]:
        all_papers = []
        seen_dois = set()

        for q in queries:
            if callback:
                callback(f"搜索: {q}")
            for searcher, name in [(self.openalex, "OpenAlex"), (self.crossref, "CrossRef")]:
                try:
                    papers = searcher.search(q, year_start, year_end, per_query)
                    for p in papers:
                        doi_key = (p.doi or "").lower()
                        if doi_key and doi_key in seen_dois:
                            continue
                        if doi_key:
                            seen_dois.add(doi_key)
                        all_papers.append(p)
                    if callback:
                        callback(f"  {name}: {len(papers)} 篇")
                except Exception:
                    pass

        if callback:
            callback(f"共检索到 {len(all_papers)} 篇文献")
        return all_papers

    def cluster_and_summarize(self, papers: list[Paper], topic: str, callback=None) -> dict:
        papers_text = ""
        for i, p in enumerate(papers[:50]):
            abstract_preview = (p.abstract or "无摘要")[:200]
            papers_text += f"\n{i+1}. {p.title}\n   作者: {', '.join(p.authors[:3])}\n   年份: {p.year} | 期刊: {p.journal or 'N/A'}\n   摘要: {abstract_preview}\n"

        if callback:
            callback("AI 正在分析和聚类文献...")

        prompt = f"""你是学术文献综述写作专家。请基于以下检索到的文献，为研究主题"{topic}"撰写一篇结构化的文献综述。

检索到的文献：
{papers_text}

请完成以下任务：
1. 将文献按研究主题/方向聚类为 3-5 个类别
2. 为每个类别撰写综述段落（每段 200-400 字）
3. 分析研究趋势和不足
4. 总结研究空白和未来方向

请严格按以下 JSON 格式返回：
{{
  "title": "文献综述标题",
  "introduction": "综述开篇引言（100-200字）",
  "clusters": [
    {{
      "theme": "主题类别名称",
      "summary": "该类别的综述文字（200-400字，需要引用具体文献）",
      "key_papers": [1, 5, 12],
      "paper_count": 8
    }}
  ],
  "trends": "研究趋势分析（150-250字）",
  "gaps": "研究空白与不足（150-250字）",
  "future_directions": ["未来研究方向1", "未来研究方向2", "未来研究方向3"],
  "conclusion": "综述结论（100-200字）"
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是学术文献综述写作专家，擅长系统性梳理文献并撰写高质量综述。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )

        if callback:
            callback("综述生成完成")

        content = response.choices[0].message.content.strip()
        return json.loads(content)
