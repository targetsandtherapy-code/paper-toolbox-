# 参考文献匹配系统 — 重构路线图

对应《完整重构思路》文档，按阶段落地，每阶段可单独开关与回退。

## 已落地（本仓库持续更新）

| 项 | 说明 |
|----|------|
| 论点类型 `claim_type` | `ContentAnalyzer` 输出六类 + 启发式兜底 |
| `claim_confidence` / `secondary_claim_type` | LLM 输出 + 论点关键词纠偏 mechanism；日志带 `conf=`；**jsonl** 写入 `claim_confidence` |
| 类型分流检索 | 政策宏观英文双源限流、CNKI 动态翻页、检索词强化 |
| **政策宏观早停** | `policy_macro` 时默认 **跳过论点分解轮**（`REFERENCE_SKIP_DECOMPOSE_FOR_POLICY`，环境变量可关） |
| 机制型分级 | `verify_fit_mechanism_tier` + 部分支撑 |
| 精校缓存 | `deep_fit_cache` / `mechanism_tier_cache` |
| **精校深度** | **主类或次要类为 `mechanism` 时**走 `verify_fit_deep`（+ tier）；否则批量 fit 通过记 `match_tier=sufficient` |
| **`ref_type`（J/M/R/D/C/EB/Z）** | `ContentAnalyzer` 输出 + `Z` 启发式；`ref_type_routing.py` 统一策略 |
| **双轨道 LLM** | **论证**：`key_claim` / `core_topic` 供 fit；**检索**：`ref_authors`、`ref_title_keywords_cn/en`、`ref_population`、`ref_method` 等供检索；`search_query_builder.py` 组装检索式，避免用结论句直接搜库 |
| **P2 检索词** | `adjust_queries_for_ref_type`：M/R/D/C/EB/J 后缀与书名号前置 |
| **P2/P3 路由** | R/EB/D：**中文优先**；R/EB/D 英文轮 **仅 OA+CR**（无 PubMed）；R/EB/M **跳过论点分解**；R/EB **跳过第三轮领域级检索** |
| **补救阶段** | `MISS` 路径按 `ref_type` 调整检索词 |

## 阶段一：分类观测（可选）

- [x] 日志输出 `claim_confidence`；jsonl 记录 `claim_confidence`
- [ ] 日志中显式输出 `secondary_claim_type`（当前可从分析 JSON / 扩展字段读取）
- [ ] 人工抽检 20～30 篇，统计主类/次类准确率

## 阶段二：校验标准完全类型化

- [x] `verify_fit_batch` 主类+次类并集提示（`_batch_claim_type_hint`）
- [ ] 政策/概念类快筛提示与文档第五节进一步对齐（细调 prompt）

## 阶段三：三级过滤（硬排除 / 软扣分 / 类型规则）

- [ ] 标题无「护士」但摘要有护理人群 → 软扣分而非硬踢
- [ ] `intervention` 与机制型边界规则

## 阶段四：检索路由增强

- [ ] 政策型：CNKI 报纸/会议扩展（若 API 可得）
- [ ] 综述型：时间窗优先（近 5 年加权）
- [x] 按类型早停（`policy_macro` 跳过论点分解；**`ref_type`** R/EB/M 跳过分解；R/EB 跳过领域级第三轮）

## 阶段五：多维评分 + 嵌入

- [ ] 候选池内实时 embedding（中英分模型）
- [ ] 与关键词、核心刊、类型契合度加权，**替代或弱化**独立 `rank()` LLM（减少重复判断）

## 阶段六：类型化补救 + 四级标签

- [ ] 输出 `exact` / `sufficient` / `related` / `miss`（或等价字段）
- [ ] 按类型的 MISS 补救路径（拆变量搜、放宽人群等）

## 回退开关建议

`config.py` / 环境变量：

| 变量 | 默认 | 含义 |
|------|------|------|
| `REFERENCE_SKIP_DECOMPOSE_FOR_POLICY` | 开 | 政策宏观跳过论点分解轮 |
| `REFERENCE_USE_EMBEDDING_RANK` | 关 | 阶段五：候选 embedding 排序 |
| `REFERENCE_SKIP_DEEP_FOR_NON_MECHANISM` | （未单独做 env） | 深校逻辑已按 mechanism 门禁写死在 `main.py` |
| `REFERENCE_SEQUENTIAL_EN_SEARCH` | 关 | 英文库 OpenAlex→CrossRef→PubMed 顺序检索，单源 fit 通过即停；全未过再合并重排 |
| `REFERENCE_LANG_FALLBACK` | 开 | 中文位无匹配改试英文库，英文位无匹配改试知网 |
| `REFERENCE_POLICY_CN_ONLY` | **关** | 为开时 `policy_macro` 固定先走知网；默认关，与其它角标统配 |
| `REFERENCE_POLICY_ALLOW_EN_FALLBACK` | 关 | 与上项同开时，中文无果后是否允许改试英文 |
| `REFERENCE_CANONICAL_POLICY_EB` | **关** | 为开时启用内置国务院文件等固定 [EB/OL] 白名单；默认关 |
| `REFERENCE_NURSING_HARD_SCOPE` | **关** | 护理/医务课题可选：人群硬过滤 + 检索式带护士/nurse；通用学科默认不设限，设 1 开启 |
| `REFERENCE_SKIP_POOL_FALLBACK` | 关 | 为开时跳过角标内第四轮「候选池合并再 fit」 |
---

**一句话**：先看论点类型，再选检索与校验深度；机制型才精校，其余类型以快筛为主，降低延迟与 API 成本。
