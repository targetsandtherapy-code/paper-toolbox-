"""主流程：论文参考文献智能生成（支持中英文比例控制）"""
import sys
import re
import json
import time
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from config import (
    REFERENCE_LANG_FALLBACK,
    REFERENCE_NURSING_HARD_SCOPE,
    REFERENCE_POLICY_ALLOW_EN_FALLBACK,
    REFERENCE_POLICY_CN_ONLY,
    REFERENCE_RESCUE_CN_FALLBACK_EN,
    REFERENCE_SEQUENTIAL_EN_SEARCH,
    REFERENCE_SKIP_DECOMPOSE_FOR_POLICY,
    REFERENCE_SKIP_POOL_FALLBACK,
    YEAR_RANGE,
)
from modules.doc_parser import DocParser
from modules.reference.content_analyzer import ContentAnalyzer
from modules.reference.searcher.crossref import CrossRefSearcher
from modules.reference.searcher.openalex import OpenAlexSearcher
from modules.reference.searcher.pubmed import PubMedSearcher
from modules.reference.searcher.cnki import CNKISearcher
from modules.reference.searcher.base import Paper
from modules.reference.fast_ranker import fast_rank
from modules.reference.relevance_ranker import RelevanceRanker
from modules.reference.field_analyzer import FieldAnalyzer, build_journal_set, is_field_core_journal
from modules.reference.formatter import format_reference_list, format_reference_list_markdown
from modules.reference.quote_lang import quoted_title_source_lang
from modules.reference.quoted_work_refs import try_resolve_quoted_citation
from modules.reference.ref_type_routing import (
    adjust_queries_for_ref_type,
    lang_attempts_for_ref_type,
    resolve_ref_type_for_marker,
    should_skip_decompose_for_ref_type,
    should_skip_domain_fallback,
    use_light_english_sources,
)
from modules.reference.search_query_builder import (
    build_search_queries_from_analysis,
    rank_keywords_from_analysis,
)
from modules.db.claim_cache import get_cached_paper_for_claim, save_cached_match


def _is_chinese_title(title: str) -> bool:
    """判断标题是否为中文"""
    if not title:
        return False
    cn_chars = sum(1 for c in title if '\u4e00' <= c <= '\u9fff')
    return cn_chars / max(len(title), 1) > 0.3


_TITLE_JUNK_RE = re.compile(
    r"decision\s+letter|author\s+response|supplemental\s+material|"
    r"(^|\s)correction:\s|review\s+for\s+[\"\']|editorial\s+response|"
    r"author\s+response\s+for",
    re.I,
)

_IRRELEVANT_KEYWORDS = {
    "教学", "课程思政", "课程教学", "教学改革", "教学实践", "教学模式",
    "教学设计", "教学探索", "教学中的应用", "体验式教学", "对分课堂",
    "翻转课堂", "混合式教学", "OBE理念", "PBL教学", "课程建设",
    "教材", "慕课", "课堂教学", "教学质量", "教育评价",
}

_ANIMAL_VETERINARY_RE = re.compile(
    r"\b(horses?|equine|bovine|cattle|calves|calf|goats?|sheep|swine|porcine|"
    r"poultry|chickens?|canine|feline|piglets?|ewes?|heifers?|"
    r"veterinary|dairy\s+goats?|dairy\s+cattle|feedlot)\b",
    re.I,
)
_ANIMAL_CN_KEYWORDS = ("牛", "猪", "羊", "马", "鸡", "犬", "猫", "兽医", "畜牧", "肉牛", "奶牛")

# 注入检索词用（中文）
_NURSING_QUERY_MARKERS = ("护士", "护理", "医护", "医务人员", "护理人员")


def _thesis_nursing_scope(paper_title: str) -> bool:
    """论文题目是否要求引用落在护理/临床医务情境"""
    if not paper_title:
        return False
    return any(k in paper_title for k in ("护士", "护理", "医护", "医务"))


def _cn_title_has_care_scope(title: str) -> bool:
    if not title:
        return False
    if any(
        k in title
        for k in (
            "护士", "护理人员", "医务人员", "医护", "护师", "护士长",
            "临床护士", "ICU护士", "手术室护士", "急诊护士", "精神科护士",
            "注册护士", "新入职护士", "专科护士", "医务工作者",
        )
    ):
        return True
    if "护理" in title and all(x not in title for x in ("教学", "课程", "实习生", "护生")):
        return True
    return False


def _en_title_has_care_scope(title: str) -> bool:
    if not title:
        return False
    t = title.lower()
    if re.search(
        r"\b(nurses?|nursing|midwif|icu\s+nurses?|operating\s+room\s+nurses?|"
        r"psychiatric\s+nurses?|perioperative\s+nurses?|registered\s+nurses?|\brn\b)\b",
        t,
    ):
        return True
    if re.search(
        r"\b(health\s*care\s+workers?|healthcare\s+workers?|hospital\s+nurses?|"
        r"hospital\s+staff|hospital\s+workers?|clinical\s+staff|medical\s+staff)\b",
        t,
    ):
        return True
    return False


def _cn_title_wrong_population(title: str) -> bool:
    """中文标题中明显非护理人群（且标题未体现护理情境）"""
    bad = (
        "警察", "警务", "公安", "教师", "幼儿教师", "会计", "银行",
        "大学生", "中学生", "高中生", "小学生", "本科生", "硕士研究生",
        "企业职工", "酒店", "厨师", "听障", "运动员",
        "行政管理人员", "医院行政", "产业工人", "矿工",
        "产妇", "剖宫产", "妊娠期高血压", "妊高症", "患儿家长",
        "护生", "实习护生", "本科护生",
    )
    return any(b in title for b in bad)


def _en_title_wrong_population(title: str) -> bool:
    t = (title or "").lower()
    pats = [
        r"\bpolice\b", r"\bpolicing\b", r"\bteachers?\b", r"\baccounting\s+educators?\b",
        r"\bhospitality\b", r"\bhotel\s", r"\brheumatoid\b",
        r"\bhome\s+industry\b", r"\bpregnant\b", r"\bpostpartum\b",
        r"\bhigh\s+school\b", r"\badolescents?\b",
        r"\boccupational\s+therapist\b",
    ]
    for pat in pats:
        if re.search(pat, t):
            return True
    if re.search(r"\b(students?|undergraduates?)\b", t) and not re.search(
        r"\b(nurse|nursing)\b", t
    ):
        return True
    return False


def _paper_passes_content_scope(
    paper: Paper,
    target_lang: str,
    scope_nursing: bool,
) -> bool:
    """非正式文献过滤 +（护理类题目时）强制护理/医务情境与人群。"""
    title = paper.title or ""
    if _TITLE_JUNK_RE.search(title):
        return False
    if re.search(r"citespace", title, re.I):
        return False
    for kw in _IRRELEVANT_KEYWORDS:
        if kw in title:
            return False
    if _ANIMAL_VETERINARY_RE.search(title):
        return False
    if any(kw in title for kw in _ANIMAL_CN_KEYWORDS):
        return False
    if not scope_nursing:
        return True
    if target_lang == "cn":
        if _cn_title_wrong_population(title):
            return False
        return _cn_title_has_care_scope(title)
    if _en_title_wrong_population(title):
        return False
    return _en_title_has_care_scope(title)


