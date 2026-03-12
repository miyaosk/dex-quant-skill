---
name: backtest-reviewer
description: >
  Evaluate backtest results, assess strategy robustness, detect overfitting, and decide whether a strategy
  is approved for monitoring or live trading. Use when user asks to review backtests, check if a strategy
  is good, analyze performance, or decide whether to go live.
  评审回测结果，分析策略稳健性，检测过拟合，决定策略是否可以进入监控/实盘阶段。
---

# Backtest Reviewer Skill

## 目标

独立评审回测结果，给出明确的通过/驳回决策。本 Skill 是策略生命周期中的"质量关卡"——只有通过评审的策略才能进入信号监控和实盘交易阶段。

本 Skill 的职责是：**接收回测结果 → 多维分析 → 风险评估 → 给出决策 → 输出评审报告**。

评审结论不可含糊。每次评审必须以 `approved`（通过）、`paper_trade_first`（先模拟交易）、`rejected`（驳回）三者之一结束。

---

## 触发条件

当用户表达以下意图时激活本 Skill：

- "帮我看看这个回测结果怎么样"
- "这个策略能上实盘吗？"
- "分析一下回测表现"
- "检查一下有没有过拟合"
- "这个 Sharpe 算好吗？"
- "回测通过了吗？可以部署吗？"
- 任何涉及回测结果评审、策略质量判断、是否可上线的请求

---

## 输入

| 输入项 | 是否必须 | 说明 |
|--------|---------|------|
| BacktestResult | **必须** | 回测引擎输出的完整结果，包含交易记录、权益曲线、绩效指标 |
| StrategySpec | **必须** | 关联的策略定义，用于理解策略逻辑和参数 |
| 交易分布数据 | 建议提供 | 交易在时间/品种/方向上的分布情况 |
| 参数扫描结果 | 建议提供 | 不同参数组合的表现对比，用于检测参数敏感性 |
| 样本内/外数据 | 建议提供 | In-sample 和 Out-of-sample 的分段表现 |
| 成本前后对比 | 建议提供 | 未计手续费/滑点 vs 已计手续费/滑点的表现差异 |

---

## 输出

| 输出项 | 说明 |
|--------|------|
| ReviewReport | 完整的评审报告，遵循 `backtest-reviewer/assets/review_template.json` 格式 |

### ReviewReport 核心字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `decision` | `string` | 评审结论：`approved`（通过）/ `paper_trade_first`（先模拟）/ `rejected`（驳回） |
| `summary` | `string` | 一段话总结评审结论和核心理由 |
| `strengths` | `string[]` | 策略优势列表（具体、可量化） |
| `risks` | `string[]` | 策略风险列表（具体、可量化，不可用"可能有风险"等模糊表述） |
| `metrics_summary` | `object` | 关键指标的值与评级 |
| `overfitting_assessment` | `string` | 过拟合评估结论与依据 |
| `cost_impact` | `string` | 成本影响分析（手续费/滑点对收益的侵蚀程度） |
| `required_actions` | `string[]` | 必须完成的改进事项（仅 `paper_trade_first` 和 `rejected` 时填写） |
| `recommended_next_step` | `string` | 建议的下一步操作 |

---

## 工作流程

### 第 1 步：完整性检查

确认输入数据完整可用：

- BacktestResult 存在且包含完整的交易记录和权益曲线
- 关联的 StrategySpec 可获取
- 回测时间范围足够长（至少 6 个月，建议 1 年以上）
- 交易数量足够形成统计意义（至少 30 笔，建议 100 笔以上）

如果数据不完整，立即告知用户缺少什么，不可在数据不足的情况下强行评审。

### 第 2 步：绩效指标评估

逐项检查核心绩效指标，对照评级标准（参考 `references/metrics-guide.md`）：

- Sharpe ratio：是否达到可接受水平？
- 最大回撤：是否在可控范围内？
- 胜率 × 盈亏比：是否形成正期望值？
- Calmar ratio：收益是否值得承受的回撤？
- Sortino ratio：下行风险是否可控？
- 年化收益率：是否显著跑赢 benchmark？

每个指标给出 `pass` / `warning` / `fail` 评级及具体数值。

### 第 3 步：收益来源分析

分析策略的收益从何而来：

- 收益是否集中在少数几笔交易？（集中度 > 50% 为高风险信号）
- 收益是否来自趋势段还是极端行情？
- 是否依赖特定市场状态（如单边牛市/暴跌反弹）？
- 剔除最大 N 笔交易后，策略是否仍然盈利？

### 第 4 步：成本影响分析

对比成本前后的表现差异：

- 手续费侵蚀了多少收益？（占比 > 30% 为 warning）
- 滑点假设是否合理？
- 如果成本翻倍，策略是否仍然盈利？
- 换手率是否过高导致成本不可承受？

### 第 5 步：过拟合检测

