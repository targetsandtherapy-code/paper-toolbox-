"""GB/T 7714-2015 参考文献格式化模块"""
from datetime import date

from modules.reference.searcher.base import Paper


def _is_chinese_name(name: str) -> bool:
    return any('\u4e00' <= c <= '\u9fff' for c in (name or ""))


def format_authors_gbt(authors: list[str], max_authors: int = 3) -> str:
    """格式化作者列表（国标格式：中文用「等」，英文用「et al.」）"""
    if not authors:
        return ""
    if len(authors) <= max_authors:
        return ", ".join(authors)
    suffix = ", 等" if _is_chinese_name(authors[0]) else ", et al."
    return ", ".join(authors[:max_authors]) + suffix


def format_paper_gbt7714(index: int, paper: Paper) -> str:
    """将论文格式化为 GB/T 7714-2015 标准格式

    期刊论文格式:
    [序号] 作者. 题名[J]. 刊名, 年, 卷(期): 页码. DOI:xxx.

    电子公告/在线文献:
    [序号] 作者. 题名[EB/OL]. 出版者/网站. (更新日期)[引用日期]. URL.
    """
    ref_t = getattr(paper, "reference_type", None) or "J"
    title = paper.title.rstrip(".")
    parts = [f"[{index}]"]

    if ref_t == "EB/OL":
        authors_str = format_authors_gbt(paper.authors)
        if authors_str:
            parts.append(f" {authors_str}.")
        parts.append(f" {title}[EB/OL].")
        if paper.journal:
            parts.append(f" {paper.journal}.")
        eb_pub = getattr(paper, "eb_publish_date", None) or ""
        acc = getattr(paper, "access_date", None) or date.today().isoformat()
        if eb_pub:
            parts.append(f" ({eb_pub})[{acc}].")
        else:
            parts.append(f" [{acc}].")
        link = paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else "")
        if link:
            parts.append(f" {link}.")
        return "".join(parts)

    if ref_t == "M":
        authors_str = format_authors_gbt(paper.authors)
        if authors_str:
            parts.append(f" {authors_str}.")
        parts.append(f" {title}[M].")
        if paper.year:
            parts.append(f" {paper.year}.")
        # 无出版者时年可单独出现；出版地/出版者建议人工补全
        return "".join(parts)

    # --- 期刊 [J] ---
    authors_str = format_authors_gbt(paper.authors)
    if authors_str:
        parts.append(f" {authors_str}.")
    parts.append(f" {title}[J].")

    if paper.journal:
        parts.append(f" {paper.journal},")
    if paper.year:
        parts.append(f" {paper.year}.")
    elif paper.journal:
        parts[-1] = parts[-1].rstrip(",") + "."

    if paper.doi:
        parts.append(f" DOI: {paper.doi}.")

    return "".join(parts)


def format_reference_list(papers: dict[int, Paper]) -> str:
    """生成完整参考文献列表

    Args:
        papers: {角标编号: Paper} 的字典
    """
    lines = []
    lines.append("参考文献")
    lines.append("")
    for idx in sorted(papers.keys()):
        paper = papers[idx]
        line = format_paper_gbt7714(idx, paper)
        lines.append(line)
    return "\n".join(lines)


def format_reference_list_markdown(papers: dict[int, Paper]) -> str:
    """生成带可点击 DOI 链接的 Markdown 格式参考文献列表"""
    lines = []
    lines.append("# 参考文献")
    lines.append("")
    for idx in sorted(papers.keys()):
        paper = papers[idx]
        authors_str = format_authors_gbt(paper.authors)
        title = paper.title.rstrip(".")

        ref_t = getattr(paper, "reference_type", None) or "J"
        entry = f"[{idx}] "
        if ref_t == "EB/OL":
            if authors_str:
                entry += f"{authors_str}. "
            entry += f"{title}[EB/OL]. "
            if paper.journal:
                entry += f"{paper.journal}. "
            eb_pub = getattr(paper, "eb_publish_date", None) or ""
            acc = getattr(paper, "access_date", None) or date.today().isoformat()
            entry += f"({eb_pub})[{acc}]. " if eb_pub else f"[{acc}]. "
            link = paper.url or ""
            if link:
                entry += f"[链接]({link})"
        elif ref_t == "M":
            if authors_str:
                entry += f"{authors_str}. "
            entry += f"{title}[M]. "
            if paper.year:
                entry += f"{paper.year}. "
            entry += "（出版地/出版者待补）"
        else:
            if authors_str:
                entry += f"{authors_str}. "
            entry += f"{title}[J]. "
            if paper.journal:
                entry += f"{paper.journal}, "
            if paper.year:
                entry += f"{paper.year}. "

            if paper.doi:
                doi_url = f"https://doi.org/{paper.doi}"
                entry += f"DOI: [{paper.doi}]({doi_url})"

        lines.append(entry)
        lines.append("")

    return "\n".join(lines)


def format_single_reference_markdown(index: int, paper: Paper) -> str:
    """格式化单条参考文献（Markdown，带可点击 DOI）"""
    authors_str = format_authors_gbt(paper.authors)
    title = paper.title.rstrip(".")

    entry = f"**[{index}]** "
    if authors_str:
        entry += f"{authors_str}. "
    entry += f"*{title}*[J]. "
    if paper.journal:
        entry += f"{paper.journal}, "
    if paper.year:
        entry += f"{paper.year}. "
    if paper.doi:
        doi_url = f"https://doi.org/{paper.doi}"
        entry += f"DOI: [{paper.doi}]({doi_url})"

    return entry
