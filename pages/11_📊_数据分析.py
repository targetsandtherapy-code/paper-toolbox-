"""Streamlit 页面 - 数据分析代码生成"""
import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.title("📊 数据分析代码生成")
st.markdown("描述研究设计，自动生成统计分析代码（Python/R/SPSS），附带论文结果描述模板。")

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("研究设计")

    description = st.text_area("研究描述", height=120,
        placeholder="例：探究正念训练对护理人员隐性缺勤的影响，以工作投入为中介变量，以组织支持感为调节变量。样本量为300名护理人员。")

    language = st.selectbox("编程语言", ["Python (pandas + statsmodels)", "R", "SPSS 语法"])

    variables = st.text_area("变量说明（可选）", height=80,
        placeholder="自变量：正念训练(X)\n因变量：隐性缺勤(Y)\n中介变量：工作投入(M)\n调节变量：组织支持感(W)")

    method = st.selectbox("分析方法", [
        "自动推荐",
        "回归分析",
        "中介效应分析 (Bootstrap)",
        "调节效应分析",
        "有调节的中介模型",
        "结构方程模型 (SEM)",
        "方差分析 (ANOVA)",
        "t检验",
        "相关分析",
        "因子分析",
        "聚类分析",
    ])

    data_format = st.selectbox("数据格式", ["CSV", "Excel (.xlsx)", "SPSS (.sav)"])

    run_btn = st.button("📊 生成代码", type="primary", use_container_width=True)

with col_right:
    if run_btn:
        if not description.strip():
            st.error("请描述你的研究设计")
            st.stop()

        lang_map = {
            "Python (pandas + statsmodels)": "Python",
            "R": "R",
            "SPSS 语法": "SPSS",
        }

        with st.spinner("AI 正在生成分析代码..."):
            try:
                from modules.stats_code.generator import StatsCodeGenerator
                gen = StatsCodeGenerator()
                result = gen.generate(
                    description=description.strip(),
                    language=lang_map.get(language, "Python"),
                    variables=variables.strip(),
                    method="" if method == "自动推荐" else method,
                    data_format=data_format,
                )
            except Exception as e:
                st.error(f"生成失败: {e}")
                st.stop()

        st.success("代码生成完成!")

        packages = result.get("packages", [])
        if packages:
            st.markdown("### 需要安装的包")
            st.code(" ".join(f"pip install {p}" if "Python" in language else p for p in packages), language="bash")

        st.markdown("### 分析代码")
        code = result.get("code", "")
        code_lang = "python" if "Python" in language else "r" if language == "R" else "sql"
        st.code(code, language=code_lang)

        steps = result.get("steps_explanation", [])
        if steps:
            st.markdown("### 步骤说明")
            for s in steps:
                st.markdown(f"**{s.get('step', '')}：** {s.get('description', '')}")

        template = result.get("result_template", "")
        if template:
            st.markdown("### 论文结果描述模板")
            st.info(template)

        st.divider()
        st.download_button("下载代码", data=code,
            file_name=f"analysis.{'py' if 'Python' in language else 'R' if language == 'R' else 'sps'}",
            mime="text/plain", use_container_width=True)
    else:
        st.info("👈 描述研究设计和分析需求，点击「生成代码」")
