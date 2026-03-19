"""论文工具箱 — 统一入口"""
import streamlit as st

st.set_page_config(page_title="论文工具箱", page_icon="🎓", layout="wide")

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
