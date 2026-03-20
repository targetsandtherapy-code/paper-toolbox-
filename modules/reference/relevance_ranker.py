"""相关性排序模块 — 使用 LLM 对候选文献与段落内容打分"""
import hashlib
import json
from typing import Any, Optional

from openai import OpenAI
from modules.reference.searcher.base import Paper
from modules.reference.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from modules.reference.core_journals import is_core_journal


def _paper_claim_cache_key(paper: Paper, claim: str, *parts: str) -> str:
    pid = (paper.doi or "").strip().lower()
    if not pid:
        pid = hashlib.md5((paper.title or "").encode("utf-8", errors="ignore")).hexdigest()[:20]
    ch = hashlib.md5((claim or "").encode("utf-8", errors="ignore")).hexdigest()[:12]
    return "|".join([pid, ch] + [str(p) for p in parts])


class RelevanceRanker:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def rank(self, context: str, claim: str, candidates: list[Paper], top_k: int = 3,
             paper_title: str = "", min_score: int = 4) -> list[Paper]:
        if not candidates:
            return []

        if len(candidates) <= top_k:
            return candidates

        candidates_text = ""
        for i, p in enumerate(candidates):
            abstract_preview = (p.abstract or "无摘要")[:220]
            core_tag = "★核心期刊" if is_core_journal(p.journal or "") else "普通期刊"
            candidates_text += (
                f"\n{i+1}. 标题: {p.title}"
                f"\n   摘要: {abstract_preview}"
                f"\n   期刊: {p.journal or 'N/A'} [{core_tag}] | 年份: {p.year} | 被引: {p.citation_count or 0}\n"
            )

        title_hint = f"\n本论文标题：{paper_title}" if paper_title else ""
        title_anchor = ""
        if paper_title:
            title_anchor = (
                "\n**请先根据论文标题**把握全文学科、核心人群与主干变量（含是否含干预/机制）；**每篇论文题目不同**，勿套用固定课题模板。"
                "评分时候选文献须同时贴合「本题题目语境」与「角标论点」，勿因单篇质量高而忽略与题目人群或论点变量不符的情况。\n"
                "**题目—论点—文献 三方对齐**：若题目主干包含某干预或机制、且论点 claim 也在谈该链条，则**同类干预/机制实证**可高分；"
                "勿仅因「属于干预研究」就压低与**当前题目**一致的文献。若论点仅为某概念的**纯背景/概念史**且与题目干预无关，再将「无关干预 RCT」从严给低分。\n"
            )
        prompt = f"""你是学术论文引用匹配专家。请严格评估以下候选文献与论文段落中特定论点的相关性。
{title_hint}{title_anchor}
论文段落上下文：
{context}

该引用需要支撑的具体论点（角标处必须能由文献直接支撑）：
{claim}

候选文献：
{candidates_text}

评分规则（请严格执行，宁低勿高）：
- **书名号《…》**：若论点明确引自某书/规范，文献标题或摘要须**体现该书或该文献类型（专著/教材）及主题对应**；仅主题泛相关而完全未涉该书/该规范者，最高不超过4分
- **句中点名学者/人名**：候选文献应体现该学者的**实证、综述或原著**工作；完全未涉该姓名且与「谁提出/谁定义」类断言无关的，最高不超过4分
- **必须先核对论点中的核心变量、人群、机制**：只与大领域（如护理、心理）沾边但变量/对象不符的，最高不超过4分
- **显性缺勤 absenteeism（未到岗）** 与 **隐性缺勤 presenteeism（带病在岗）** 不可混用：论点明确写缺勤率监测、absenteeism、人力资源管理中的缺勤时，文献若**仅**讨论 presenteeism 而无对 absenteeism 的实质内容，最高不超过3分
- **纯概念起源/定义/多学科讨论** 的论点：若候选仅为**与论点概念无关**的某干预 RCT，且摘要未讨论该概念的理论或综述脉络，最高不超过3分；**若题目主干与 claim 明确就是该干预/机制与结局的关系，则按常规则给分，勿套用本条**
- **中国宏观卫生政策**（二十大、健康中国、医疗卫生队伍）：若文献仅为某国局部医院人力配置细则且与中国政策语境明显无关，最高不超过5分（除非摘要明确讨论国家层卫生人力战略且可类比）
- 8-10分: 论文直接研究该论点涉及的核心变量/概念/方法，属于实证研究或系统综述
- 5-7分: 论文研究领域相同，且涉及该论点的部分关键概念（实证研究）
- 3-4分: 仅领域相关，但未涉及该论点的核心概念
- 1-2分: 与该具体论点无实质关联
- 0分: 教学论文、教材编写、课程设计、综述教材章节等非研究性论文，一律给0分

重要排除规则（以下论文必须给0分）：
- 标题含"教学""课程""教材""教育改革"等的教学类论文
- Decision letter、Author response、Correction:、Review for "…"、Supplemental material 等非正式论文
- 纯 CiteSpace / 科学计量可视化、无独立研究结论的文献
- 研究对象完全不同的论文（论点关于护士/护理人员时，文献却是警察、患者家属、酒店员工、中学生、普通大学生等）
- 预印本中无摘要且标题与论点明显不符的论文

期刊质量加分：
- ★核心期刊：+2 分（上限10分）
- 普通期刊：不加分
- 相关性仍是第一优先级；**核心期刊加分不得使明显无关文献超过 6 分**
- **reason 写法**：须点明论点**核心词**在文献标题或摘要中的对应；若仅能写「同属大领域」而无对应词，该篇最高不超过 5 分

请严格按以下 JSON 格式返回（不要添加其他文字）：
{{
  "rankings": [
    {{"index": 1, "score": 9, "reason": "简短理由"}},
    {{"index": 2, "score": 5, "reason": "简短理由"}}
  ]
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是严谨的学术论文引用匹配专家。评分以论点与文献的**命题级对应**为准，"
                            "禁止因期刊名气或摘要泛泛相关而抬高分数。reason 必须可核对。只返回 JSON。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.15,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )

            content = response.choices[0].message.content.strip()
            data = json.loads(content)
            rankings = data.get("rankings", [])

            score_map = {}
            for r in rankings:
                idx = r.get("index", 0)
                score = r.get("score", 0)
                if 1 <= idx <= len(candidates):
                    score_map[idx - 1] = score

            scored = []
            for i, p in enumerate(candidates):
                scored.append((score_map.get(i, 0), p))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [p for s, p in scored[:top_k] if s >= min_score]

        except Exception as e:
            print(f"[RelevanceRanker] 排序失败，返回原始顺序: {e}")
            return candidates[:top_k]

    def verify_fit(
        self,
        context: str,
        claim: str,
        paper: Paper,
        paper_title: str = "",
    ) -> bool:
        """最终校验：该文献是否真能支撑角标处论点（与论文主题一致）。"""
        abst = (paper.abstract or "")[:500]
        title_fit_hint = ""
        if paper_title:
            title_fit_hint = (
                "\n（篇目会变：请结合**本题**题目中的人群、核心变量、是否含干预/机制等主干，判断文献与论点是否真匹配。）\n"
            )
        prompt = f"""你是学术引用审核专家。判断下面这篇文献是否适合作为引用，用来支撑「具体论点」。

