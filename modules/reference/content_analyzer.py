"""LLM 内容分析模块 — 使用通义千问分析段落并生成搜索关键词"""
import json
import re
from openai import OpenAI
from dataclasses import dataclass, field
from modules.reference.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from modules.reference.quote_lang import quoted_title_source_lang

CLAIM_TYPES = frozenset(
    {
        "policy_macro",
        "concept_definition",
        "mechanism",
        "status_quo",
        "intervention",
        "review_progress",
    }
)


def infer_claim_type_from_text(key_claim: str, paper_title: str = "") -> str:
    """LLM 未返回 claim_type 时的启发式兜底。"""
    t = f"{key_claim or ''} {paper_title or ''}"
    if any(
        k in t
        for k in (
            "健康中国",
            "医疗卫生队伍",
            "卫生人才",
            "人才强国",
            "卫生强国",
            "战略实施",
            "国家战略",
        )
    ):
        return "policy_macro"
    if any(
        k in t
        for k in (
            "概念",
            "定义",
            "内涵",
            "起源",
            "理论基础",
            "多学科",
            "discipline",
        )
    ):
        return "concept_definition"
    if any(
        k in t
        for k in (
            "中介",
            "调节",
            "链式",
            "路径分析",
            "结构方程",
            "SEM",
            "moderat",
            "mediat",
        )
    ):
        return "mechanism"
    if any(k in t for k in ("干预", "训练", "试验", "随机", "RCT", "正念", "方案")):
        return "intervention"
    if any(k in t for k in ("综述", "进展", "系统评价", "meta", "Meta", "范围综述")):
        return "review_progress"
    return "status_quo"


def _coerce_str_list(val, max_items: int = 16) -> list[str]:
    """JSON 数组或单字符串 → 非空 str 列表。"""
    if val is None:
        return []
    if isinstance(val, str):
        s = val.strip()
        return [s] if s else []
    if isinstance(val, list):
        out: list[str] = []
        for x in val[:max_items]:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    return []


def claim_text_suggests_mechanism(key_claim: str) -> bool:
    """论点出现关系/机制词但 LLM 未标 mechanism 时，强制次要类型为 mechanism。"""
    t = key_claim or ""
    if any(
        k in t
        for k in (
            "中介",
            "调节",
            "链式",
            "路径分析",
            "结构方程",
            "SEM",
            "影响路径",
        )
    ):
        return True
    tl = t.lower()
    return bool(re.search(r"\bmediat(e|ion|ing|or)?\b|\bmoderat(e|ion|or)?\b", tl))


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
    claim_type: str = "status_quo"
    """次要类型；置信度低或与主类并集策略时使用（如 mechanism 与 status_quo 并存）。"""
    secondary_claim_type: str = ""
    """LLM 对主类置信度 0~1；低于 0.7 时建议参考 secondary_claim_type。"""
    claim_confidence: float = 1.0
    ref_type: str = "J"
    """J/M/R/D/C/EB/Z：期刊/专著/报告/学位/会议/网络/不确定（Z 由下游启发式解析）。"""
    ref_type_confidence: float = 0.0
    ref_type_hint: str = ""
    # —— 检索轨道（拟合「被引文献」题名/元数据，供数据库检索；勿写结论性大白话）——
    ref_authors: list[str] = field(default_factory=list)
    ref_title_keywords_cn: list[str] = field(default_factory=list)
    ref_title_keywords_en: list[str] = field(default_factory=list)
    ref_population: list[str] = field(default_factory=list)
    ref_method: list[str] = field(default_factory=list)
    ref_year_hint: str = ""
    ref_journal_hint: str = ""
    recommended_lang: str = "en"
    """LLM 推荐的检索语种：cn=中文文献 en=英文文献。由 LLM 根据角标句判断。"""


