"""首页"""
import streamlit as st

st.title("🎓 论文工具箱")
st.markdown("一站式论文写作辅助平台 — 点击卡片或使用左侧导航进入工具。")
st.divider()

tools = [
    ("📝", "格式调整", "上传论文 + 学校模板，一键统一格式", "1_📝_格式调整"),
    ("📚", "参考文献生成", "角标匹配学术论文，GB/T 7714 格式", "2_📚_参考文献生成"),
    ("🔍", "查重预检", "知网前自查，标记高风险段落", "3_🔍_查重预检"),
    ("📋", "摘要生成", "生成中英文摘要及关键词", "4_📋_摘要生成"),
    ("📑", "大纲生成", "生成结构化论文大纲", "5_📑_大纲生成"),
    ("🌐", "学术翻译", "中英互译，术语准确", "6_🌐_学术翻译"),
    ("📄", "开题报告", "生成完整开题报告", "7_📄_开题报告"),
    ("✏️", "降重改写", "改写段落，降低重复率", "8_✏️_降重改写"),
    ("📖", "文献综述", "检索文献 + 聚类 + 生成综述", "9_📖_文献综述"),
    ("🔬", "论文审稿", "逐段审阅逻辑、论述、规范", "10_🔬_论文审稿"),
    ("📊", "数据分析", "生成统计分析代码 + 结果描述", "11_📊_数据分析"),
]

rows = [tools[i:i+3] for i in range(0, len(tools), 3)]

for row in rows:
    cols = st.columns(3)
    for j, (icon, name, desc, page) in enumerate(row):
        with cols[j]:
            with st.container(border=True):
                st.page_link(f"pages/{page}.py", label=f"**{icon} {name}**", use_container_width=True)
                st.caption(desc)