本论文题目：{paper_title or "（未提供）"}
{title_fit_hint}角标所在句/段落（节选）：{context[:800]}
需要支撑的论点：{claim}

待选文献：
- 标题：{paper.title}
- 期刊：{paper.journal or "未知"}
- 摘要（节选）：{abst}

判定为 **不适合**（fit=false）的情况包括但不限于：
- 研究对象与论点明显不符（例如论点写护士/护理人员，文献却是警察、普通大学生、酒店员工、患者/家属为主角等）
- 论点强调 **absenteeism/到岗缺勤**（人力资源管理、缺勤率监测），而文献**仅**研究 **presenteeism** 且摘要未涉及缺勤到岗，二者不可互相替代 → fit=false
- 论点为 **概念起源、定义、多学科理论讨论**（且**与题目主干的干预/暴露无关**），而文献仅为**另一类无关干预试验**且未讨论论点中的概念脉络 → fit=false
- 论点含 **《书名》** 而文献明显**不是该书及相关书评/引用研究**、无法作为该书依据 → fit=false
- 论点**点名特定学者**作为出处，而文献**完全未出现该学者工作**且摘要无法支撑「该人提出/定义」→ fit=false
- 论点为 **中国宏观卫生政策**（二十大、健康中国、医疗卫生队伍），而文献仅为**他国局部机构** staffing 且无法支撑该政策表述 → fit=false
- 论点为 **国家层卫生战略/队伍壮大**，而文献主题为**食疗养生、单科设置臆想、个案护理**等与政策表述无实质支撑关系 → fit=false
- 非正式研究文献：Decision letter、Author response、Correction、纯编辑信件等
- 仅有科学计量/CiteSpace 图谱、无实质研究结论的文献
- 主题词沾边但变量/机制与论点无关，无法作为该句的依据

