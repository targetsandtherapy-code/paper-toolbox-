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
# 须在环境变量或 .streamlit/secrets.toml 中配置，勿将真实密钥写入代码库
QWEN_API_KEY = _get_secret("QWEN_API_KEY", "")
QWEN_BASE_URL = _get_secret("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = _get_secret("QWEN_MODEL", "qwen-turbo")

# 学术数据源
YEAR_RANGE = (2021, 2026)
MAX_RESULTS_PER_SOURCE = 10
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
CROSSREF_API = "https://api.crossref.org"
OPENALEX_API = "https://api.openalex.org"
REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}

# 参考文献匹配：政策宏观论点往往不需「论点分解」子查询，跳过可省 LLM + 检索（设 0/false 关闭）
def _env_bool(key: str, default_true: bool = True) -> bool:
    v = os.environ.get(key)
    if v is None:
        return default_true
    return v.strip().lower() not in ("0", "false", "no", "off")


REFERENCE_SKIP_DECOMPOSE_FOR_POLICY = _env_bool("REFERENCE_SKIP_DECOMPOSE_FOR_POLICY", True)

# 英文文献：按 OpenAlex → CrossRef → PubMed 顺序检索；单源 fit 通过即停（省 API 和时间）
REFERENCE_SEQUENTIAL_EN_SEARCH = _env_bool("REFERENCE_SEQUENTIAL_EN_SEARCH", True)

# 角标分配为中文库但未匹配时改试英文（反之亦然），提高覆盖率（设 0/false 关闭）
REFERENCE_LANG_FALLBACK = _env_bool("REFERENCE_LANG_FALLBACK", True)

# 最终补救：书名号判为中文且仅优先知网后仍无匹配时，是否再试 CrossRef/OpenAlex（设 0/false 关闭）
REFERENCE_RESCUE_CN_FALLBACK_EN = _env_bool("REFERENCE_RESCUE_CN_FALLBACK_EN", True)

# 政策宏观论点是否固定走中文库（专用路由）；默认关，与其它角标共用随机中英分配与跨语言降级
REFERENCE_POLICY_CN_ONLY = _env_bool("REFERENCE_POLICY_CN_ONLY", False)
REFERENCE_POLICY_ALLOW_EN_FALLBACK = _env_bool("REFERENCE_POLICY_ALLOW_EN_FALLBACK", False)

# 内置国务院文件等「固定 URL 的 EB/OL」白名单；默认关，避免专用政策硬编码
REFERENCE_CANONICAL_POLICY_EB = _env_bool("REFERENCE_CANONICAL_POLICY_EB", False)

# 为 True 时跳过角标内的「第四轮：从本语种候选池合并再排序再 fit」（跨语言降级与前几轮仍保留）
REFERENCE_SKIP_POOL_FALLBACK = _env_bool("REFERENCE_SKIP_POOL_FALLBACK", False)

# 护理/医务类题目专用：人群硬过滤 + 检索式自动带护士/nurse（默认关=通用学科；护理课题可设 1 或 Streamlit 勾选）
REFERENCE_NURSING_HARD_SCOPE = _env_bool("REFERENCE_NURSING_HARD_SCOPE", False)

