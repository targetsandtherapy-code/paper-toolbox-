"""SimHash 文本指纹 — 用于快速检测段落相似度"""
import re
import hashlib


def _tokenize_cn(text: str, n: int = 3) -> list[str]:
    """中文 N-gram 分词"""
    text = re.sub(r'[^\u4e00-\u9fffa-zA-Z0-9]', '', text)
    tokens = []
    for i in range(len(text) - n + 1):
        tokens.append(text[i:i + n])
    return tokens


def simhash(text: str, bits: int = 64) -> int:
    """计算文本的 SimHash 指纹"""
    tokens = _tokenize_cn(text)
    if not tokens:
        return 0

    v = [0] * bits
    for token in tokens:
        h = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16)
        for i in range(bits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(bits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(h1: int, h2: int) -> int:
    """计算两个 SimHash 指纹的汉明距离"""
    return bin(h1 ^ h2).count('1')


def similarity(h1: int, h2: int, bits: int = 64) -> float:
    """基于汉明距离计算相似度 (0-1)"""
    dist = hamming_distance(h1, h2)
    return 1.0 - dist / bits


def check_similarity(sentences_a: list[str], sentences_b: list[str], threshold: float = 0.85) -> list[dict]:
    """比对两组句子，返回相似度超过阈值的配对"""
    hashes_b = [(s, simhash(s)) for s in sentences_b if len(s) >= 10]

    results = []
    for sa in sentences_a:
        if len(sa) < 10:
            continue
        ha = simhash(sa)
        for sb, hb in hashes_b:
            sim = similarity(ha, hb)
            if sim >= threshold:
                results.append({
                    "source": sa,
                    "match": sb,
                    "similarity": round(sim, 4),
                })
    return results


def self_check(sentences: list[str], threshold: float = 0.90) -> list[dict]:
    """自查：检测文档内部是否有高度重复的段落"""
    hashes = [(s, simhash(s)) for s in sentences if len(s) >= 15]
    duplicates = []

    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            sim = similarity(hashes[i][1], hashes[j][1])
            if sim >= threshold:
                duplicates.append({
                    "sentence_a": hashes[i][0],
                    "sentence_b": hashes[j][0],
                    "similarity": round(sim, 4),
                })
    return duplicates