系统性检测过拟合风险（参考 `references/review-checklist.md`）：

- 参数数量 vs 交易数量的比例（参数 / 交易 > 0.1 为 warning）
- 参数敏感性：微调参数后收益变化是否剧烈？
- 样本内 vs 样本外表现差异（OOS 衰减 > 50% 为 fail）
- 策略逻辑复杂度与数据量是否匹配？

### 第 6 步：市场状态分析

检查策略在不同市场状态下的表现：

- 趋势行情表现如何？
- 震荡行情表现如何？
- 暴跌行情表现如何？
- 是否存在某种行情下的系统性亏损？
- 不同行情的表现差异是否可解释？

### 第 7 步：真实可交易性评估

评估策略在实盘中的可执行性：

- 交易标的的流动性是否支撑策略所需的交易量？
- 持仓时间是否合理？
- 订单类型和执行频率是否可实现？
- 资金费率对永续合约策略的真实影响？
- Alpha 衰减风险——策略的有效性是否有时效性？

### 第 8 步：综合评审决策

基于以上 7 步分析，给出最终评审结论：

**通过（approved）条件：**
- 核心指标全部 pass 或至多 1 个 warning
- 无过拟合高风险信号
- 成本后表现仍然稳健
- 收益来源可解释、不集中
- OOS 表现与 IS 一致

**先模拟交易（paper_trade_first）条件：**
- 核心指标多数 pass 但存在 2-3 个 warning
- 过拟合风险为 medium
- 需要实盘数据进一步验证
- 成本影响较大但可接受

**驳回（rejected）条件：**
- 核心指标存在 fail
- 过拟合风险为 high
- 收益集中在少数交易
- OOS 表现显著衰减
- 成本后不盈利

---

## 禁止事项

| 禁止行为 | 原因 |
|---------|------|
| ❌ 为差策略找借口 | 评审必须客观，不可因"用户辛苦了"而降低标准 |
| ❌ 仅因回测盈利就通过 | 盈利只是最低门槛，还需检查稳健性、过拟合、成本影响 |
| ❌ 绕过评审门卡 | 未通过评审的策略不得进入 `runtime_ready` 状态 |
| ❌ 混淆工程质量与策略质量 | 代码写得好不等于策略赚钱，策略赚钱不等于策略稳健 |
| ❌ 使用模糊的风险描述 | "可能有风险"是无效表述，必须说明"什么风险、多大、什么条件下触发" |
| ❌ 修改 StrategySpec 参数 | 评审只负责判断，修改是 strategy-designer Skill 的职责 |
| ❌ 生成信号代码或执行订单 | 这是 signal-runtime-builder 和 execution-guard 的职责 |
| ❌ 修改 lifecycle_state 到 `review_passed` / `review_rejected` 以外的状态 | 本 Skill 只能将状态从 `backtest_done` 推进到 `review_passed` 或 `review_rejected` |

---

## 最终检查清单

在输出 ReviewReport 之前，Agent 必须确认以下事项：

- [ ] 决策明确——是 `approved`、`paper_trade_first` 还是 `rejected`，不可含糊
- [ ] 所有风险描述都是具体的、可量化的，不存在"可能有风险"等模糊表述
- [ ] 可以用一句话解释为什么通过/为什么驳回
- [ ] `strengths` 列表中的每一项都有数据支撑
- [ ] `risks` 列表中的每一项都说明了触发条件和潜在影响
- [ ] 如果驳回，`required_actions` 给出了具体的改进方向
- [ ] 如果通过，`recommended_next_step` 明确指向下一个 Skill（signal-runtime-builder）
- [ ] 过拟合评估有依据（不是"看起来还好"）
- [ ] 成本影响已量化

---

## 交互指南

### 评审报告模板

```
## 评审结论

**决策：[approved / paper_trade_first / rejected]**

[一段话总结]

## 核心指标

| 指标 | 值 | 评级 | 说明 |
|------|---|------|------|
| Sharpe | X.XX | ✅/⚠️/❌ | ... |
| 最大回撤 | X.XX% | ✅/⚠️/❌ | ... |
| ... | ... | ... | ... |

## 优势
1. [具体优势 + 数据支撑]

## 风险
1. [具体风险 + 触发条件 + 潜在影响]

## 过拟合评估
[结论 + 依据]

## 成本影响
[成本侵蚀比例 + 成本翻倍后是否仍盈利]

## 改进建议 / 下一步
[具体行动项]
```

---

## 参考资源

- **评审检查清单**：`backtest-reviewer/references/review-checklist.md`
- **指标解读指南**：`backtest-reviewer/references/metrics-guide.md`
- **评审报告模板**：`backtest-reviewer/assets/review_template.json`
- **数据对象定义**：`shared/schemas/data_objects.md`
- **生命周期规范**：`shared/schemas/lifecycle.md`
