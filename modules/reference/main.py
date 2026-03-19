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
from modules.reference.searcher.base import Paper
from modules.reference.fast_ranker import fast_rank
from modules.reference.relevance_ranker import RelevanceRanker
from modules.reference.formatter import format_reference_list, format_reference_list_markdown


def _is_chinese_title(title: str) -> bool:
    """判断标题是否为中文"""
    if not title:
        return False
    cn_chars = sum(1 for c in title if '\u4e00' <= c <= '\u9fff')
    return cn_chars / max(len(title), 1) > 0.3


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
                    result.remove(existing)
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
    ranker = RelevanceRanker()

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

        cn_query = " ".join(analysis.cn_keywords[:3])
        en_query = " ".join(analysis.en_keywords[:3])

        # 根据目标语言选择数据源
        candidates = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            if target_lang == "cn":
                futures = [
                    pool.submit(_search_source, crossref, cn_query, year_start, year_end, results_per_source, "CrossRef-CN"),
                    pool.submit(_search_source, openalex, cn_query, year_start, year_end, results_per_source, "OpenAlex-CN"),
                ]
            else:
                futures = [
                    pool.submit(_search_source, openalex, en_query, year_start, year_end, results_per_source, "OpenAlex-EN"),
                    pool.submit(_search_source, pubmed, en_query, year_start, year_end, results_per_source, "PubMed-EN"),
                    pool.submit(_search_source, crossref, en_query, year_start, year_end, results_per_source, "CrossRef-EN"),
                ]
            for f in as_completed(futures):
                label, papers = f.result()
                if papers:
                    log(f"  {label}: {len(papers)}篇")
                    candidates.extend(papers)

        if not candidates:
            log(f"  无结果")
            continue

        # 去重 + 排除已分配
        candidates = deduplicate_papers(candidates)
        candidates = [
            p for p in candidates
            if not (p.doi and p.doi.lower() in used_dois)
            and p.title.lower().strip()[:50] not in used_titles
        ]

        # 按目标语言过滤
        if target_lang == "cn":
            lang_filtered = [p for p in candidates if _is_chinese_title(p.title)]
            if not lang_filtered:
                lang_filtered = candidates
        else:
            lang_filtered = [p for p in candidates if not _is_chinese_title(p.title)]
            if not lang_filtered:
                lang_filtered = candidates

        if not lang_filtered:
            log(f"  无可用候选")
            continue

        # 本地预筛 + LLM 精排
        all_keywords = analysis.cn_keywords + analysis.en_keywords
        pre_ranked = fast_rank(
            context=marker.context_before,
            keywords=all_keywords,
            candidates=lang_filtered,
            top_k=5,
        )
        try:
            ranked = ranker.rank(
                context=marker.context_before,
                claim=analysis.key_claim,
                candidates=pre_ranked,
                top_k=max(top_k, 3),
                paper_title=paper_title,
            )
        except Exception:
            ranked = pre_ranked[:max(top_k, 3)]

        best = None
        for p in ranked:
            doi_key = p.doi.lower() if p.doi else None
            title_key = p.title.lower().strip()[:50]
            if doi_key and doi_key in used_dois:
                continue
            if title_key in used_titles:
                continue
            best = p
            break

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