若文献可以合理支撑该论点，fit=true。

只返回 JSON：{{"fit": true 或 false, "reason": "不超过30字"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是严谨的引用审核专家。fit=true 仅当文献能直接背书论点中的断言，"
                            "不能仅靠护理/健康大领域沾边。只返回 JSON。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.08,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            data = json.loads(response.choices[0].message.content.strip())
            return bool(data.get("fit", False))
        except Exception as e:
            print(f"[RelevanceRanker] verify_fit 失败，默认接受: {e}")
            return True

    def _one_type_batch_hint(self, claim_type: str) -> str:
        ct = claim_type or "status_quo"
        if ct == "policy_macro":
            return (
                "\n**论点类型：宏观政策/战略**。优先匹配**中国语境**（健康中国、卫生人才队伍、医改、二十大相关卫生表述）"
                "或**可类比的全球卫生人力战略**论述；政策解读、卫生体系、人才队伍可判 fit=true；不要求随机对照。"
                "欧洲某单一医院排班细则若与「国家战略/队伍壮大」明显无关，倾向 false。"
            )
        if ct == "concept_definition":
            return (
                "\n**论点类型：概念/定义/起源**。若文献讨论该概念的理论界定、综述、多学科脉络或发展，可判 fit=true；"
                "勿要求与论文具体研究情境逐句一致。"
            )
        if ct == "mechanism":
            return (
                "\n**论点类型：中介/调节/路径**。粗筛时只要涉及论点中的关键变量之一或同人群同主题机制研究，"
                "可判 fit=true；明显无关再 false。精细匹配留给后续步骤。"
            )
        if ct == "review_progress":
            return (
                "\n**论点类型：综述/进展**。综述、系统评价、研究进展类文献可判 fit=true；优先近年发表。"
            )
        if ct == "intervention":
            return (
                "\n**论点类型：干预/效果**。随机对照、干预方案、训练效果类实证可判 fit=true。"
            )
        return ""

    def _batch_claim_type_hint(self, claim_type: str, secondary: str = "") -> str:
        """主类型 + 次要类型（并集）提示，避免只返回主类型而丢失次类型。"""
        primary_ct = claim_type or "status_quo"
        parts = [self._one_type_batch_hint(primary_ct)]
        sec = (secondary or "").strip()
        if sec and sec != primary_ct:
            sh = self._one_type_batch_hint(sec)
            if sh:
                parts.append("\n**次要类型（并集）**" + sh)
        return "".join(parts)

    def verify_fit_batch(
        self,
        context: str,
        claim: str,
        papers: list[Paper],
        paper_title: str = "",
        claim_type: str = "status_quo",
        secondary_claim_type: str = "",
    ) -> list[bool]:
        """一次请求判断多篇文献是否适合支撑该角标论点（显著减少 API 次数）。"""
        if not papers:
            return []
        if len(papers) == 1:
            return [
                self.verify_fit(context, claim, papers[0], paper_title),
            ]

        lines = []
        for i, p in enumerate(papers):
            abst = (p.abstract or "")[:320]
            lines.append(
                f"【文献{i+1}】标题：{p.title}\n"
                f"期刊：{p.journal or '未知'}\n摘要节选：{abst}\n"
            )
        block = "\n".join(lines)
        ct_hint = self._batch_claim_type_hint(
            claim_type or "status_quo", secondary_claim_type or ""
        )

        prompt = f"""本论文题目：{paper_title or "（未提供）"}
角标所在句/段落（节选）：{context[:700]}
需要支撑的论点：{claim}
{ct_hint}

以下共 {len(papers)} 篇候选，请逐篇判断是否适合作为该论点的引用依据。

{block}

对每篇文献输出 fit：true 表示可以合理支撑该论点；false 表示对象/变量/主题明显不符，或系编辑信件/CiteSpace 计量等非实质研究。

**放宽**：若论点涉及隐性缺勤的概念、内涵、定义、研究进展、影响因素、现状等，且文献标题明确为护士/护理人员/医务人员与隐性缺勤的实证或综述，应判 fit=true。

**政策类（claim 含二十大/健康中国/卫生人才队伍等）**：fit=true 须文献明显讨论**中国卫生政策、医改、人才队伍或同级战略话语**；**不得**仅凭「护士+健康」或食疗/学科设置类杂文即判 true。

**书名号/人名**：论点含《…》则文献须能作为该书或该规范之依据；论点点名学者则文献须体现该学者相关工作，否则 fit=false。

只返回 JSON，fits 为长度 {len(papers)} 的布尔数组，顺序与文献编号一致：
{{"fits": [true, false, ...]}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是严谨的批量引用审核专家，宁缺毋滥；fits 长度必须与文献篇数一致。"
                            "只返回 JSON。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.08,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            data = json.loads(response.choices[0].message.content.strip())
            fits = data.get("fits", [])
            if not isinstance(fits, list) or len(fits) != len(papers):
                print("[RelevanceRanker] verify_fit_batch 返回长度异常，逐篇回退")
                return [self.verify_fit(context, claim, p, paper_title) for p in papers]
            return [bool(x) for x in fits]
        except Exception as e:
            print(f"[RelevanceRanker] verify_fit_batch 失败，逐篇校验: {e}")
            return [self.verify_fit(context, claim, p, paper_title) for p in papers]

    def verify_fit_deep(
        self,
        paragraph: str,
        context_before: str,
        claim: str,
        paper: Paper,
        paper_title: str = "",
        claim_type: str = "status_quo",
        cache: Optional[dict[str, Any]] = None,
    ) -> bool:
        """第二阶段精校：更长段落与摘要；按论点类型使用不同严格度。"""
        ck = _paper_claim_cache_key(paper, claim, claim_type or "status_quo", "deep_v2")
        if cache is not None and ck in cache:
            return bool(cache[ck])

        abst = (paper.abstract or "")[:900]
        ct = claim_type or "status_quo"

        if ct == "policy_macro":
            prompt = f"""你是引用审核专家。论点为**中国宏观政策/卫生战略/人才队伍**类表述。

论文题目：{paper_title or "（未提供）"}
段落节选：{paragraph[:1200]}
角标所在句（节选）：{context_before[:600]}
论点：{claim}

候选文献：
- 标题：{paper.title}
- 期刊：{paper.journal or "未知"}
- 摘要：{abst}

**fit=true**：文献在讨论医疗卫生体系、卫生人力、健康中国/国民健康战略、医改与政策议题，或与论点同一政策话语（可含行业分析、战略意义论述）；不要求 RCT。
**fit=false**：仅泛泛护理操作/临床技巧且完全不涉政策/体系/队伍战略，或对象主题明显无关；**食疗、生活方式医学纳入二级学科等杂文**若与「壮大队伍/二十大表述」无直接论述关系，判 false。

只返回 JSON：{{"fit": true 或 false}}"""
        elif ct == "concept_definition":
            prompt = f"""你是引用审核专家。论点为**概念定义、起源、内涵或多学科讨论**。

论文题目：{paper_title or "（未提供）"}
段落节选：{paragraph[:1200]}
角标所在句（节选）：{context_before[:600]}
论点：{claim}

候选文献：
- 标题：{paper.title}
- 期刊：{paper.journal or "未知"}
- 摘要：{abst}

**fit=true**：文献核心在讨论该概念（如 presenteeism/隐性缺勤）的理论、定义、综述、测量或跨学科脉络即可。
**fit=false**：完全未涉及该概念或明显另一主题。

只返回 JSON：{{"fit": true 或 false}}"""
        else:
            prompt = f"""你是严格的引用审核专家。判断这篇文献是否**直接、有力**地支撑角标所在句子的论点。

论文题目：{paper_title or "（未提供）"}
角标所在段落（完整或较长节选）：
{paragraph[:1200]}

角标紧邻前文：
{context_before[:600]}

需要支撑的论点：{claim}

候选文献：
- 标题：{paper.title}
- 期刊：{paper.journal or "未知"}
- 摘要：{abst}

**通过（fit=true）** 仅当：文献的研究问题或结论能**直接对应**论点中的核心关系（如变量、机制、量表、理论），而非仅同属「护理/心理」大领域。

**不通过（fit=false）**：仅领域相关、对象不符、或无法作为该句依据。

只返回 JSON：{{"fit": true 或 false}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "只返回 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.05,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            data = json.loads(response.choices[0].message.content.strip())
            out = bool(data.get("fit", False))
            if cache is not None:
                cache[ck] = out
            return out
        except Exception as e:
            print(f"[RelevanceRanker] verify_fit_deep 失败，沿用粗判: {e}")
            if cache is not None:
                cache[ck] = True
            return True

    def verify_fit_mechanism_tier(
        self,
        paragraph: str,
        context_before: str,
        claim: str,
        paper: Paper,
        paper_title: str = "",
        cache: Optional[dict[str, Any]] = None,
    ) -> str:
        """机制类论点：在严格精校失败后，评定 exact / relevant / contextual / none。"""
        ck = _paper_claim_cache_key(paper, claim, "mechanism", "tier_v1")
        if cache is not None and ck in cache:
            return str(cache[ck])

        abst = (paper.abstract or "")[:900]
        prompt = f"""论点往往涉及**中介、调节或链式路径**等多变量关系。请判断文献对论点的支撑等级（四选一）。

论文题目：{paper_title or "（未提供）"}
段落节选：{paragraph[:1200]}
角标所在句（节选）：{context_before[:600]}
论点：{claim}

候选文献：
- 标题：{paper.title}
- 期刊：{paper.journal or "未知"}
- 摘要：{abst}

等级定义：
- exact：研究了与论点相同或高度同构的变量关系/路径
- relevant：涉及论点中至少一对关键变量或机制的一部分（可作主要依据的弱化版）
- contextual：同人群、同主题（如护士+隐性缺勤），但未覆盖论点中的具体路径，可作背景/情境支撑
- none：明显无关或对象不符

只返回 JSON：{{"tier": "exact"|"relevant"|"contextual"|"none"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "只返回 JSON，tier 必须是四个单词之一。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.08,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            data = json.loads(response.choices[0].message.content.strip())
            tier = (data.get("tier") or "none").strip().lower()
            if tier not in ("exact", "relevant", "contextual", "none"):
                tier = "none"
            if cache is not None:
                cache[ck] = tier
            return tier
        except Exception as e:
            print(f"[RelevanceRanker] verify_fit_mechanism_tier 失败: {e}")
            if cache is not None:
                cache[ck] = "none"
            return "none"
