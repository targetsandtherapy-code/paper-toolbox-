"""统一项目配置"""
import os


def _get_secret(key, default=""):
    val = os.environ.get(key)
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


# LLM 配置（通义千问，兼容 OpenAI 格式）
QWEN_API_KEY = _get_secret("QWEN_API_KEY", "sk-81e555f2292c4305a53f8843884b36ab")
QWEN_BASE_URL = _get_secret("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = _get_secret("QWEN_MODEL", "qwen-turbo")

# 学术数据源
YEAR_RANGE = (2021, 2026)
MAX_RESULTS_PER_SOURCE = 10
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
CROSSREF_API = "https://api.crossref.org"
OPENALEX_API = "https://api.openalex.org"
BAIDU_SCHOLAR_URL = "https://xueshu.baidu.com/s"

REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}