def _is_irrelevant_paper(paper: Paper, strict: bool = False) -> bool:
    """兼容旧调用：基础垃圾过滤；strict 时护理题目下中英任一门槛通过即不算垃圾。"""
    title = paper.title or ""
    for kw in _IRRELEVANT_KEYWORDS:
        if kw in title:
            return True
    if _TITLE_JUNK_RE.search(title) or re.search(r"citespace", title, re.I):
        return True
    if strict:
        cn_ok = _paper_passes_content_scope(paper, "cn", True)
        en_ok = _paper_passes_content_scope(paper, "en", True)
        return not (cn_ok or en_ok)
    return False


def _claim_allows_student_sample(claim: str) -> bool:
    c = claim or ""
    return any(
        k in c
        for k in (
            "护生",
            "实习护",
            "本科护生",
            "护理学生",
            "学生",
            "undergraduate",
            "student nurse",
        )
    )


def _title_is_nursing_student_study(title: str) -> bool:
    t = (title or "").lower()
    return bool(
        re.search(r"nursing\s+students?|student\s+nurses?|nurse\s+students?", t)
    )


def _heuristic_fit_veto(paper: Paper, claim: str) -> bool:
    """明显跑题的硬否决（不依赖 LLM）。"""
    t = paper.title or ""
    c = claim or ""
    if not t or not c:
        return False
    # 论点谈健康中国/队伍，文献却在谈食疗、二级学科划分等
    if any(k in c for k in ("健康中国", "医疗卫生队伍", "卫生人才")):
        if "隐性缺勤" not in t and "presenteeism" not in t.lower():
            if any(b in t for b in ("食疗", "二级学科", "生活方式医学", "大健康产业")):
                return True
    return False


def _analysis_needs_deep_verify(cur_analysis) -> bool:
    """仅机制关系型（主类或次要类）进入二阶段精校，其余类型批量 fit 通过即可（提速、防误杀）。"""
    if getattr(cur_analysis, "claim_type", None) == "mechanism":
        return True
    if (getattr(cur_analysis, "secondary_claim_type", None) or "") == "mechanism":
        return True
    return False


def _heuristic_fit_accept(paper: Paper, claim: str, paper_title: str) -> bool:
    """概念/进展/定义类论点 + 标题明确护士隐性缺勤 → 视为可引用（避免 LLM 过严误杀）。"""
    t = paper.title or ""
    c = (claim or "") + " " + (paper_title or "")
    definitional = any(
        k in c
        for k in (
            "研究进展",
            "概念",
            "内涵",
            "定义",
            "综述",
            "理论基础",
            "起源",
            "核心内涵",
            "生产力",
            "生产力损失",
            "影响因素",
            "现状",
        )
    )
    if not definitional:
        return False
    if "隐性缺勤" not in t and "带病" not in t and "出勤" not in t:
        if "presenteeism" not in t.lower():
            return False
    return any(
        k in t
        for k in (
            "护士",
            "护理人员",
            "医务人员",
            "医护",
            "护理",
            "临床护士",
            "ICU护士",
        )
    )


def _ensure_nursing_query(query: str, target_lang: str, scope_nursing: bool) -> str:
    """护理类论文：检索式强制带上护士/nurse，减少错人群结果。"""
    if not scope_nursing or not (query or "").strip():
        return query
    q = query.strip()
    if target_lang == "cn":
        if any(m in q for m in _NURSING_QUERY_MARKERS):
            return q
        return f"{q} 护士"
    ql = q.lower()
    if re.search(r"\b(nurse|nursing|midwif)\b", ql):
        return q
    return f"{q} nurse"


@dataclass
class TopicAnchors:
    """论文主题锚定词（LLM 动态提取）"""
    topic_cn: str = ""
    topic_en: str = ""
    population_cn: str = ""
    population_en: str = ""


