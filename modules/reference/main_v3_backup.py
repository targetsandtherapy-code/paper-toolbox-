"""主流程：论文参考文献智能生成（支持中英文比例控制）"""
import sys
import re
import json
import time
import random
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import (
    REFERENCE_LANG_FALLBACK,
    REFERENCE_NURSING_HARD_SCOPE,
    REFERENCE_POLICY_ALLOW_EN_FALLBACK,
    REFERENCE_POLICY_CN_ONLY,
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
            callback(msg)
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
    log(f"  发现 {full_marker_count} 个角标: {list(grouped.keys())}")
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

    # 预分配中英文角标（随机打散，1:3 = 每4篇1中3英）
    import math
    total = len(grouped)
    cn_count = max(1, math.ceil(total * cn_ratio))
    en_count = total - cn_count
    lang_slots = ["cn"] * cn_count + ["en"] * en_count
    random.shuffle(lang_slots)
    marker_ids = list(grouped.keys())
    lang_map = {marker_ids[i]: lang_slots[i] for i in range(total)}

    cn_ids = [k for k, v in lang_map.items() if v == "cn"]
    en_ids = [k for k, v in lang_map.items() if v == "en"]
    log(f"  中文角标 ({len(cn_ids)}): {cn_ids}")
    log(f"  英文角标 ({len(en_ids)}): {en_ids}")

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
        quote_src = quoted_title_source_lang(marker.context_before or "")
        ref_rt = resolve_ref_type_for_marker(analysis, marker.context_before or "")
        _rth = (getattr(analysis, "ref_type_hint", "") or "").strip()
        log(f"  ref_type: {ref_rt}" + (f" — {_rth[:56]}…" if len(_rth) > 56 else (f" — {_rth}" if _rth else "")))
        if quote_src == "cn":
            _lang_attempts = ["cn"]
            log("  [策略] 书名号《…》为中文题名：本角标仅使用知网等中文源（不请求英文学术库）")
        elif quote_src == "en":
            _lang_attempts = ["en"]
            log("  [策略] 书名号《…》为英文题名：本角标仅使用英文学术库（不用知网）")
        elif ct == "policy_macro" and pol_cn_only:
            _lang_attempts = ["cn"]
            if lf_on and pol_en_fb:
                _lang_attempts.append("en")
            log(
                "  [策略] 政策宏观论点："
                + ("仅中文库检索" if not pol_en_fb else "优先中文库，无果再试英文")
                + "（忽略本角标随机中英分配）"
            )
        else:
            _lang_attempts = lang_attempts_for_ref_type(
                ref_rt, assigned_lang, lf_on, None
            )
            if ref_rt in ("R", "EB", "D"):
                _le = (
                    "；英文降级时精简英文源（无 PubMed）"
                    if use_light_english_sources(ref_rt)
                    else ""
                )
                log(f"  [策略] ref_type={ref_rt}：优先中文检索{_le}")

        target_lang = assigned_lang
        verify_meta: dict[str, str] = {"match_tier": ""}
        best = None

        for _li, target_lang in enumerate(_lang_attempts):
            if best is not None:
                break
            if _li > 0:
                log(
                    f"  [降级] 分配为{'中文' if assigned_lang == 'cn' else '英文'}库无匹配，"
                    f"改试{'英文' if target_lang == 'en' else '中文'}文献…"
                )
            verify_meta["match_tier"] = ""
            all_candidates_pool: list[Paper] = []

            def _search_candidates(cn_q, en_q, pages_override: Optional[int] = None):
                """执行搜索并返回候选列表（政策类英文降级为双源少条）。"""
                pages = eff_pages if pages_override is None else pages_override
                candidates = []
                policy_en = target_lang == "en" and (
                    ct == "policy_macro" or use_light_english_sources(ref_rt)
                )
                lim = min(results_per_source, 5) if policy_en else results_per_source
                with ThreadPoolExecutor(max_workers=3) as pool:
                    if target_lang == "cn":
                        futures = [
                            pool.submit(
                                _search_cnki,
                                cnki,
                                cn_q,
                                year_start,
                                year_end,
                                results_per_source * 2,
                                cn_cores,
                                "CNKI",
                                pages,
                            ),
                        ]
                    else:
                        if policy_en:
                            futures = [
                                pool.submit(_search_source, openalex, en_q, year_start, year_end, lim, "OpenAlex-EN"),
                                pool.submit(_search_source, crossref, en_q, year_start, year_end, lim, "CrossRef-EN"),
                            ]
                        else:
                            futures = [
                                pool.submit(_search_source, openalex, en_q, year_start, year_end, lim, "OpenAlex-EN"),
                                pool.submit(_search_source, pubmed, en_q, year_start, year_end, lim, "PubMed-EN"),
                                pool.submit(_search_source, crossref, en_q, year_start, year_end, lim, "CrossRef-EN"),
                            ]
                    for f in as_completed(futures):
                        label, papers = f.result()
                        if papers:
                            log(f"  {label}: {len(papers)}篇")
                            candidates.extend(papers)
                return candidates

            def _try_verify_accept(candidates_list: list[Paper], cur_analysis) -> Optional[Paper]:
                """硬过滤后批量 LLM fit，减少 API 次数；无题目时直接取首篇通过硬过滤的。"""
                verify_meta["match_tier"] = ""
                eligible: list[Paper] = []
                for p in candidates_list:
                    doi_key = p.doi.lower() if p.doi else None
                    title_key = p.title.lower().strip()[:50]
                    if doi_key and doi_key in used_dois:
                        continue
                    if title_key in used_titles:
                        continue
                    if not _paper_passes_content_scope(p, target_lang, scope_nursing):
                        continue
                    if (
                        scope_nursing
                        and target_lang == "en"
                        and not _claim_allows_student_sample(cur_analysis.key_claim)
                        and _title_is_nursing_student_study(p.title)
                    ):
                        continue
                    eligible.append(p)
                if not eligible:
                    return None
                if not paper_title:
                    return eligible[0]

                claim_u = cur_analysis.key_claim or ""
                claim_ct = getattr(cur_analysis, "claim_type", None) or "status_quo"
                sec_ct = getattr(cur_analysis, "secondary_claim_type", None) or ""
                for start in range(0, len(eligible), verify_batch_size):
                    chunk = eligible[start : start + verify_batch_size]
                    fits = ranker.verify_fit_batch(
                        marker.context_before,
                        claim_u,
                        chunk,
                        paper_title,
                        claim_type=claim_ct,
                        secondary_claim_type=sec_ct,
                    )
                    deep_tried = 0
                    for p, ok in zip(chunk, fits):
                        if _heuristic_fit_veto(p, claim_u):
                            log(f"  [启发否决] {p.title[:38]}...")
                            continue
                        heur_ok = _heuristic_fit_accept(p, claim_u, paper_title)
                        if not ok and not heur_ok:
                            continue
                        if ok and paper_title and (marker.paragraph_text or "").strip():
                            if _analysis_needs_deep_verify(cur_analysis) and deep_tried < 2:
                                deep_tried += 1
                                deep_ok = ranker.verify_fit_deep(
                                    marker.paragraph_text,
                                    marker.context_before,
                                    claim_u,
                                    p,
                                    paper_title,
                                    claim_type=claim_ct,
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
                                        verify_meta["match_tier"] = tier
                                        log(f"  [部分支撑:{tier}] {p.title[:38]}...")
                                        return p
                                    log(f"  [精校否] {p.title[:38]}...")
                                    continue
                            else:
                                verify_meta["match_tier"] = "sufficient"
                        return p
                    for p, ok in zip(chunk, fits):
                        if not ok and not _heuristic_fit_accept(p, claim_u, paper_title):
                            log(f"  [fit否] 跳过: {p.title[:40]}...")
                return None

            def _filter_and_rank(
                candidates, cur_analysis, min_score=5, skip_llm_rank: bool = False
            ):
                """去重 + 情境/人群过滤 + 排序 + fit 校验"""
                candidates = deduplicate_papers(candidates)
                candidates = [
                    p for p in candidates
                    if not (p.doi and p.doi.lower() in used_dois)
                    and p.title.lower().strip()[:50] not in used_titles
                    and _paper_passes_content_scope(p, target_lang, scope_nursing)
                ]

                if target_lang == "cn":
                    lang_filtered = [p for p in candidates if _is_chinese_title(p.title)]
                    if not lang_filtered:
                        lang_filtered = candidates
                else:
                    lang_filtered = [p for p in candidates if not _is_chinese_title(p.title)]
                    if not lang_filtered:
                        lang_filtered = candidates

                if not lang_filtered:
                    return None

                all_kw = _rank_keywords_for_analysis(cur_analysis)
                pre_ranked = fast_rank(
                    context=marker.context_before,
                    keywords=all_kw,
                    candidates=lang_filtered,
                    top_k=8,
                    field_cores=all_field_cores,
                    claim=cur_analysis.key_claim or "",
                )
                # fast_rank 首位高分时直接 fit 验证，跳过 LLM rank 省一次 API
                if pre_ranked and not skip_llm_rank:
                    top_hit = _try_verify_accept(pre_ranked[:3], cur_analysis)
                    if top_hit is not None:
                        return top_hit

                ranked: list[Paper] = []
                if not skip_llm_rank:
                    try:
                        ranked = ranker.rank(
                            context=marker.context_before,
                            claim=cur_analysis.key_claim,
                            candidates=pre_ranked,
                            top_k=max(top_k, 5),
                            paper_title=paper_title,
                            min_score=min_score,
                        )
                    except Exception:
                        ranked = []

                order = ranked if ranked else pre_ranked[:8]
                return _try_verify_accept(order, cur_analysis)

            def _en_source_pairs(policy_en: bool):
                if policy_en:
                    return [(openalex, "OpenAlex-EN"), (crossref, "CrossRef-EN")]
                return [(openalex, "OpenAlex-EN"), (crossref, "CrossRef-EN"), (pubmed, "PubMed-EN")]

            def _search_en_sequential_and_try(
                en_q: str, cur_analysis, min_score: float = 5
            ) -> Optional[Paper]:
                """英文库顺序检索：逐源拉取，单源内 fast_rank+fit，命中即停；皆不中则合并后再走完整 LLM 排序。"""
                policy_en = (
                    getattr(cur_analysis, "claim_type", None) == "policy_macro"
                    or use_light_english_sources(ref_rt)
                )
                lim = min(results_per_source, 5) if policy_en else results_per_source
                merged: list[Paper] = []
                for searcher, label in _en_source_pairs(policy_en):
                    _, papers = _search_source(
                        searcher, en_q, year_start, year_end, lim, label
                    )
                    if papers:
                        log(f"  {label}: {len(papers)}篇")
                        merged.extend(papers)
                        all_candidates_pool.extend(papers)
                        b = _filter_and_rank(
                            papers, cur_analysis, min_score=min_score, skip_llm_rank=True
                        )
                        if b is not None:
                            log(f"  [顺序英文库] 已在 {label} 命中，未请求后续英文源")
                            return b
                if merged:
                    log("  [顺序英文库] 各源单独未通过 fit，合并候选并重排…")
                    return _filter_and_rank(
                        merged, cur_analysis, min_score=min_score, skip_llm_rank=False
                    )
                return None

            # === 第一轮：检索轨道（题名式）→ 政策类等再 enrich ===
            _base_cn, _base_en = build_search_queries_from_analysis(analysis)
            _cn_raw, _en_raw = _enrich_queries_for_claim_type(_base_cn, _base_en, ct)
            _cn_raw, _en_raw = adjust_queries_for_ref_type(
                _cn_raw, _en_raw, ref_rt, marker.context_before or ""
            )
            cn_q1 = _ensure_nursing_query(_cn_raw, "cn", scope_nursing)
            en_q1 = _ensure_nursing_query(_en_raw, "en", scope_nursing)
            if target_lang == "en" and seq_en:
                best = _search_en_sequential_and_try(en_q1, analysis, min_score=5)
            else:
                cands1 = _search_candidates(cn_q1, en_q1)
                all_candidates_pool.extend(cands1)
                best = _filter_and_rank(cands1, analysis, min_score=5) if cands1 else None

            # === 第二轮：LLM 宽泛关键词（尝试 broaden_query 返回的搜索词） ===
            if not best:
                log(f"  [重试] 宽泛关键词...")
                try:
                    broad = analyzer.broaden_query(analysis, paper_title=paper_title)
                    _bb_cn, _bb_en = build_search_queries_from_analysis(broad)
                    _bc, _be = _enrich_queries_for_claim_type(
                        _bb_cn,
                        _bb_en,
                        getattr(broad, "claim_type", None) or ct,
                    )
                    _bc, _be = adjust_queries_for_ref_type(
                        _bc, _be, ref_rt, marker.context_before or ""
                    )
                    broad_q_cn = _ensure_nursing_query(_bc, "cn", scope_nursing)
                    broad_q_en = _ensure_nursing_query(_be, "en", scope_nursing)
                    if target_lang == "en" and seq_en:
                        best = _search_en_sequential_and_try(broad_q_en, broad, min_score=5)
                    else:
                        cands2 = _search_candidates(broad_q_cn, broad_q_en)
                        all_candidates_pool.extend(cands2)
                        best = (
                            _filter_and_rank(cands2, broad, min_score=5) if cands2 else None
                        )
                except Exception:
                    pass

            # === 第2.5 轮：论点分解检索（多侧面子查询合并） ===
            if not best:
                if ct == "policy_macro" and REFERENCE_SKIP_DECOMPOSE_FOR_POLICY:
                    log(
                        "  [策略] 政策宏观论点：跳过论点分解检索"
                        "（省 API，见 REFERENCE_SKIP_DECOMPOSE_FOR_POLICY）"
                    )
                elif should_skip_decompose_for_ref_type(ref_rt):
                    log(
                        f"  [策略] ref_type={ref_rt}：跳过论点分解检索（专著/报告/网络类控制轮次）"
                    )
                else:
                    log(f"  [重试] 论点分解检索...")
                    try:
                        subs = analyzer.decompose_claim_for_search(
                            analysis, paper_title=paper_title, target_lang=target_lang
                        )
                        for sub in subs:
                            sq_cn = _ensure_nursing_query(sub.get("cn", ""), "cn", scope_nursing)
                            sq_en = _ensure_nursing_query(sub.get("en", ""), "en", scope_nursing)
                            sq_cn, sq_en = adjust_queries_for_ref_type(
                                sq_cn, sq_en, ref_rt, marker.context_before or ""
                            )
                            if not sq_cn and not sq_en:
                                continue
                            if target_lang == "en" and seq_en:
                                sub_en = sq_en or sq_cn or paper_title
                                best = _search_en_sequential_and_try(
                                    _ensure_nursing_query(sub_en, "en", scope_nursing),
                                    analysis,
                                    min_score=4,
                                )
                            else:
                                c_sub = _search_candidates(
                                    sq_cn or paper_title, sq_en or sq_cn or paper_title
                                )
                                all_candidates_pool.extend(c_sub)
                                if c_sub:
                                    best = _filter_and_rank(c_sub, analysis, min_score=4)
                            if best:
                                break
                    except Exception:
                        pass

            # === 第三轮：用论文标题核心词 + 该角标的核心概念做搜索 ===
            if not best:
                if should_skip_domain_fallback(ref_rt):
                    log(
                        f"  [策略] ref_type={ref_rt}：跳过领域级宽泛检索（控制轮次与跑题）"
                    )
                else:
                    log(f"  [重试] 领域级搜索...")
                    core_word = (
                        (analysis.ref_title_keywords_cn[0] if analysis.ref_title_keywords_cn else "")
                        or (analysis.cn_keywords[0] if analysis.cn_keywords else "")
                    )
                    if target_lang == "cn":
                        _fb_cn = _ensure_nursing_query(
                            (core_word + " 护士") if core_word else paper_title,
                            "cn",
                            scope_nursing,
                        )
                        _fb_en = _fb_cn
                    else:
                        core_en = (
                            (
                                analysis.ref_title_keywords_en[0]
                                if analysis.ref_title_keywords_en
                                else ""
                            )
                            or (
                                analysis.en_keywords[0]
                                if analysis.en_keywords
                                else "nursing"
                            )
                        )
                        _fb_en = _ensure_nursing_query(
                            core_en + " nurse", "en", scope_nursing
                        )
                        _fb_cn = _fb_en
                    _fb_cn, _fb_en = adjust_queries_for_ref_type(
                        _fb_cn, _fb_en, ref_rt, marker.context_before or ""
                    )
                    fallback_q = _fb_cn if target_lang == "cn" else _fb_en
                    if target_lang == "en" and seq_en:
                        best = _search_en_sequential_and_try(
                            fallback_q, analysis, min_score=4
                        )
                    else:
                        cands3 = _search_candidates(_fb_cn, _fb_en)
                        all_candidates_pool.extend(cands3)
                        best = (
                            _filter_and_rank(cands3, analysis, min_score=4)
                            if cands3
                            else None
                        )

            # === 第四轮兜底：同一语种内从已累计候选池再排序+fit（与跨语言降级互补） ===
            if not skip_pool_fb and not best and all_candidates_pool:
                log(f"  [兜底] 从候选池选最佳...")
                pool_deduped = deduplicate_papers(all_candidates_pool)
                pool_deduped = [
                    p for p in pool_deduped
                    if not (p.doi and p.doi.lower() in used_dois)
                    and p.title.lower().strip()[:50] not in used_titles
                    and _paper_passes_content_scope(p, target_lang, scope_nursing)
                ]
                if target_lang == "cn":
                    pool_lang = [p for p in pool_deduped if _is_chinese_title(p.title)]
                    if not pool_lang:
                        pool_lang = pool_deduped
                else:
                    pool_lang = [p for p in pool_deduped if not _is_chinese_title(p.title)]
                    if not pool_lang:
                        pool_lang = pool_deduped

                if pool_lang:
                    all_kw = _rank_keywords_for_analysis(analysis)
                    fallback_ranked = fast_rank(
                        context=marker.context_before,
                        keywords=all_kw,
                        candidates=pool_lang,
                        top_k=8,
                        field_cores=all_field_cores,
                        claim=analysis.key_claim or "",
                    )
                    if fallback_ranked:
                        try:
                            llm_ranked = ranker.rank(
                                context=marker.context_before,
                                claim=analysis.key_claim,
                                candidates=fallback_ranked,
                                top_k=6,
                                paper_title=paper_title,
                                min_score=4,
                            )
                            merged = llm_ranked if llm_ranked else fallback_ranked
                            best = _try_verify_accept(merged, analysis)
                            if not best:
                                best = _try_verify_accept(fallback_ranked, analysis)
                        except Exception:
                            best = _try_verify_accept(fallback_ranked, analysis)

            if best:
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
            log(f"  [OK] [{elapsed:.1f}s] {'[中]' if is_cn else '[英]'} {best.title[:55]}")
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
                match_tier=verify_meta.get("match_tier") or "",
                claim_confidence=getattr(analysis, "claim_confidence", None),
            )
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
            rescue_lang = quote_rescue if quote_rescue else target_lang_m
            miss_ref_rt = (
                resolve_ref_type_for_marker(miss_analysis, marker.context_before or "")
                if miss_analysis
                else "J"
            )
            if quote_rescue:
                log(
                    f"  [补救] 书名号题名判定为{'中文' if quote_rescue == 'cn' else '英文'}，"
                    f"补救检索仅走{'知网' if quote_rescue == 'cn' else '英文库'}"
                )

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
                rescue_q = (
                    _ensure_nursing_query(paper_title, "cn", scope_nursing)
                    if rescue_lang == "cn"
                    else _ensure_nursing_query("mindfulness nursing presenteeism", "en", scope_nursing)
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

            best_p = None
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
                                            best_p = p
                                            break
                                        if best_p:
                                            break
                                        continue
                                else:
                                    rescue_meta["match_tier"] = "sufficient"
                            best_p = p
                            break
                        if best_p:
                            break
                elif eligible_r:
                    best_p = eligible_r[0]
            elif available:
                available.sort(
                    key=lambda p: (
                        2 if is_core_journal(p.journal or "") else 0,
                        p.citation_count or 0,
                    ),
                    reverse=True,
                )
                best_p = available[0]

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
