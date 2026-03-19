"""论文工具箱 — 统一入口"""
import streamlit as st

st.set_page_config(page_title="论文工具箱", page_icon="🎓", layout="wide")

st.title("🎓 论文工具箱")
st.markdown("一站式论文写作辅助平台，包含格式调整、参考文献生成、查重预检、摘要生成、大纲生成等工具。")

st.divider()

cols = st.columns(4)

tools = [
    ("📝", "格式调整", "上传论文 + 学校模板，一键统一格式"),
    ("📚", "参考文献生成", "角标匹配学术论文，生成 GB/T 7714 格式"),
    ("🔍", "查重预检", "知网前自查，标记高风险段落"),
    ("📋", "摘要生成", "生成中英文摘要及关键词"),
    ("📑", "大纲生成", "生成结构化论文大纲"),
    ("🌐", "学术翻译", "中英互译，术语准确"),
    ("📄", "开题报告", "生成完整开题报告"),
    ("✏️", "降重改写", "改写段落，降低重复率"),
    ("📖", "文献综述", "检索文献 + 聚类 + 生成综述"),
    ("🔬", "论文审稿", "逐段审阅逻辑、论述、规范"),
    ("📊", "数据分析", "生成统计分析代码 + 结果描述"),
]

for i, (icon, name, desc) in enumerate(tools):
    with cols[i % 4]:
        with st.container(border=True):
            st.subheader(f"{icon} {name}")
            st.markdown(desc)

st.divider()
st.caption("👈 使用左侧导航栏切换工具")
