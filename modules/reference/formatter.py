"""GB/T 7714-2015 参考文献格式化模块"""
from modules.reference.searcher.base import Paper


def format_authors_gbt(authors: list[str], max_authors: int = 3) -> str:
    """格式化作者列表（国标格式）"""
    if not authors:
        return ""
    if len(authors) <= max_authors:
        return ", ".join(authors)
    return ", ".join(authors[:max_authors]) + ", 等"


def format_paper_gbt7714(index: int, paper: Paper) -> str:
    """将论文格式化为 GB/T 7714-2015 标准格式

    期刊论文格式:
    [序号] 作者. 题名[J]. 刊名, 年, 卷(期): 页码. DOI:xxx.
    """
    parts = []

    # [序号]
    parts.append(f"[{index}]")

    # 作者
    authors_str = format_authors_gbt(paper.authors)
    if authors_str:
        parts.append(f" {authors_str}.")
    
    # 题名[J]
    title = paper.title.rstrip(".")
    parts.append(f" {title}[J].")

    # 刊名, 年
    if paper.journal:
        parts.append(f" {paper.journal},")
    if paper.year:
        parts.append(f" {paper.year}.")
    elif paper.journal:
        parts[-1] = parts[-1].rstrip(",") + "."

    # DOI
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

        entry = f"[{idx}] "
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
