"""论文工具箱 — 统一入口"""
import streamlit as st

st.set_page_config(page_title="论文工具箱", page_icon="🎓", layout="wide")

st.title("🎓 论文工具箱")
st.markdown("一站式论文写作辅助平台，包含格式调整、参考文献生成、查重预检、摘要生成、大纲生成等工具。")

st.divider()

cols = st.columns(3)

tools = [
    ("📝", "格式调整", "上传论文 + 学校模板，一键统一格式（字体、段落、页边距、三线表等）"),
    ("📚", "参考文献生成", "识别论文角标，自动匹配学术论文并生成 GB/T 7714 格式参考文献"),
    ("🔍", "查重预检", "提交知网前先自查，标记高风险段落，预估重复率"),
    ("📋", "摘要生成", "输入论文内容，生成符合学术规范的中英文摘要"),
    ("📑", "大纲生成", "输入研究题目，生成结构化论文大纲"),
]

for i, (icon, name, desc) in enumerate(tools):
    with cols[i % 3]:
        with st.container(border=True):
            st.subheader(f"{icon} {name}")
            st.markdown(desc)

st.divider()
st.caption("👈 使用左侧导航栏切换工具")
