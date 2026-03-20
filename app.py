"""论文工具箱 — 统一入口"""
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="论文工具箱", page_icon="🎓", layout="wide")

# 从 Streamlit Secrets 写出 CNKI Cookie 文件（部署环境无法直接上传文件）
_cookie_path = Path(__file__).parent / "cnki_cookies.txt"
if not _cookie_path.exists():
    _cookie_val = st.secrets.get("CNKI_COOKIES", "")
    if _cookie_val:
        _cookie_path.write_text(_cookie_val, encoding="utf-8")

home = st.Page("pages/home.py", title="首页", icon="🎓", default=True)

tools = [
    st.Page("pages/1_📝_格式调整.py", title="格式调整", icon="📝"),
    st.Page("pages/2_📚_参考文献生成.py", title="参考文献生成", icon="📚"),
    st.Page("pages/3_🔍_查重预检.py", title="查重预检", icon="🔍"),
    st.Page("pages/4_📋_摘要生成.py", title="摘要生成", icon="📋"),
    st.Page("pages/5_📑_大纲生成.py", title="大纲生成", icon="📑"),
    st.Page("pages/6_🌐_学术翻译.py", title="学术翻译", icon="🌐"),
    st.Page("pages/7_📄_开题报告.py", title="开题报告", icon="📄"),
    st.Page("pages/8_✏️_降重改写.py", title="降重改写", icon="✏️"),
    st.Page("pages/9_📖_文献综述.py", title="文献综述", icon="📖"),
    st.Page("pages/10_🔬_论文审稿.py", title="论文审稿", icon="🔬"),
    st.Page("pages/11_📊_数据分析.py", title="数据分析", icon="📊"),
]

pg = st.navigation({"": [home], "工具": tools})
pg.run()
