"""数据分析代码生成模块 — 根据研究设计生成统计分析代码"""
import json
from openai import OpenAI
from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


class StatsCodeGenerator:
    def __init__(self, api_key: str = QWEN_API_KEY, base_url: str = QWEN_BASE_URL, model: str = QWEN_MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(self, description: str, language: str = "Python", variables: str = "",
                 method: str = "", data_format: str = "") -> dict:
        prompt = f"""你是社科/医学统计分析专家。请根据以下研究设计生成完整的数据分析代码。

研究描述：{description}
{f"变量说明：{variables}" if variables else ""}
{f"分析方法：{method}" if method else ""}
{f"数据格式：{data_format}" if data_format else ""}
编程语言：{language}

请生成包含以下部分的完整代码：
1. 数据加载与预处理
2. 描述性统计
3. 信效度检验（如适用）
4. 主要统计分析（根据研究方法）
5. 结果可视化
6. 结果解读（以注释形式说明如何解读每步输出）

额外要求：
- 代码必须可以直接运行（假设数据文件名为 data.csv 或 data.xlsx）
- 每个步骤要有清晰的注释
- 在代码末尾生成可直接写入论文的结果描述模板

请严格按以下 JSON 格式返回：
{{
  "code": "完整的可运行代码",
  "packages": ["需要安装的包1", "需要安装的包2"],
  "steps_explanation": [
    {{"step": "数据加载", "description": "说明"}},
    {{"step": "描述性统计", "description": "说明"}}
  ],
  "result_template": "论文中可直接使用的统计结果描述模板（如：回归分析结果表明，X对Y有显著正向影响(β=___, p<0.05)...）"
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": f"你是社科/医学统计分析专家，擅长用{language}进行数据分析。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)
