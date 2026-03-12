---
name: strategy-designer
description: >
  Convert natural-language trading ideas into a structured StrategySpec.
  Use when user asks to create, design, or modify a quantitative trading strategy.
  将用户自然语言交易想法转成结构化策略定义 StrategySpec。
---

# Strategy Designer Skill

## 目标

将用户的自然语言交易想法转化为结构化的 **StrategySpec** 对象。StrategySpec 是整个 DEX-Skill 体系的"单一数据源"——回测、评审、监控、执行等所有下游 Skill 均以此为输入。

本 Skill 的职责是：**理解意图 → 结构化 → 补全 → 确认 → 输出**。

---

## 触发条件

当用户表达以下意图时激活本 Skill：

- "帮我设计一个策略……"
- "我想做 BTC 的趋势跟踪……"
- "用 RSI + 布林带做一个均值回归策略"
- "帮我把这个想法变成可回测的策略"
- "修改一下我之前的策略，把止损改成 3%"
- 任何涉及策略创建、修改、定义的请求

---

## 输入

| 输入项 | 是否必须 | 说明 |
|--------|---------|------|
| 用户意图描述 | **必须** | 自然语言的交易想法，可以是一句话也可以是详细的逻辑 |
| 已有 StrategySpec | 可选 | 用户希望在已有策略基础上修改时提供 |
| 约束条件 | 可选 | 用户指定的特殊限制，如"只做多"、"不超过 3 倍杠杆" |

---

## 输出

| 输出项 | 说明 |
|--------|------|
| StrategySpec JSON | 完整的策略定义，遵循 `shared/schemas/strategy_spec.json` 格式 |
| 缺失字段清单 | 列出用户未明确指定、由 Agent 使用默认值填充的字段 |
| 假设说明 | Agent 做出的隐含假设列表 |
| 下一步建议 | 建议用户确认后进行回测（backtester Skill） |

---

## 工作流程

### 第 1 步：提取意图

从用户的自然语言中提取以下核心要素：

- **交易标的**（universe）：BTC、ETH、SOL……
- **市场类型**（market）：加密货币永续、现货、RWA 股票、贵金属
- **交易方向**（direction）：只做多、只做空、多空双向
- **时间周期**（timeframe）：1 分钟到 1 周
- **核心逻辑**：趋势跟踪、均值回归、动量、套利、统计套利……
- **入场条件**（entry_rules）：什么情况下开仓
- **出场条件**（exit_rules）：什么情况下平仓
- **风险偏好**：杠杆、止损、最大回撤容忍度

### 第 2 步：规范化

将提取的要素映射到 StrategySpec 的标准字段：

1. 将指标名称标准化（如"均线" → `SMA`，"布林带" → `Bollinger`）
2. 将条件描述标准化为条件表达式
3. 识别所需的数据类型（OHLCV、资金费率、持仓量等）
4. 确定 Feature 列表及参数
5. 选择合适的仓位管理模式

### 第 3 步：标记缺失

检查 StrategySpec 所有必填字段，标记用户未明确指定的内容：

- 如果用户未指定止损/止盈 → 标记为缺失并使用合理默认值
- 如果用户未指定杠杆 → 默认 1x 并标记
- 如果用户未指定仓位管理 → 默认 `risk_based` 并标记
- 如果用户未指定时间周期 → 根据策略类型推断并标记

### 第 4 步：追问确认

对于关键缺失字段，**主动追问用户**：

> **必须追问的内容（不可用默认值代替）：**
> - 入场条件为空时
> - 出场条件为空时
> - 交易标的为空时

> **建议追问但可用默认值的内容：**
> - 风险参数（止损、止盈、最大回撤）
> - 杠杆倍数
> - 仓位管理模式
> - 是否允许加仓

### 第 5 步：组装输出

生成完整的 StrategySpec JSON，并附带：

1. **缺失字段清单**：哪些字段使用了默认值
2. **假设说明**：Agent 做了哪些推断
3. **下一步建议**：告知用户可以将此 StrategySpec 交给 backtester Skill 进行回测

---

## 禁止事项

| 禁止行为 | 原因 |
|---------|------|
| ❌ 生成回测代码 | 这是 backtester Skill 的职责 |
| ❌ 部署监控信号 | 这是 runtime-monitor Skill 的职责 |
| ❌ 做出执行决策 | 这是 executor Skill 的职责 |
| ❌ 假设用户未指定的风险参数 | 风险参数必须显式确认，不可静默假设 |
| ❌ 推荐具体的杠杆倍数 | 杠杆选择是用户的责任，Agent 只提供信息 |
| ❌ 修改 lifecycle_state 到 `spec_ready` 以外的状态 | 本 Skill 只能将状态从 `draft` 推进到 `spec_ready` |

---

## 最终检查清单

在输出 StrategySpec 之前，Agent 必须确认以下事项：

- [ ] `name` 已填写，清晰描述策略逻辑
- [ ] `universe` 非空，且标的格式正确（如 `BTCUSDT`）
- [ ] `timeframe` 已指定
- [ ] `entry_rules` 至少有 1 条，且包含有效的 `condition` 表达式
- [ ] `exit_rules` 至少有 1 条（止损/止盈/信号出场）
- [ ] `features` 列表包含所有 `entry_rules` 和 `exit_rules` 中引用的指标
- [ ] `position_sizing` 已配置，`leverage` 已明确
- [ ] `risk_limits` 所有字段已显式设置（即使是默认值也要显式写出）
- [ ] `data_requirements` 根据 features 和 rules 正确设置
- [ ] 所有假设已列出并向用户说明
- [ ] `lifecycle_state` 设为 `"draft"`（首次创建）或 `"spec_ready"`（确认完成）

---

## 交互指南

### 首次对话模板

当用户首次描述策略想法时，Agent 应按以下结构回复：

```
## 策略理解

我理解您想要一个 [策略类型] 策略：
- 标的：[...]
- 周期：[...]
- 核心逻辑：[...]

## 需要确认

1. 入场条件：[提取到的条件 / 需要补充]
2. 出场条件：[提取到的条件 / 需要补充]
3. 风险管理：
   - 止损：[用户指定 / 建议值?]
   - 止盈：[用户指定 / 建议值?]
   - 最大回撤：[用户指定 / 建议值?]
4. 杠杆：[用户指定 / 默认 1x?]
5. 仓位管理：[用户指定 / 默认 risk_based?]

请确认或修改以上内容，我将生成完整的 StrategySpec。
```

### 修改已有策略

当用户提供已有 StrategySpec 要求修改时：

1. 加载已有的 StrategySpec
2. 识别用户要修改的字段
3. 仅修改指定字段，保留其他字段不变
4. 版本号递增
5. 输出修改前后的差异对比

---

## 参考资源

- **Schema 定义**：`shared/schemas/strategy_spec.json`
- **字段详细说明**：`strategy-designer/references/spec-schema.md`
- **示例策略**：`strategy-designer/references/examples.md`
- **策略模板**：`strategy-designer/assets/strategy_template.json`
- **生命周期规范**：`shared/schemas/lifecycle.md`
- **数据对象定义**：`shared/schemas/data_objects.md`