def _extract_topic_entities(paper_title: str, analyzer=None) -> TopicAnchors:
    """用 LLM 从论文标题动态提取核心主题词和人群词。"""
    if not paper_title:
        return TopicAnchors()

    if analyzer is None:
        from modules.reference.content_analyzer import ContentAnalyzer
        analyzer = ContentAnalyzer()

    prompt = f"""从以下论文标题中提取 **2个核心实体**，用于限定文献检索范围。

论文标题：{paper_title}

提取规则：
1. **topic（核心主题）**：论文核心疾病名、核心变量名或研究对象。**只提取最核心的1个名词短语**，不超过6个字/3个英文单词。
   - 例：肺炎支原体 → Mycoplasma pneumoniae（不要写成「儿童重症肺炎支原体肺炎」）
   - 例：隐性缺勤 → presenteeism（注意：隐性缺勤=presenteeism，不是absenteeism）
   - 例：深度学习 → deep learning
   - 例：认知功能障碍 → cognitive dysfunction
2. **population（人群）**：研究对象/人群，**只填1个词**。无明确人群则留空。
   - 例：儿童 → children, 护士 → nurses, 老年患者 → elderly patients

返回 JSON：
{{
  "topic_cn": "最短的中文核心词",
  "topic_en": "shortest English term",
  "population_cn": "人群词或空",
  "population_en": "population or empty"
}}"""

    try:
        import json
        resp = analyzer.client.chat.completions.create(
            model=analyzer.model,
            messages=[
                {"role": "system", "content": "你是学术检索专家，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )
        data = json.loads(resp.choices[0].message.content.strip())
        return TopicAnchors(
            topic_cn=(data.get("topic_cn") or "").strip(),
            topic_en=(data.get("topic_en") or "").strip(),
            population_cn=(data.get("population_cn") or "").strip(),
            population_en=(data.get("population_en") or "").strip(),
        )
    except Exception as e:
        print(f"[TopicAnchors] LLM 提取失败: {e}")
        return TopicAnchors()


def _ensure_topic_query(query: str, target_lang: str,
                        anchors: TopicAnchors, paper_title: str) -> str:
    """检查搜索词是否包含论文核心主题词，缺失则注入。
    
    限制注入后总 token 数不超过 5，避免 CNKI 过严查询。
    """
    if not query or not query.strip():
        return query
    q = query.strip()
    token_count = len(q.split())
    max_tokens = 5

    if target_lang == "cn":
        topic = anchors.topic_cn
        pop = anchors.population_cn
        if topic and topic not in q and token_count < max_tokens:
            q = f"{q} {topic}"
            token_count += 1
        if pop and pop not in q and pop not in (topic or "") and token_count < max_tokens - 1:
            q = f"{q} {pop}"
    else:
        ql = q.lower()
        topic = anchors.topic_en
        pop = anchors.population_en
        if topic and topic.lower() not in ql and token_count < max_tokens:
            q = f"{q} {topic}"
            token_count += len(topic.split())
        if pop and pop.lower() not in ql and pop.lower() not in (topic or "").lower() and token_count < max_tokens:
            q = f"{q} {pop}"
    return q


def _effective_cnki_pages(claim_type: str, base_pages: int, fast_mode: bool) -> int:
    """政策/概念类论点多翻知网，提高召回。"""
    ct = claim_type or "status_quo"
    if ct in ("policy_macro", "concept_definition"):
        bump = 1 if fast_mode else 2
        return min(base_pages + bump, 6)
    return base_pages


def _rank_keywords_for_analysis(cur_analysis) -> list[str]:
    k = rank_keywords_from_analysis(cur_analysis)
    if k:
        return k
    return list(cur_analysis.cn_keywords or []) + list(cur_analysis.en_keywords or [])


def _enrich_queries_for_claim_type(cn_q: str, en_q: str, claim_type: str) -> tuple[str, str]:
    """宏观政策类：强化中文政策词与英文 Healthy China 交叉检索。"""
    cn = (cn_q or "").strip()
    en = (en_q or "").strip()
    ct = claim_type or "status_quo"
    if ct == "policy_macro":
        if "健康中国" not in cn:
            cn = f"{cn} 健康中国".strip()
        if "战略" not in cn and "卫生人才" not in cn:
            cn = f"{cn} 战略".strip()
        if not re.search(r"healthy\s*china|healthcare\s+workforce|health\s+policy", en, re.I):
            en = f"{en} Healthy China healthcare workforce".strip()
    return cn, en


def _append_reference_match_log(
    cid: int,
    key_claim: str,
    paper_title: str,
    status: str,
    chosen_title: str = "",
    journal: str = "",
    claim_type: str = "",
    match_tier: str = "",
    claim_confidence: Optional[float] = None,
) -> None:
    """反馈闭环：追加 JSONL，便于后续分析误配/漏配。"""
    try:
        root = Path(__file__).resolve().parent.parent.parent
        logd = root / "logs"
        logd.mkdir(parents=True, exist_ok=True)
        path = logd / "reference_matches.jsonl"
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "marker_id": cid,
            "paper_title": paper_title[:200],
            "key_claim": (key_claim or "")[:500],
            "status": status,
            "chosen_title": (chosen_title or "")[:300],
            "journal": (journal or "")[:120],
        }
        if claim_type:
            rec["claim_type"] = claim_type[:40]
        if match_tier:
            rec["match_tier"] = match_tier[:24]
        if claim_confidence is not None:
            rec["claim_confidence"] = round(float(claim_confidence), 3)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def deduplicate_papers(papers: list[Paper]) -> list[Paper]:
    seen_dois: dict[str, Paper] = {}
    seen_titles: dict[str, Paper] = {}
    result = []
    for p in papers:
        if p.doi:
            doi_lower = p.doi.lower()
            if doi_lower in seen_dois:
                existing = seen_dois[doi_lower]
                if (p.citation_count or 0) > (existing.citation_count or 0):
                    try:
                        result.remove(existing)
                    except ValueError:
                        pass
                    result.append(p)
                    seen_dois[doi_lower] = p
                continue
            seen_dois[doi_lower] = p
        title_key = p.title.lower().strip()[:50]
        if title_key in seen_titles:
            continue
        seen_titles[title_key] = p
        result.append(p)
    return result


def _search_source(searcher, query, year_start, year_end, limit, label):
    try:
        papers = searcher.search(query, year_start, year_end, limit)
        return label, papers
    except Exception:
        return label, []


def _search_cnki(
    searcher,
    query,
    year_start,
    year_end,
    limit,
    field_cn_cores,
    label,
    max_pages: int = 2,
):
    try:
        papers = searcher.search(
            query,
            year_start,
            year_end,
            limit,
            max_pages=max_pages,
            field_cn_cores=field_cn_cores,
        )
        return label, papers
    except Exception:
        return label, []


def process_paper(
    docx_path: str,
    year_start: int = None,
    year_end: int = None,
    results_per_source: int = 5,
    top_k: int = 1,
    cn_ratio: float = 0.25,
    callback=None,
    progress_callback=None,
    paper_title: str = "",
    fast_mode: bool = False,
    sequential_en_search: Optional[bool] = None,
    max_markers: Optional[int] = None,
    lang_fallback: Optional[bool] = None,
    skip_pool_fallback: Optional[bool] = None,
    policy_cn_only: Optional[bool] = None,
    policy_allow_en_fallback: Optional[bool] = None,
    nursing_hard_scope: Optional[bool] = None,
):
    """处理论文主流程

    Args:
        cn_ratio: 中文文献占比 (0.25 = 1:3 中英文比例)
        progress_callback: 进度回调 progress_callback(current, total, status_text)
        fast_mode: True 时 CNKI 少翻页、fit 批量略小，整体更快，检索覆盖面略降
        sequential_en_search: True 时英文库顺序检索（OpenAlex→CrossRef→PubMed），单源试匹配成功即停；
            None 时读取环境变量 / 配置 REFERENCE_SEQUENTIAL_EN_SEARCH
        max_markers: 若设置正整数，仅按编号升序处理前 N 个角标（用于试跑/测速）
        lang_fallback: 主语言无匹配时是否改试另一语种检索；None 时用 REFERENCE_LANG_FALLBACK
        skip_pool_fallback: True 时跳过角标内第四轮「候选池合并再 fit」；None 时用 REFERENCE_SKIP_POOL_FALLBACK
        policy_cn_only: policy_macro 是否固定走中文检索（忽略角标随机中英分配）；None 时用 REFERENCE_POLICY_CN_ONLY
        policy_allow_en_fallback: policy_macro 在中文无果后是否允许改试英文；None 时用 REFERENCE_POLICY_ALLOW_EN_FALLBACK
        nursing_hard_scope: 护理题下是否启用人群/情境硬过滤与检索式护士限定；False 时仅保留基础垃圾过滤与 LLM fit；None 时用 REFERENCE_NURSING_HARD_SCOPE
    """
    if year_start is None:
        year_start = YEAR_RANGE[0]
    if year_end is None:
        year_end = YEAR_RANGE[1]

    seq_en = (
        sequential_en_search
        if sequential_en_search is not None
        else REFERENCE_SEQUENTIAL_EN_SEARCH
    )
    lf_on = (
        lang_fallback if lang_fallback is not None else REFERENCE_LANG_FALLBACK
    )
    rescue_cn_en_fb = REFERENCE_RESCUE_CN_FALLBACK_EN
    skip_pool_fb = (
        skip_pool_fallback
        if skip_pool_fallback is not None
        else REFERENCE_SKIP_POOL_FALLBACK
    )
    pol_cn_only = (
        policy_cn_only
        if policy_cn_only is not None
        else REFERENCE_POLICY_CN_ONLY
    )
    pol_en_fb = (
        policy_allow_en_fallback
        if policy_allow_en_fallback is not None
        else REFERENCE_POLICY_ALLOW_EN_FALLBACK
    )
    nh_hard = (
        nursing_hard_scope
        if nursing_hard_scope is not None
        else REFERENCE_NURSING_HARD_SCOPE
    )

    def log(msg):
        if callback:
            try:
                callback(msg)
            except InterruptedError:
                raise
            except Exception:
                pass
        else:
            try:
                print(msg)
            except Exception:
                pass

    total_start = time.time()

    log("Step 1: 解析 Word 文档...")
    parser = DocParser(docx_path)
    if not paper_title:
        paper_title = parser.get_title()
    grouped = parser.extract_markers_grouped()
    log(f"  论文标题: {paper_title}")
    full_marker_count = len(grouped)
    log(
        f"  发现 {full_marker_count} 个唯一角标编号（[1]、[2,3] 等同号只计一次）: "
        f"{list(grouped.keys())}"
    )
    if max_markers is not None and max_markers > 0 and full_marker_count > max_markers:
        take_ids = sorted(grouped.keys())[:max_markers]
        grouped = {k: grouped[k] for k in take_ids}
        tail = "…" if len(take_ids) > 12 else ""
        log(
            f"  [限制] 文档共 {full_marker_count} 个角标，本次仅处理前 {len(grouped)} 个（按编号）: "
            f"{take_ids[:12]}{tail}"
        )

    if not grouped:
        return {}, "", ""

    # 语种分配：先由 LLM 推荐，预分析完成后按比例调整
    import math
    total = len(grouped)
    target_cn = max(1, math.ceil(total * cn_ratio))
    target_en = total - target_cn
    lang_map: dict[int, str] = {k: "en" for k in grouped}  # 占位，预分析后覆盖
    log(f"  目标比例: 中文{target_cn}篇 英文{target_en}篇")

    analyzer = ContentAnalyzer()
    crossref = CrossRefSearcher()
    openalex = OpenAlexSearcher()
    pubmed = PubMedSearcher()
    cnki = CNKISearcher()
    ranker = RelevanceRanker()

    # Step 1.5: 根据论文标题分析领域，获取推荐核心期刊
    field_analyzer = FieldAnalyzer()
    log("Step 1.5: 分析论文领域与核心期刊...")
    field_info = field_analyzer.analyze(paper_title)
    cn_cores, en_cores = build_journal_set(field_info)
    log(f"  领域: {field_info.get('field', '未知')}")
    log(f"  推荐中文核心: {len(cn_cores)} 个, 英文核心: {len(en_cores)} 个")
    all_field_cores = cn_cores | en_cores

    log("Step 1.6: LLM 提取论文主题锚定词...")
    topic_anchors = _extract_topic_entities(paper_title, analyzer)
    if topic_anchors.topic_cn or topic_anchors.population_cn:
        parts = []
        if topic_anchors.topic_cn:
            parts.append(f"主题={topic_anchors.topic_cn}/{topic_anchors.topic_en}")
        if topic_anchors.population_cn:
            parts.append(f"人群={topic_anchors.population_cn}/{topic_anchors.population_en}")
        log(f"  [主题锚定] {', '.join(parts)}")

    scope_detect = _thesis_nursing_scope(paper_title)
    scope_nursing = scope_detect and nh_hard
    if scope_detect:
        if nh_hard:
            log("  [策略] 护理/医务类题目：启用人群与情境硬过滤 + 检索护士/nurse 限定 + LLM 引用 fit 校验")
        else:
            log("  [策略] 护理/医务类题目：已关闭人群与情境硬过滤与护士检索限定（仅基础去噪 + LLM fit），便于对比测试")
    cnki_max_pages = 1 if fast_mode else 2
    verify_batch_size = 10 if fast_mode else 12
    if fast_mode:
        log("  [快速模式] CNKI max_pages=1，fit 批量=6")
    if seq_en:
        log("  [策略] 英文库顺序检索+早停已开启（单源匹配成功即不再请求后续英文源）")
    if lf_on:
        log("  [策略] 跨语言降级已开启：主分配语种无匹配时自动改试另一语种")
    if skip_pool_fb:
        log("  [策略] 已关闭候选池兜底（第四轮），主/次语种流程内不再从累计池强选")

    import threading
    references: dict[int, Paper] = {}
    used_dois: set[str] = set()
    used_titles: set[str] = set()
    _dedup_lock = threading.Lock()
    analysis_cache: dict[str, object] = {}
    deep_fit_cache: dict[str, bool] = {}
    mechanism_tier_cache: dict[str, str] = {}

    marker_list = list(grouped.items())
    total_markers = len(marker_list)

    # === 预并行：LLM 分析阶段（批 3 并发，省等待时间）===
    def _do_analyze(cid_marker):
        cid, marker = cid_marker
        ck = marker.context_before.strip()[:100]
        if ck in analysis_cache:
            return cid, analysis_cache[ck], None
        try:
            a = analyzer.analyze(
                marker_id=str(cid),
                paragraph=marker.paragraph_text,
                context_before=marker.context_before,
                paper_title=paper_title,
            )
            return cid, a, None
        except Exception as e:
            return cid, None, e

    log("Step 2: 预并行 LLM 分析…")
    with ThreadPoolExecutor(max_workers=3) as _apool:
        _afuts = [_apool.submit(_do_analyze, item) for item in marker_list]
        for f in as_completed(_afuts):
            _cid, _ar, _err = f.result()
            if _ar is not None:
                ck = grouped[_cid].context_before.strip()[:100]
                analysis_cache[ck] = _ar
            elif _err is not None:
                log(f"  [预分析] 角标[{_cid}] 失败: {_err}")
    log(f"  预分析完成: {len(analysis_cache)} 条缓存")

    # Step 2.5: 用 LLM recommended_lang 填充 lang_map，再按 cn_ratio 调整
    for cid in grouped:
        ck = grouped[cid].context_before.strip()[:100]
        ar = analysis_cache.get(ck)
        if ar:
            lang_map[cid] = getattr(ar, "recommended_lang", "en") or "en"
        else:
            lang_map[cid] = "en"

    llm_cn = [k for k, v in lang_map.items() if v == "cn"]
    llm_en = [k for k, v in lang_map.items() if v == "en"]
    log(f"  LLM 推荐: 中文{len(llm_cn)}篇 英文{len(llm_en)}篇")

    def _cn_signal_score(cid_: int) -> float:
        """角标的中文信号强度，越高越适合分配到中文。"""
        ck_ = grouped[cid_].context_before.strip()[:100]
        ar_ = analysis_cache.get(ck_)
        score = 0.0
        ctx_ = grouped[cid_].context_before or ""
        if re.search(r"[\u4e00-\u9fff]{2,4}等(?:研究|发现|报道|认为|指出)?", ctx_):
            score += 3.0
        if "《" in ctx_ and "》" in ctx_:
            score += 3.0
        if re.search(r"我国|国内|中国|某(?:省|市|院|医院)", ctx_):
            score += 2.0
        if ar_:
            ct_ = getattr(ar_, "claim_type", "") or ""
            if ct_ in ("policy_macro", "concept_definition"):
                score += 1.5
            elif ct_ == "status_quo":
                score += 0.5
            cn_auth = any(
                re.search(r"[\u4e00-\u9fff]", a or "")
                for a in (getattr(ar_, "ref_authors", []) or [])
            )
            if cn_auth:
                score += 2.5
        return score

    # 按 cn_ratio 调整：多退少补（智能选择）
    if len(llm_cn) > target_cn:
        excess = len(llm_cn) - target_cn
        scored = sorted(llm_cn, key=_cn_signal_score)
        to_flip = scored[:excess]
        for k in to_flip:
            lang_map[k] = "en"
        log(f"  [比例调整] 中文超额{excess}篇→翻转信号最弱的为英文: {to_flip[:8]}{'…' if excess > 8 else ''}")
    elif len(llm_cn) < target_cn:
        deficit = target_cn - len(llm_cn)
        scored = sorted(llm_en, key=_cn_signal_score, reverse=True)
        to_flip = scored[:min(deficit, len(scored))]
        for k in to_flip:
            lang_map[k] = "cn"
        log(f"  [比例调整] 中文不足{deficit}篇→翻转信号最强的为中文: {to_flip[:8]}{'…' if deficit > 8 else ''}")

    final_cn = [k for k, v in lang_map.items() if v == "cn"]
    final_en = [k for k, v in lang_map.items() if v == "en"]
    log(f"  最终分配: 中文{len(final_cn)}篇 英文{len(final_en)}篇")

    _parallel_search = 3
    log(f"Step 3: 检索匹配（{_parallel_search} 并发）…")

    def _process_one_marker(marker_idx, cid, marker):
        """处理单个角标的全部搜索+匹配流程。"""
        nonlocal references
        marker_start = time.time()
        assigned_lang = lang_map[cid]
        lang_label = "中文" if assigned_lang == "cn" else "英文"

        log(f"\n[{cid}] ({lang_label}) {marker_idx+1}/{total_markers}")

        cache_key = marker.context_before.strip()[:100]
        if cache_key not in analysis_cache:
            log(f"  分析失败（预分析阶段），跳过")
            return
        analysis = analysis_cache[cache_key]
        _ct0 = getattr(analysis, "claim_type", None) or "status_quo"
        _cf0 = getattr(analysis, "claim_confidence", 1.0)
        _sec0 = getattr(analysis, "secondary_claim_type", "") or ""
        _sec0s = f" sec={_sec0}" if _sec0 else ""
        log(f"  分析: {getattr(analysis, 'core_topic', '')[:40]} [{_ct0} conf={_cf0:.2f}{_sec0s}]")

        ct = getattr(analysis, "claim_type", None) or "status_quo"
        eff_pages = _effective_cnki_pages(ct, cnki_max_pages, fast_mode)
        ref_rt = resolve_ref_type_for_marker(analysis, marker.context_before or "")
        _rth = (getattr(analysis, "ref_type_hint", "") or "").strip()
        rec_lang = getattr(analysis, "recommended_lang", None) or assigned_lang
        log(
            f"  ref_type: {ref_rt} | 分配: {'中' if assigned_lang == 'cn' else '英'} | "
            f"LLM推荐: {'中' if rec_lang == 'cn' else '英'}"
            + (f" — {_rth}" if _rth else "")
        )

        best = None
        max_search_rounds = 5
        match_round = 0
        target_lang = assigned_lang

        # --- 论点缓存：检索前先查 DB 是否已有命中 ---
        _claim_for_cache = getattr(analysis, "key_claim", "") or ""
        _cached_paper = get_cached_paper_for_claim(paper_title, _claim_for_cache)
        if _cached_paper is not None:
            with _dedup_lock:
                _ck_doi = _cached_paper.doi.lower() if _cached_paper.doi else None
                _ck_tk = _cached_paper.title.lower().strip()[:50]
                if (_ck_doi and _ck_doi in used_dois) or _ck_tk in used_titles:
                    pass
                else:
                    best = _cached_paper
                    references[cid] = best
                    if _ck_doi:
                        used_dois.add(_ck_doi)
                    used_titles.add(_ck_tk)
            if best:
                is_cn = _is_chinese_title(best.title)
                elapsed = time.time() - marker_start
                log(f"  [缓存命中] [{elapsed:.1f}s] {'[中]' if is_cn else '[英]'} {best.title[:55]}")
                log(f"    DOI: {best.doi} | {best.journal} | {best.year}")
                _append_reference_match_log(
                    cid, _claim_for_cache, paper_title, "ok",
                    best.title, best.journal or "", claim_type=ct,
                )
                return

        ctx_text = marker.context_before or ""
        if ref_rt in ("R", "EB") and "《" in ctx_text and "》" in ctx_text:
            from modules.reference.llm_ref_generator import try_web_search_for_quoted_title
            log(f"  [策略] ref_type={ref_rt} + 《…》：直接搜网页")
            best = try_web_search_for_quoted_title(ctx_text, ref_rt, analysis.key_claim or "")
            if best:
                log(f"  [DuckDuckGo] 命中: {best.title[:50]} | {best.url or ''}")

        lang_attempts: list[str] = [assigned_lang]
        if lf_on:
            _alt = "en" if assigned_lang == "cn" else "cn"
            lang_attempts.append(_alt)

        for att_i, try_lang in enumerate(lang_attempts):
            if best is not None:
                break
            if att_i > 0:
                log(
                    f"  [跨语言降级] 分配为{'中文' if assigned_lang == 'cn' else '英文'}角标位但未匹配，"
                    f"改试{'中文' if try_lang == 'cn' else '英文'}库…"
                )

            def _do_search(query: str) -> list[Paper]:
                """单轮搜索：根据 try_lang 选库。CNKI 空结果时自动缩词重试。"""
                cands: list[Paper] = []
                if try_lang == "cn":
                    _, rp = _search_cnki(
                        cnki, query, year_start, year_end,
                        results_per_source * 2, cn_cores, "CNKI",
                        eff_pages,
                    )
                    if rp:
                        log(f"    CNKI: {len(rp)}篇")
                        cands.extend(rp)
                    elif query.strip():
                        tokens = query.strip().split()
                        if len(tokens) > 3:
                            short_q = " ".join(tokens[:3])
                            log(f"    CNKI 0结果，缩词重试: {short_q}")
                            _, rp2 = _search_cnki(
                                cnki, short_q, year_start, year_end,
                                results_per_source * 2, cn_cores, "CNKI-缩词",
                                eff_pages,
                            )
                            if rp2:
                                log(f"    CNKI(缩词): {len(rp2)}篇")
                                cands.extend(rp2)
                        if not cands and len(tokens) > 2:
                            short_q2 = " ".join(tokens[:2])
                            log(f"    CNKI 再缩词: {short_q2}")
                            _, rp3 = _search_cnki(
                                cnki, short_q2, year_start, year_end,
                                results_per_source * 2, cn_cores, "CNKI-2词",
                                eff_pages,
                            )
                            if rp3:
                                log(f"    CNKI(2词): {len(rp3)}篇")
                                cands.extend(rp3)
                else:
                    light = use_light_english_sources(ref_rt)
                    lim = min(results_per_source, 5) if light else results_per_source
                    sources = [(openalex, "OpenAlex"), (crossref, "CrossRef")]
                    if not light:
                        sources.append((pubmed, "PubMed"))
                    with ThreadPoolExecutor(max_workers=3) as pool:
                        futs = [
                            pool.submit(_search_source, s, query, year_start, year_end, lim, lbl)
                            for s, lbl in sources
                        ]
                        for f in as_completed(futs):
                            lbl, papers = f.result()
                            if papers:
                                log(f"    {lbl}: {len(papers)}篇")
                                cands.extend(papers)
                return cands

            def _pick_best(candidates: list[Paper]) -> Optional[Paper]:
                """去重 + 过滤 + fast_rank + 轻量 LLM fit（前6名批量一次判断）。

                fit 通过 → 返回。fit 全否 → 返回 None（触发 refine 重搜）。
                """
                candidates = deduplicate_papers(candidates)
                candidates = [
                    p for p in candidates
                    if not (p.doi and p.doi.lower() in used_dois)
                    and p.title.lower().strip()[:50] not in used_titles
                    and _paper_passes_content_scope(p, try_lang, scope_nursing)
                ]
                if try_lang == "cn":
                    lang_f = [p for p in candidates if _is_chinese_title(p.title)]
                    candidates = lang_f or candidates
                else:
                    lang_f = [p for p in candidates if not _is_chinese_title(p.title)]
                    candidates = lang_f or candidates
                if not candidates:
                    return None
                ranked = fast_rank(
                    context=marker.context_before,
                    keywords=_rank_keywords_for_analysis(analysis),
                    candidates=candidates,
                    top_k=8,
                    field_cores=all_field_cores,
                    claim=analysis.key_claim or "",
                )
                if not ranked:
                    return None
                top_n = ranked[:6]
                try:
                    fits = ranker.verify_fit_batch(
                        marker.context_before,
                        analysis.key_claim or "",
                        top_n,
                        paper_title,
                        claim_type=ct,
                        secondary_claim_type=getattr(analysis, "secondary_claim_type", "") or "",
                    )
                    for p, ok in zip(top_n, fits):
                        if ok:
                            return p
                    # fit 全否 → 返回 None 让外层 refine 重搜
                    log(f"    fit 全否（{len(top_n)}篇）")
                    return None
                except Exception:
                    return ranked[0]

            # 第一轮：检索轨道构建的检索词
            _base_cn, _base_en = build_search_queries_from_analysis(analysis)
            q = _base_cn if try_lang == "cn" else _base_en
            if not q:
                q = _base_en if try_lang == "cn" else _base_cn
            q = _ensure_nursing_query(q, try_lang, scope_nursing)
            q = _ensure_topic_query(q, try_lang, topic_anchors, paper_title)

            tried_queries: list[str] = []
            last_cands: list[Paper] = []
            for round_i in range(max_search_rounds):
                if best is not None:
                    break
                if not q or q in tried_queries:
                    break
                tried_queries.append(q)
                log(f"  [轮{round_i+1}] 搜索: {q[:50]}")

                cands = _do_search(q)
                if cands:
                    last_cands = cands
                    best = _pick_best(cands)
                    if best:
                        target_lang = try_lang
                        match_round = round_i + 1
                        break

                rejected_titles = [p.title[:60] for p in (cands or last_cands)[:6]]
                log(
                    f"  [轮{round_i+1}] 未命中"
                    + (f"（搜到{len(cands)}篇但fit否）" if cands else "（0结果）")
                )

                if round_i < max_search_rounds - 1:
                    try:
                        new_cn, new_en = analyzer.refine_search(
                            analysis, q, rejected_titles,
                            target_lang=try_lang, paper_title=paper_title,
                        )
                        q = (new_cn if try_lang == "cn" else new_en) or ""
                        q = _ensure_nursing_query(q, try_lang, scope_nursing)
                        q = _ensure_topic_query(q, try_lang, topic_anchors, paper_title)
                        if not q:
                            q = (new_en if try_lang == "cn" else new_cn) or ""
                    except Exception:
                        break

        if best:
            with _dedup_lock:
                tk = best.title.lower().strip()[:50]
                dk = best.doi.lower() if best.doi else None
                if (dk and dk in used_dois) or tk in used_titles:
                    log(f"  [去重冲突] 已被其他并行角标使用，跳过")
                    best = None
                else:
                    references[cid] = best
                    if dk:
                        used_dois.add(dk)
                    used_titles.add(tk)
            is_cn = _is_chinese_title(best.title)
            elapsed = time.time() - marker_start
            if target_lang != assigned_lang:
                log(
                    f"  [降级命中] 使用{'英文' if target_lang == 'en' else '中文'}文献"
                    f"（原分配为{'中文' if assigned_lang == 'cn' else '英文'}角标位）"
                )
            log(f"  [OK] [{elapsed:.1f}s] [轮{match_round}] {'[中]' if is_cn else '[英]'} {best.title[:55]}")
            rt = getattr(best, "reference_type", "J")
            if rt == "EB/OL":
                log(f"    [EB/OL] {best.journal or ''} | {best.url or ''}")
            elif rt == "M":
                log(f"    [M] 专著题名已固定 | 出版项待补")
            else:
                log(f"    DOI: {best.doi} | {best.journal} | {best.year}")
            _append_reference_match_log(
                cid,
                analysis.key_claim,
                paper_title,
                "ok",
                best.title,
                best.journal or "",
                claim_type=ct,
                match_tier="",
                claim_confidence=getattr(analysis, "claim_confidence", None),
            )
            save_cached_match(paper_title, analysis.key_claim or "", best, "ok", ct)
        if not best:
            log(f"  [MISS] 无匹配")
            _append_reference_match_log(
                cid,
                analysis.key_claim,
                paper_title,
                "miss",
                claim_type=ct,
                claim_confidence=getattr(analysis, "claim_confidence", None),
            )

    # 分批并行处理所有角标
    for batch_start in range(0, total_markers, _parallel_search):
        batch = marker_list[batch_start : batch_start + _parallel_search]
        if progress_callback:
            progress_callback(
                batch_start, total_markers,
                f"处理角标 {batch_start+1}-{min(batch_start+_parallel_search, total_markers)}/{total_markers}"
            )
        if len(batch) == 1:
            idx = batch_start
            cid, marker = batch[0]
            _process_one_marker(idx, cid, marker)
        else:
            with ThreadPoolExecutor(max_workers=_parallel_search) as pool:
                futs = []
                for i, (cid, marker) in enumerate(batch):
                    futs.append(pool.submit(_process_one_marker, batch_start + i, cid, marker))
                for f in as_completed(futs):
                    try:
                        f.result()
                    except Exception as e:
                        log(f"  [并行错误] {e}")

    # === 《…》网页搜索兜底：对含书名号但学术库未命中的角标，用 DuckDuckGo 搜索真实来源 ===
    missing_ids = [cid for cid in grouped if cid not in references]
    if missing_ids:
        from modules.reference.llm_ref_generator import try_web_search_for_quoted_title

        quoted_rescued = []
        for cid in list(missing_ids):
            marker = grouped[cid]
            ctx = marker.context_before or ""
            if "《" not in ctx or "》" not in ctx:
                continue
            cache_key = ctx.strip()[:100]
            _ma = analysis_cache.get(cache_key)
            _rt = (
                resolve_ref_type_for_marker(_ma, ctx) if _ma else "M"
            )
            if _rt not in ("R", "EB", "M"):
                continue
            log(f"\n  [《…》搜索] 角标[{cid}] ref_type={_rt}，搜索网页真实来源…")
            gen = try_web_search_for_quoted_title(
                ctx, _rt, getattr(_ma, "key_claim", "") or ""
            )
            if gen is not None:
                log(f"    DuckDuckGo 命中: {gen.title[:50]} | {gen.url or ''}")
                references[cid] = gen
                if gen.doi:
                    used_dois.add(gen.doi.lower())
                used_titles.add(gen.title.lower().strip()[:50])
                _rt_label = getattr(gen, "reference_type", "")
                log(
                    f"  [《…》搜索OK] [{_rt_label}] {gen.title[:50]}"
                    + (f" | {gen.url}" if gen.url else "")
                )
                quoted_rescued.append(cid)
            else:
                log(f"    DuckDuckGo 未命中")
        if quoted_rescued:
            missing_ids = [cid for cid in missing_ids if cid not in quoted_rescued]

    # === 最终补救：对仍未匹配的角标，逐个用论点关键词精准搜索 ===
    if missing_ids:
        log(f"\n--- 最终补救: {len(missing_ids)} 个角标未匹配 ---")
        from modules.reference.core_journals import is_core_journal

        for cid in missing_ids:
            marker = grouped[cid]
            target_lang_m = lang_map[cid]
            rescue_meta: dict[str, str] = {"match_tier": ""}

            cache_key = marker.context_before.strip()[:100]
            miss_analysis = analysis_cache.get(cache_key)
            miss_claim_ct = (
                getattr(miss_analysis, "claim_type", None) or "status_quo"
                if miss_analysis
                else "status_quo"
            )
            miss_secondary = (
                getattr(miss_analysis, "secondary_claim_type", None) or ""
                if miss_analysis
                else ""
            )
            rescue_pages = _effective_cnki_pages(miss_claim_ct, cnki_max_pages, fast_mode)

            quote_rescue = quoted_title_source_lang(marker.context_before or "")
            base_rescue_lang = quote_rescue if quote_rescue else target_lang_m
            miss_ref_rt = (
                resolve_ref_type_for_marker(miss_analysis, marker.context_before or "")
                if miss_analysis
                else "J"
            )
            rescue_attempts: list[str] = [base_rescue_lang]
            if (
                quote_rescue == "cn"
                and lf_on
                and rescue_cn_en_fb
                and "en" not in rescue_attempts
            ):
                rescue_attempts.append("en")

            if quote_rescue:
                extra_hint = (
                    "；若无合格文献将改试英文库"
                    if len(rescue_attempts) > 1
                    else ""
                )
                log(
                    f"  [补救] 书名号题名判定为{'中文' if quote_rescue == 'cn' else '英文'}，"
                    f"补救优先{'知网' if quote_rescue == 'cn' else '英文库'}{extra_hint}"
                )

            best_p = None
            for attempt_i, rescue_lang in enumerate(rescue_attempts):
                if attempt_i > 0:
                    log(f"  [补救] 角标[{cid}] 知网路径未命中，改试英文库…")

                # 用该角标自身的论点搜索，而不是泛领域词
                if miss_analysis:
                    _mr_cn, _mr_en = build_search_queries_from_analysis(miss_analysis)
                    if rescue_lang == "cn":
                        _rq0 = _ensure_nursing_query(_mr_cn, "cn", scope_nursing)
                        _en_side = _mr_en or (
                            miss_analysis.search_query_en
                            or " ".join(miss_analysis.en_keywords[:2])
                        )
                        rescue_q, _ = adjust_queries_for_ref_type(
                            _rq0,
                            _en_side,
                            miss_ref_rt,
                            marker.context_before or "",
                        )
                        rescue_q = _ensure_nursing_query(rescue_q, "cn", scope_nursing)
                        rescue_q2 = _ensure_nursing_query(paper_title, "cn", scope_nursing)
                    else:
                        _rqe0 = _ensure_nursing_query(_mr_en, "en", scope_nursing)
                        _cn_side = _mr_cn or (
                            miss_analysis.search_query_cn
                            or " ".join(miss_analysis.cn_keywords[:2])
                        )
                        _, rescue_q = adjust_queries_for_ref_type(
                            _cn_side,
                            _rqe0,
                            miss_ref_rt,
                            marker.context_before or "",
                        )
                        rescue_q = _ensure_nursing_query(rescue_q, "en", scope_nursing)
                        _e2tok = (
                            list(miss_analysis.ref_title_keywords_en or [])[:2]
                            + list(miss_analysis.en_keywords or [])[:2]
                        )
                        rescue_q2 = _ensure_nursing_query(
                            (" ".join(_e2tok) + " nurse").strip()
                            if _e2tok
                            else "nurse",
                            "en",
                            scope_nursing,
                        )
                else:
                    _ta_en = (
                        " ".join(
                            x
                            for x in (
                                topic_anchors.topic_en,
                                topic_anchors.population_en,
                            )
                            if x
                        ).strip()
                    )
                    rescue_q = (
                        _ensure_nursing_query(paper_title, "cn", scope_nursing)
                        if rescue_lang == "cn"
                        else _ensure_nursing_query(
                            _ta_en or (paper_title or "clinical"),
                            "en",
                            scope_nursing,
                        )
                    )
                    rescue_q2 = rescue_q

                rescue_cands: list[Paper] = []
                for rq in [rescue_q, rescue_q2]:
                    if not rq:
                        continue
                    try:
                        if rescue_lang == "cn":
                            _, rp = _search_cnki(
                                cnki,
                                rq,
                                year_start,
                                year_end,
                                20,
                                cn_cores,
                                f"补救-{cid}",
                                rescue_pages,
                            )
                        else:
                            _, rp1 = _search_source(crossref, rq, year_start, year_end, 10, f"补救CR-{cid}")
                            _, rp2 = _search_source(openalex, rq, year_start, year_end, 10, f"补救OA-{cid}")
                            rp = (rp1 or []) + (rp2 or [])
                        if rp:
                            rescue_cands.extend(rp)
                    except Exception:
                        pass

                rescue_cands = deduplicate_papers(rescue_cands)
                available = [
                    p for p in rescue_cands
                    if not (p.doi and p.doi.lower() in used_dois)
                    and p.title.lower().strip()[:50] not in used_titles
                    and _paper_passes_content_scope(p, rescue_lang, scope_nursing)
                ]
                if rescue_lang == "cn":
                    lang_avail = [p for p in available if _is_chinese_title(p.title)]
                    if lang_avail:
                        available = lang_avail
                else:
                    lang_avail = [p for p in available if not _is_chinese_title(p.title)]
                    if lang_avail:
                        available = lang_avail

                attempt_best = None
                if available and miss_analysis:
                    claim_u = miss_analysis.key_claim
                    pre_res = fast_rank(
                        context=marker.context_before,
                        keywords=_rank_keywords_for_analysis(miss_analysis),
                        candidates=available,
                        top_k=12,
                        field_cores=all_field_cores,
                        claim=claim_u or "",
                    )
                    try:
                        llm_res = ranker.rank(
                            context=marker.context_before,
                            claim=miss_analysis.key_claim,
                            candidates=pre_res,
                            top_k=8,
                            paper_title=paper_title,
                            min_score=3,
                        )
                    except Exception:
                        llm_res = []
                    order = llm_res if llm_res else pre_res
                    eligible_r: list[Paper] = []
                    for p in order:
                        dk = p.doi.lower() if p.doi else None
                        tk = p.title.lower().strip()[:50]
                        if dk and dk in used_dois:
                            continue
                        if tk in used_titles:
                            continue
                        if not _paper_passes_content_scope(p, rescue_lang, scope_nursing):
                            continue
                        if (
                            scope_nursing
                            and rescue_lang == "en"
                            and not _claim_allows_student_sample(claim_u)
                            and _title_is_nursing_student_study(p.title)
                        ):
                            continue
                        eligible_r.append(p)
                    if eligible_r and paper_title:
                        for start in range(0, len(eligible_r), verify_batch_size):
                            chunk = eligible_r[start : start + verify_batch_size]
                            fits = ranker.verify_fit_batch(
                                marker.context_before,
                                claim_u,
                                chunk,
                                paper_title,
                                claim_type=miss_claim_ct,
                                secondary_claim_type=miss_secondary,
                            )
                            for p, ok in zip(chunk, fits):
                                if _heuristic_fit_veto(p, claim_u):
                                    continue
                                heur_ok = _heuristic_fit_accept(p, claim_u, paper_title)
                                if not ok and not heur_ok:
                                    continue
                                if ok and paper_title and (marker.paragraph_text or "").strip():
                                    if _analysis_needs_deep_verify(miss_analysis):
                                        deep_ok = ranker.verify_fit_deep(
                                            marker.paragraph_text,
                                            marker.context_before,
                                            claim_u,
                                            p,
                                            paper_title,
                                            claim_type=miss_claim_ct,
                                            cache=deep_fit_cache,
                                        )
                                        if not deep_ok:
                                            tier = ranker.verify_fit_mechanism_tier(
                                                marker.paragraph_text,
                                                marker.context_before,
                                                claim_u,
                                                p,
                                                paper_title,
                                                cache=mechanism_tier_cache,
                                            )
                                            if tier in ("exact", "relevant", "contextual"):
                                                rescue_meta["match_tier"] = tier
                                                log(
                                                    f"  [补救部分支撑:{tier}] {p.title[:40]}..."
                                                )
                                                attempt_best = p
                                                break
                                            if attempt_best:
                                                break
                                            continue
                                    else:
                                        rescue_meta["match_tier"] = "sufficient"
                                attempt_best = p
                                break
                            if attempt_best:
                                break
                    elif eligible_r:
                        attempt_best = eligible_r[0]
                elif available:
                    available.sort(
                        key=lambda p: (
                            2 if is_core_journal(p.journal or "") else 0,
                            p.citation_count or 0,
                        ),
                        reverse=True,
                    )
                    attempt_best = available[0]

                if attempt_best:
                    best_p = attempt_best
                    break

            if best_p:
                references[cid] = best_p
                if best_p.doi:
                    used_dois.add(best_p.doi.lower())
                used_titles.add(best_p.title.lower().strip()[:50])
                is_cn = _is_chinese_title(best_p.title)
                log(f"  [补救OK] [{cid}] {'[中]' if is_cn else '[英]'} {best_p.title[:50]} | {best_p.journal}")
                if miss_analysis:
                    _append_reference_match_log(
                        cid,
                        miss_analysis.key_claim,
                        paper_title,
                        "ok_rescue",
                        best_p.title,
                        best_p.journal or "",
                        claim_type=miss_claim_ct,
                        match_tier=rescue_meta.get("match_tier") or "",
                    )
                    save_cached_match(paper_title, miss_analysis.key_claim or "", best_p, "ok_rescue", miss_claim_ct)
            else:
                log(f"  [补救失败] [{cid}]")

    # 统计中英文比例
    cn_final = sum(1 for p in references.values() if _is_chinese_title(p.title))
    en_final = len(references) - cn_final
    total_elapsed = time.time() - total_start
    log(f"\n完成! {len(references)}/{len(grouped)} 匹配")
    log(f"  中文: {cn_final} | 英文: {en_final} | 比例: {cn_final}:{en_final}")
    log(f"  总耗时: {total_elapsed:.1f}s")

    if progress_callback:
        progress_callback(total_markers, total_markers, "完成!")

    plain_output = format_reference_list(references)
    markdown_output = format_reference_list_markdown(references)

    return references, markdown_output, plain_output


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print("用法: python main.py <论文.docx> [起始年份] [结束年份] [中文比例] [论文标题]")
        print("  示例: python main.py paper.docx 2022 2026 0.25 正念训练对护理人员隐性缺勤影响机制研究")
        sys.exit(1)

    docx_path = sys.argv[1]
    year_start = int(sys.argv[2]) if len(sys.argv) > 2 else None
    year_end = int(sys.argv[3]) if len(sys.argv) > 3 else None
    cn_ratio = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25
    title = sys.argv[5] if len(sys.argv) > 5 else ""

    refs, md, plain = process_paper(docx_path, year_start, year_end, cn_ratio=cn_ratio, paper_title=title)

    print("\n" + "="*60)
    print(plain)

    output_md = Path(docx_path).stem + "_references.md"
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\nMarkdown 已保存到: {output_md}")