class ContentAnalyzer:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def analyze(self, marker_id: str, paragraph: str, context_before: str = "",
                paper_title: str = "", max_retries: int = 3) -> AnalysisResult:
        title_hint = f"本论文标题：{paper_title}\n" if paper_title else ""
        ctx_line = f"角标所在句：{context_before}\n" if context_before else ""
        topic_constraint = ""
        if paper_title:
            topic_constraint = f"""
## 论文主题约束（最高优先级，必须遵守）

本论文的题目是「{paper_title}」。

**硬性规则**：search_query_cn 和 search_query_en 中 **必须** 至少包含一个本论文的核心疾病/人群/领域实体词。
- 从论文标题中提取 1-2 个核心实体词（如疾病名、研究对象、核心变量），将其作为检索词的 **必选项**
- 即使角标句在讨论通用机制（如免疫反应、炎症、血小板、凝血），search_query 也必须加上论文的核心疾病名
- 示例：论文是关于「肺炎支原体」，角标句讨论「血小板聚集」→ search_query_cn 必须是「肺炎支原体 血小板」而不是「血小板 聚集能力 血栓」
- 示例：论文是关于「护士隐性缺勤」，角标句讨论「心理资本」→ search_query_cn 必须是「护士 心理资本 隐性缺勤」而不是「心理资本 组织行为」
- **违反此规则会导致搜索到完全无关的论文（如搜索「血小板 凝血」匹配到兽医学论文），这是不可接受的**
"""

        prompt = f"""{title_hint}{topic_constraint}论文段落（角标[{marker_id}]处需要找到被引文献）：
{paragraph}

{ctx_line}
## 你的任务

角标[{marker_id}]引用了一篇文献。请回答两个问题：
1. **这句话在说什么？**（key_claim，给校验用）
2. **被引的那篇文献，标题大概长什么样？**（给数据库检索用）

## 关键区分：「论点」vs「文献标题」

论文里写的是**结论**，但我们要搜的是**做这个研究的那篇论文**。

| 角标句写的（结论） | 被引文献标题可能像 | 应提取的检索词 |
|---|---|---|
| 护理人员隐性缺勤发生率远高于其他职业群体[5] | Presenteeism among nurses: prevalence and... | presenteeism, nurses, prevalence |
| 康晓菲等研究发现临床护士隐性缺勤与正念水平呈显著负相关[12] | 临床护士隐性缺勤与正念水平的相关性研究 | 康晓菲 隐性缺勤 正念 临床护士 |
| Zhang X等基于TARGET横断面数据考察了护士隐性缺勤[8] | Presenteeism among nurses: TARGET study | Zhang, presenteeism, nurses, TARGET |
| 正念训练能有效降低职业倦怠[15] | Mindfulness-based intervention burnout nurses | mindfulness, intervention, burnout, nurses |
| 全球护士短缺问题日益严峻[1] | Global nursing shortage: a systematic review | nursing shortage, global, workforce |

**禁止**把「发生率远高于」「显著负相关」「日益严峻」这类结论表述当检索词——没有论文标题会这样写。
**应该**写研究主题名词：变量名、人群、方法、数据集名、作者姓。

## 输出字段

**ref_authors**：句中明确写出的作者名，如"康晓菲等"→`["康晓菲"]`，"Zhang X"→`["Zhang X"]`，没有则`[]`
**ref_title_keywords_cn**：被引中文文献标题可能包含的3-6个名词（隐性缺勤、正念、临床护士……）
**ref_title_keywords_en**：被引英文文献标题可能包含的3-6个词（presenteeism, mindfulness, nurses……）
**ref_population**：研究对象，如`["护士"]`、`["ICU护士"]`，没有则`[]`
**ref_method**：研究方法，如`["横断面"]`、`["meta-analysis"]`，没有则`[]`
**ref_year_hint**：句中提到的年份，没有则`""`
**ref_journal_hint**：句中提到的期刊名，没有则`""`
**key_claim**：角标句的论点（忠实原句，允许结论表述）
**core_topic**：一句话概括
**claim_type**：policy_macro / concept_definition / mechanism / status_quo / intervention / review_progress
**claim_confidence**：0-1
**secondary_claim_type**：次要类型或`""`
**ref_type**：J期刊 / M专著 / R报告 / D学位论文 / C会议 / EB网络 / Z不确定
**ref_type_confidence**：0-1
**ref_type_hint**：一句说明
**cn_keywords**：5个中文学术实体词（用于排序）
**en_keywords**：5个英文学术实体词（用于排序）
**search_query_cn**：用ref_title_keywords_cn拼成，空格分隔，2-4个词
**search_query_en**：用ref_title_keywords_en拼成，空格分隔，2-4个词
**research_method**：研究方法
**recommended_lang**：被引文献更可能是中文还是英文？
  - `"cn"`：中文文献（如知网论文、中文专著、中国政策文件）
  - `"en"`：英文文献（如SCI/SSCI期刊、英文专著）
  - 判断依据：句中是否出现中文作者名、中文书名号、中国特有政策？角标句是在讨论中国本土现象还是国际研究？

严格返回 JSON，不要其他文字：
{{
  "key_claim": "", "core_topic": "", "research_method": "",
  "claim_type": "", "claim_confidence": 0.9, "secondary_claim_type": "",
  "ref_type": "J", "ref_type_confidence": 0.8, "ref_type_hint": "",
  "ref_authors": [], "ref_title_keywords_cn": [], "ref_title_keywords_en": [],
  "ref_population": [], "ref_method": [], "ref_year_hint": "", "ref_journal_hint": "",
  "cn_keywords": [], "en_keywords": [],
  "search_query_cn": "", "search_query_en": "",
  "recommended_lang": "en"
}}"""

        import time as _time
        last_err = None
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是学术文献检索专家。你的核心任务：从角标句推断被引文献的标题特征词。"
                                "检索词必须像论文标题里会出现的名词（变量名、人群、方法），"
                                "绝对不能是结论性表述（如'显著提高''负相关''日益严峻'）。"
                                "只返回 JSON。"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    extra_body={"enable_thinking": False},
                )

                content = response.choices[0].message.content.strip()
                data = json.loads(content)
                raw_ct = (data.get("claim_type") or "").strip()
                if raw_ct not in CLAIM_TYPES:
                    raw_ct = infer_claim_type_from_text(
                        data.get("key_claim", ""), paper_title
                    )
                sec = (data.get("secondary_claim_type") or "").strip()
                if sec not in CLAIM_TYPES:
                    sec = ""
                try:
                    conf = float(data.get("claim_confidence", 1.0))
                except (TypeError, ValueError):
                    conf = 1.0
                conf = max(0.0, min(1.0, conf))
                kc = data.get("key_claim", "") or ""
                # 关键词纠偏：明显含机制关系词却未标 mechanism → 强制次要类型
                if claim_text_suggests_mechanism(kc) and raw_ct != "mechanism":
                    if sec != "mechanism":
                        sec = sec or "mechanism"

                rt_raw = str(data.get("ref_type") or "J").strip().upper()
                if rt_raw.startswith("EB"):
                    rt_raw = "EB"
                if rt_raw not in ("J", "M", "R", "D", "C", "EB", "Z"):
                    rt_raw = "J"
                try:
                    rtc = float(data.get("ref_type_confidence", 0.7))
                except (TypeError, ValueError):
                    rtc = 0.7
                rtc = max(0.0, min(1.0, rtc))
                rth = str(data.get("ref_type_hint", "") or "")
                ra = _coerce_str_list(data.get("ref_authors"), 10)
                rtcn = _coerce_str_list(data.get("ref_title_keywords_cn"), 14)
                rten = _coerce_str_list(data.get("ref_title_keywords_en"), 14)
                rpop = _coerce_str_list(data.get("ref_population"), 10)
                rmet = _coerce_str_list(data.get("ref_method"), 8)
                ryh = str(data.get("ref_year_hint", "") or "").strip()
                rjh = str(data.get("ref_journal_hint", "") or "").strip()

                return AnalysisResult(
                    marker_id=marker_id,
                    core_topic=data.get("core_topic", ""),
                    research_method=data.get("research_method", ""),
                    key_claim=kc,
                    cn_keywords=_coerce_str_list(data.get("cn_keywords"), 12),
                    en_keywords=_coerce_str_list(data.get("en_keywords"), 12),
                    search_query_cn=str(data.get("search_query_cn", "") or "").strip(),
                    search_query_en=str(data.get("search_query_en", "") or "").strip(),
                    claim_type=raw_ct,
                    secondary_claim_type=sec,
                    claim_confidence=conf,
                    ref_type=rt_raw,
                    ref_type_confidence=rtc,
                    ref_type_hint=rth,
                    ref_authors=ra,
                    ref_title_keywords_cn=rtcn,
                    ref_title_keywords_en=rten,
                    ref_population=rpop,
                    ref_method=rmet,
                    ref_year_hint=ryh,
                    ref_journal_hint=rjh,
                    recommended_lang=(
                        "cn"
                        if (data.get("recommended_lang") or "").strip().lower().startswith("cn")
                        or (data.get("recommended_lang") or "").strip() == "中文"
                        else "en"
                    ),
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
        prompt = f"""在知网(CNKI)等库用下列检索式未找到合适文献。请生成**更宽但仍像论文标题/主题词**的替代检索词。
{title_hint}
**检索元数据（宽泛化时优先保留其中的实体，不要改成结论句）**：
- ref_authors: {original.ref_authors}
- ref_title_keywords_cn: {original.ref_title_keywords_cn}
- ref_population: {original.ref_population}
- ref_method: {original.ref_method}
原始备用检索式（搜不到）：{original.search_query_cn}
**论证句（仅供核对变量来源，勿当作检索句复述）**：{original.key_claim}

知网搜索技巧：
- 用**日常学术用语**；可去掉罕见人名，但若 ref_authors 明示第一作者且检索目标为「某某的研究」，应保留或保留姓氏
- 去掉量表缩写，用通俗名
- 每组 2～4 个常见中文实体词，空格分隔
- 禁止出现「角标」「参考文献」「PPT」等与文献无关的词

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
                    {
                        "role": "system",
                        "content": (
                            "你是学术检索专家。宽泛化的是**题名式主题词**，不是结论句；"
                            "保留原检索轨道中的变量与人群；不可偷换成另一主题。只返回 JSON。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.25,
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
                claim_type=getattr(original, "claim_type", None) or "status_quo",
                secondary_claim_type=getattr(original, "secondary_claim_type", "") or "",
                claim_confidence=getattr(original, "claim_confidence", 1.0),
                ref_type=getattr(original, "ref_type", "J") or "J",
                ref_type_confidence=getattr(original, "ref_type_confidence", 0.0),
                ref_type_hint=getattr(original, "ref_type_hint", "") or "",
                ref_authors=list(getattr(original, "ref_authors", []) or []),
                ref_title_keywords_cn=list(
                    getattr(original, "ref_title_keywords_cn", []) or []
                ),
                ref_title_keywords_en=list(
                    getattr(original, "ref_title_keywords_en", []) or []
                ),
                ref_population=list(getattr(original, "ref_population", []) or []),
                ref_method=list(getattr(original, "ref_method", []) or []),
                ref_year_hint=getattr(original, "ref_year_hint", "") or "",
                ref_journal_hint=getattr(original, "ref_journal_hint", "") or "",
            )
        except Exception:
            return original

    def refine_search(
        self,
        original: AnalysisResult,
        failed_query: str,
        found_titles: list[str],
        target_lang: str = "cn",
        paper_title: str = "",
    ) -> tuple[str, str]:
        """搜不到时反馈给 LLM，让它换词重搜。返回 (cn_query, en_query)。"""
        title_hint = f"\n论文标题：{paper_title}" if paper_title else ""
        found_info = ""
        if found_titles:
            found_info = f"\n搜到了以下文献但都不太对：\n" + "\n".join(
                f"  - {t[:60]}" for t in found_titles[:5]
            )
        else:
            found_info = "\n搜索结果为空，一篇也没搜到。"

        prompt = f"""{title_hint}
我用「{failed_query}」在{'知网' if target_lang == 'cn' else 'CrossRef/OpenAlex'}搜索，想找支撑以下论点的文献：
论点：{original.key_claim}
{found_info}

请给我**2组新的检索词**（每组 2-4 个名词/专名，空格分隔），换个角度搜。
要求：
- 像论文标题里会出现的词，不要结论表述
- 每组不超过 4 个词
- 不要重复已经失败的检索词

返回 JSON：
{{
  "cn_query": "中文检索词",
  "en_query": "English search terms",
  "cn_query_2": "备选中文检索词",
  "en_query_2": "alternative English terms"
}}"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是学术检索专家。换词时保持与原论点相关，只返回 JSON。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            data = json.loads(resp.choices[0].message.content.strip())
            if target_lang == "cn":
                q1 = (data.get("cn_query") or "").strip()
                q2 = (data.get("cn_query_2") or "").strip()
                return q1 or q2, (data.get("en_query") or "").strip()
            else:
                q1 = (data.get("en_query") or "").strip()
                q2 = (data.get("en_query_2") or "").strip()
                return (data.get("cn_query") or "").strip(), q1 or q2
        except Exception:
            return "", ""

    def decompose_claim_for_search(
        self,
        original: AnalysisResult,
        paper_title: str = "",
        target_lang: str = "cn",
    ) -> list[dict]:
        """将论点拆成 2～3 条可独立检索的子查询（多轮仍无结果时使用）。"""
        title_hint = f"\n论文标题：{paper_title}" if paper_title else ""
        lang_hint = "每条同时给出中文检索式 cn 与英文检索式 en（英文 2～4 个词）。" if target_lang == "cn" else "每条给出英文检索式 en，并给出对应中文 cn。"
        prompt = f"""以下检索在数据库中难以一次搜全。请拆成 2～3 条**独立题名式检索式**（像论文会用的主题词组合），提高召回率。
{title_hint}
**检索元数据**：authors={original.ref_authors} | 题名关键词-中={original.ref_title_keywords_cn} | 题名关键词-英={original.ref_title_keywords_en} | 人群={original.ref_population} | 方法={original.ref_method}
当前中文检索式：{original.search_query_cn}
当前英文检索式：{original.search_query_en}
**论证句（实体须能追溯至此句，勿用句中未出现的主题）**：{original.key_claim}

要求：
- 每条 cn/en 为 2～5 个**实体词**，不要写成结论句
- 覆盖不同变量组合（如 A+B、B+人群），避免纯同义词重复
- 若有《书名》或明示作者，至少一条含书名核心词或作者姓
- {lang_hint}
- 护理/医务类论文时，中文检索式须含「护士」或「护理」或「医务人员」之一；英文须含 nurse 或 nursing

返回 JSON：
{{
  "subqueries": [
    {{"label": "子主题1一句话", "cn": "2-3个中文词空格分隔", "en": "2-4 English words"}},
    {{"label": "子主题2一句话", "cn": "...", "en": "..."}}
  ]
}}"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是学术信息检索专家，拆分的是题名式检索式，不是结论复述；只返回 JSON。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.25,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            data = json.loads(resp.choices[0].message.content.strip())
            subs = data.get("subqueries", [])
            out = []
            for s in subs[:3]:
                if isinstance(s, dict) and (s.get("cn") or s.get("en")):
                    out.append({"cn": (s.get("cn") or "").strip(), "en": (s.get("en") or "").strip()})
            return out
        except Exception as e:
            print(f"[ContentAnalyzer] decompose_claim_for_search 失败: {e}")
            return []

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
