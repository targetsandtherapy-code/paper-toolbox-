"""主流程：论文参考文献智能生成（支持中英文比例控制）"""
import sys
import re
import time
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import YEAR_RANGE
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


def _is_chinese_title(title: str) -> bool:
    """判断标题是否为中文"""
    if not title:
        return False
    cn_chars = sum(1 for c in title if '\u4e00' <= c <= '\u9fff')
    return cn_chars / max(len(title), 1) > 0.3


_IRRELEVANT_KEYWORDS = {
    "教学", "课程思政", "课程教学", "教学改革", "教学实践", "教学模式",
    "教学设计", "教学探索", "教学中的应用", "体验式教学", "对分课堂",
    "翻转课堂", "混合式教学", "OBE理念", "PBL教学", "课程建设",
    "教材", "慕课", "课堂教学", "教学质量", "教育评价",
}


def _is_irrelevant_paper(paper: Paper) -> bool:
    """过滤明显不相关的论文（教学类等）"""
    title = paper.title or ""
    for kw in _IRRELEVANT_KEYWORDS:
        if kw in title:
            return True
    return False


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


def _search_cnki(searcher, query, year_start, year_end, limit, field_cn_cores, label):
    try:
        papers = searcher.search(query, year_start, year_end, limit,
                                 max_pages=2, field_cn_cores=field_cn_cores)
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
):
    """处理论文主流程

    Args:
        cn_ratio: 中文文献占比 (0.25 = 1:3 中英文比例)
        progress_callback: 进度回调 progress_callback(current, total, status_text)
    """
    if year_start is None:
        year_start = YEAR_RANGE[0]
    if year_end is None:
        year_end = YEAR_RANGE[1]

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
    log(f"  发现 {len(grouped)} 个角标: {list(grouped.keys())}")

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

    references: dict[int, Paper] = {}
    used_dois: set[str] = set()
    used_titles: set[str] = set()
    analysis_cache: dict[str, object] = {}

    marker_list = list(grouped.items())
    total_markers = len(marker_list)

    for marker_idx, (cid, marker) in enumerate(marker_list):
        marker_start = time.time()
        target_lang = lang_map[cid]
        lang_label = "中文" if target_lang == "cn" else "英文"

        if progress_callback:
            progress_callback(marker_idx, total_markers, f"处理角标 [{cid}] ({marker_idx+1}/{total_markers})")

        log(f"\n[{cid}] ({lang_label}) {marker_idx+1}/{total_markers}")

        # LLM 分析（缓存）
        cache_key = marker.context_before.strip()[:100]
        if cache_key in analysis_cache:
            analysis = analysis_cache[cache_key]
            log(f"  分析: (缓存)")
        else:
            try:
                analysis = analyzer.analyze(
                    marker_id=str(cid),
                    paragraph=marker.paragraph_text,
                    context_before=marker.context_before,
                    paper_title=paper_title,
                )
                analysis_cache[cache_key] = analysis
                log(f"  分析: {analysis.core_topic[:40]}")
            except Exception as e:
                log(f"  分析失败: {e}")
                continue

        all_candidates_pool: list[Paper] = []

        def _search_candidates(cn_q, en_q):
            """执行搜索并返回候选列表"""
            candidates = []
            with ThreadPoolExecutor(max_workers=3) as pool:
                if target_lang == "cn":
                    futures = [
                        pool.submit(_search_cnki, cnki, cn_q, year_start, year_end, results_per_source * 2, cn_cores, "CNKI"),
                    ]
                else:
                    futures = [
                        pool.submit(_search_source, openalex, en_q, year_start, year_end, results_per_source, "OpenAlex-EN"),
                        pool.submit(_search_source, pubmed, en_q, year_start, year_end, results_per_source, "PubMed-EN"),
                        pool.submit(_search_source, crossref, en_q, year_start, year_end, results_per_source, "CrossRef-EN"),
                    ]
                for f in as_completed(futures):
                    label, papers = f.result()
                    if papers:
                        log(f"  {label}: {len(papers)}篇")
                        candidates.extend(papers)
            return candidates

        def _filter_and_rank(candidates, cur_analysis, min_score=4):
            """去重 + 语言过滤 + 排序，返回最佳 Paper 或 None"""
            candidates = deduplicate_papers(candidates)
            candidates = [
                p for p in candidates
                if not (p.doi and p.doi.lower() in used_dois)
                and p.title.lower().strip()[:50] not in used_titles
                and not _is_irrelevant_paper(p)
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

            all_kw = cur_analysis.cn_keywords + cur_analysis.en_keywords
            pre_ranked = fast_rank(
                context=marker.context_before,
                keywords=all_kw,
                candidates=lang_filtered,
                top_k=5,
                field_cores=all_field_cores,
            )
            try:
                ranked = ranker.rank(
                    context=marker.context_before,
                    claim=cur_analysis.key_claim,
                    candidates=pre_ranked,
                    top_k=max(top_k, 3),
                    paper_title=paper_title,
                    min_score=min_score,
                )
            except Exception:
                ranked = pre_ranked[:max(top_k, 3)]

            for p in ranked:
                doi_key = p.doi.lower() if p.doi else None
                title_key = p.title.lower().strip()[:50]
                if doi_key and doi_key in used_dois:
                    continue
                if title_key in used_titles:
                    continue
                return p
            return None

        # === 第一轮：原始关键词 ===
        cn_q1 = " ".join(analysis.cn_keywords[:3])
        en_q1 = " ".join(analysis.en_keywords[:3])
        cands1 = _search_candidates(cn_q1, en_q1)
        all_candidates_pool.extend(cands1)
        best = _filter_and_rank(cands1, analysis) if cands1 else None

        # === 第二轮：LLM 宽泛关键词（尝试 broaden_query 返回的搜索词） ===
        if not best:
            log(f"  [重试] 宽泛关键词...")
            try:
                broad = analyzer.broaden_query(analysis, paper_title=paper_title)
                broad_q_cn = broad.search_query_cn or " ".join(broad.cn_keywords[:3])
                broad_q_en = broad.search_query_en or " ".join(broad.en_keywords[:3])
                cands2 = _search_candidates(broad_q_cn, broad_q_en)
                all_candidates_pool.extend(cands2)
                best = _filter_and_rank(cands2, broad) if cands2 else None
            except Exception:
                pass

        # === 第三轮：用论文标题核心词 + 该角标的核心概念做搜索 ===
        if not best:
            log(f"  [重试] 领域级搜索...")
            core_word = analysis.cn_keywords[0] if analysis.cn_keywords else ""
            if target_lang == "cn":
                fallback_q = core_word + " 护士" if core_word else paper_title
            else:
                core_en = analysis.en_keywords[0] if analysis.en_keywords else "nursing"
                fallback_q = core_en + " nurse"
            cands3 = _search_candidates(fallback_q, fallback_q)
            all_candidates_pool.extend(cands3)
            best = _filter_and_rank(cands3, analysis, min_score=2) if cands3 else None

        # === 第四轮兜底：从所有候选池中选分最高的（不经 LLM 排序） ===
        if not best and all_candidates_pool:
            log(f"  [兜底] 从候选池选最佳...")
            pool_deduped = deduplicate_papers(all_candidates_pool)
            pool_deduped = [
                p for p in pool_deduped
                if not (p.doi and p.doi.lower() in used_dois)
                and p.title.lower().strip()[:50] not in used_titles
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
                all_kw = analysis.cn_keywords + analysis.en_keywords
                fallback_ranked = fast_rank(
                    context=marker.context_before,
                    keywords=all_kw,
                    candidates=pool_lang,
                    top_k=1,
                    field_cores=all_field_cores,
                )
                if fallback_ranked:
                    best = fallback_ranked[0]

        if best:
            references[cid] = best
            if best.doi:
                used_dois.add(best.doi.lower())
            used_titles.add(best.title.lower().strip()[:50])
            is_cn = _is_chinese_title(best.title)
            elapsed = time.time() - marker_start
            log(f"  [OK] [{elapsed:.1f}s] {'[中]' if is_cn else '[英]'} {best.title[:55]}")
            log(f"    DOI: {best.doi} | {best.journal} | {best.year}")
        else:
            log(f"  [MISS] 无匹配")

    # === 最终补救：对仍未匹配的角标，逐个用论点关键词精准搜索 ===
    missing_ids = [cid for cid in grouped if cid not in references]
    if missing_ids:
        log(f"\n--- 最终补救: {len(missing_ids)} 个角标未匹配 ---")
        from modules.reference.core_journals import is_core_journal

        for cid in missing_ids:
            marker = grouped[cid]
            target_lang_m = lang_map[cid]

            cache_key = marker.context_before.strip()[:100]
            miss_analysis = analysis_cache.get(cache_key)

            # 用该角标自身的论点搜索，而不是泛领域词
            if miss_analysis:
                if target_lang_m == "cn":
                    rescue_q = miss_analysis.search_query_cn or " ".join(miss_analysis.cn_keywords[:2])
                    rescue_q2 = paper_title
                else:
                    rescue_q = miss_analysis.search_query_en or " ".join(miss_analysis.en_keywords[:2])
                    rescue_q2 = " ".join(miss_analysis.en_keywords[:2]) + " nursing"
            else:
                rescue_q = paper_title if target_lang_m == "cn" else "mindfulness nursing presenteeism"
                rescue_q2 = rescue_q

            rescue_cands: list[Paper] = []
            for rq in [rescue_q, rescue_q2]:
                if not rq:
                    continue
                try:
                    if target_lang_m == "cn":
                        _, rp = _search_cnki(cnki, rq, year_start, year_end, 20, cn_cores, f"补救-{cid}")
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
                and not _is_irrelevant_paper(p)
            ]
            if target_lang_m == "cn":
                lang_avail = [p for p in available if _is_chinese_title(p.title)]
                if lang_avail:
                    available = lang_avail
            else:
                lang_avail = [p for p in available if not _is_chinese_title(p.title)]
                if lang_avail:
                    available = lang_avail

            if available:
                available.sort(key=lambda p: (
                    2 if is_core_journal(p.journal or "") else 0,
                    p.citation_count or 0,
                ), reverse=True)
                best_p = available[0]
                references[cid] = best_p
                if best_p.doi:
                    used_dois.add(best_p.doi.lower())
                used_titles.add(best_p.title.lower().strip()[:50])
                is_cn = _is_chinese_title(best_p.title)
                log(f"  [补救OK] [{cid}] {'[中]' if is_cn else '[英]'} {best_p.title[:50]} | {best_p.journal}")
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
