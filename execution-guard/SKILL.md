---
name: execution-guard
description: >
  Convert trade signals into executable orders with comprehensive risk checks. Performs position limit check,
  daily loss threshold check, duplicate order prevention, cooldown check, venue health check, and generates
  order plans. Use when user asks to execute trades, check if an order is allowed, or manage live trading risk.
  将交易信号转成可执行订单，完成全面风控检查，确保交易安全。
---

# Execution Guard Skill

## 目标

将 SignalEvent 转化为安全可执行的订单，通过全面的风控检查确保每一笔交易都在可控范围内。本 Skill 是策略生命周期中的最后一道安全关卡——信号说"该做"，Guard 决定"能不能做"。

本 Skill 的职责是：**接收信号 → 风控检查 → 生成订单计划 → 请求确认 → 执行记录**。

核心原则：**宁可错过交易，绝不失控冒险**。

---

## 触发条件

当用户表达以下意图时激活本 Skill：

- "执行这个信号"
- "这个信号可以下单吗？"
- "帮我检查一下这笔交易的风险"
- "开启自动执行"
- "当前仓位风控状态怎么样？"
- "激活/关闭 kill switch"
- 任何涉及订单执行、风控检查、交易安全管理的请求

---

## 输入

| 输入项 | 是否必须 | 说明 |
|--------|---------|------|
| SignalEvent | **必须** | 信号运行时生成的交易信号，遵循 `shared/schemas/data_objects.md` |
| 账户状态 | **必须** | 当前账户余额、已用保证金、可用余额 |
| 持仓状态 | **必须** | 当前所有持仓的详情（标的、方向、数量、未实现盈亏等） |
| 风控规则 | **必须** | 风控配置参数（来自 StrategySpec.risk_limits 或自定义覆盖） |
| 执行模式 | **必须** | `manual`（人工确认）/ `semi_auto`（半自动）/ `auto`（全自动） |

---

## 输出

| 输出项 | 说明 |
|--------|------|
| ExecutionDecision | 执行决策，遵循 `shared/schemas/data_objects.md` 中的 ExecutionDecision 定义 |

### ExecutionDecision 核心字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `allowed` | `boolean` | 是否允许执行 |
| `risk_checks` | `dict[str, RiskCheckResult]` | 各项风控检查结果 |
| `order_plan` | `OrderPlan` | 订单计划（仅 allowed=true 时填写） |
| `rejection_reason` | `string` | 拒绝原因（仅 allowed=false 时填写） |
| `execution_mode` | `string` | 实际执行模式 |
| `requires_confirmation` | `boolean` | 是否需要用户确认 |

---

## 工作流程

### 第 1 步：信号验证

验证收到的 SignalEvent 是否有效：

1. 检查 `signal_id` 是否非空且唯一
2. 检查 `strategy_id` 是否与当前活跃策略匹配
3. 检查信号是否在有效期内（`ttl_seconds` 未过期）
4. 检查信号来源策略的 `lifecycle_state` 是否允许执行

如果信号无效，立即拒绝并记录原因。

### 第 2 步：仓位上限检查

检查新订单是否会超出仓位限制：

- 当前持仓市值 + 新订单市值 ≤ 总资金 × `max_position_pct`
- 当前持仓数量 < `max_concurrent_positions`
- 如果超限，拒绝并说明当前仓位占比和限制值

### 第 3 步：日内亏损阈值检查

检查当日已实现亏损是否超过阈值：

- 当日已实现亏损 + 当前持仓未实现亏损 ≤ 总资金 × `max_daily_loss`
- 如果超限，拒绝并说明当日亏损情况
- 当日亏损的计算以 UTC 00:00 为日切时间

### 第 4 步：重复下单防护

检查是否存在重复订单：

- 同一 `signal_id` 不可重复执行
- 同一标的、同方向的订单在去重窗口内不可重复
- 查询最近 N 笔订单记录进行比对

### 第 5 步：冷却期检查

检查上一笔交易后是否经过了足够的冷却时间：

- 上次出场时间到当前时间 ≥ 冷却期
- 冷却期由 StrategySpec 或自定义配置决定

### 第 6 步：交易所可用性检查

验证目标交易所是否正常运行：

- API 连接是否正常
- 交易对是否可交易（未暂停/退市）
- 系统维护状态
- 如果交易所不可用，拒绝并标记为 `venue_unavailable`

### 第 7 步：账户余额检查

检查账户是否有足够的保证金：

- 可用余额 ≥ 新订单所需保证金
- 新订单所需保证金 = 订单市值 / 杠杆
- 保留安全边际（可用余额 - 安全余量 ≥ 所需保证金）

### 第 8 步：杠杆限制检查

验证杠杆是否在允许范围内：

- 实际杠杆 ≤ 策略定义的 `leverage`
- 实际杠杆 ≤ 交易所允许的最大杠杆
- 综合杠杆（含所有持仓）不超过安全阈值

### 第 9 步：黑名单时段过滤

检查当前时间是否在禁止交易的时段内：

- 已知的高风险时段（如重大经济数据发布、交易所维护）
- 自定义的禁止交易时间窗口
- 流动性极低的时段（如周末凌晨）

### 第 10 步：相关性暴露检查

检查新仓位是否会导致过度集中的相关性暴露：

- 同类资产的仓位总和不超过限制
- 高度相关的标的不同时持有同方向仓位
- 例如：已做多 BTCUSDT，不建议同时做多 ETHUSDT（高相关性）

### 第 11 步：Kill Switch（熔断）检查

检查是否有全局熔断信号：

- 手动激活的 kill switch
- 自动触发的熔断条件（如账户回撤超过阈值）
- kill switch 激活时，拒绝所有新订单

### 第 12 步：生成执行决策

综合以上所有检查结果，生成 ExecutionDecision：

**全部通过 → 生成订单计划**：
- 构建 OrderParams（标的、方向、类型、数量、价格等）
- 根据执行模式决定是否需要用户确认
- `manual` → 必须用户确认
- `semi_auto` → 低风险自动执行，高风险需确认
- `auto` → 自动执行（需用户提前授权）

**任一检查失败 → 拒绝执行**：
- 记录哪项检查失败
- 记录具体的拒绝原因和当前值/限制值
- 建议用户如何解决（降低仓位？等待冷却期？）

---

## 禁止事项

| 禁止行为 | 原因 |
|---------|------|
| ❌ 跳过风控检查直接执行 | 每一笔交易都必须经过完整的风控检查链 |
| ❌ 未经用户授权开启自动执行 | 执行模式必须由用户显式设置 |
| ❌ 忽略风控拦截原因 | 每次拦截都必须记录清晰的原因 |
| ❌ 在状态写入失败后执行交易 | 如果执行前的状态记录失败，必须中止执行 |
| ❌ 修改策略定义或信号内容 | Guard 只做风控判断，不修改上游数据 |
| ❌ 在 kill switch 激活时允许执行 | kill switch 是最高级别的安全机制 |
| ❌ 生成信号或部署监控 | 这是 signal-runtime-builder 的职责 |
| ❌ 修改 lifecycle_state 到 `execution_enabled` / `paper_trading` / `live_trading` / `paused` 以外的状态 | 本 Skill 只能推进执行阶段的状态 |

---

## 最终检查清单

在输出 ExecutionDecision 之前，Agent 必须确认以下事项：

- [ ] 每笔执行决策都有完整的风控检查记录（`risk_checks` 非空）
- [ ] 每次拒绝都有清晰、具体的原因（不是"风控未通过"）
- [ ] 每个订单都可以追溯到源信号（`signal_id` 关联）
- [ ] 执行模式已确认（manual/semi_auto/auto）
- [ ] 如果是 manual 或 semi_auto 高风险订单，`requires_confirmation = true`
- [ ] 订单参数完整（symbol, side, order_type, quantity, leverage, margin_mode）
- [ ] 状态已成功写入后才允许执行
- [ ] kill switch 状态已检查

---

## 交互指南

### 风控检查结果模板

```
## 🛡️ 风控检查结果

📌 信号来源: {strategy_name} | {signal_id}
📈 信号方向: {signal_type} {symbol}

### 检查项

| # | 检查项 | 结果 | 详情 |
|---|--------|------|------|
| 1 | 仓位上限 | ✅/❌ | 当前 X% / 上限 Y% |
| 2 | 日内亏损 | ✅/❌ | 当日 -X% / 上限 -Y% |
| 3 | 重复下单 | ✅/❌ | 无重复 / 已存在相同订单 |
| 4 | 冷却期 | ✅/❌ | 上次交易 Xmin 前 / 冷却 Ymin |
| 5 | 交易所可用 | ✅/❌ | 正常 / 维护中 |
| 6 | 余额充足 | ✅/❌ | 可用 $X / 需要 $Y |
| 7 | 杠杆合规 | ✅/❌ | 使用 Xx / 上限 Yx |
| 8 | 时段检查 | ✅/❌ | 正常时段 / 黑名单时段 |
| 9 | 相关性暴露 | ✅/❌ | 无过度暴露 / 已有相关仓位 |
| 10 | Kill Switch | ✅/❌ | 未激活 / 已激活 |

### 决策

**[✅ 允许执行 / ❌ 拒绝执行]**

[如果允许] 订单计划:
- 标的: {symbol}
- 方向: {side}
- 类型: {order_type}
- 数量: {quantity}
- 杠杆: {leverage}x
- 需要确认: {yes/no}

[如果拒绝] 原因: {rejection_reason}
建议: {suggestion}
```

---

## 执行模式说明

| 模式 | 中文 | 行为 | 适用场景 |
|------|------|------|---------|
| `manual` | 人工确认 | 每笔订单都需要用户显式确认后执行 | 初次使用、高风险策略、大额交易 |
| `semi_auto` | 半自动 | 符合预设条件的订单自动执行，超出条件的需确认 | 日常运行 |
| `auto` | 全自动 | 通过风控的订单自动执行，无需确认 | 成熟策略、已验证的低风险策略 |

### 半自动模式的自动执行条件

以下条件全部满足时可自动执行，否则需用户确认：

- 订单金额 ≤ 单笔上限的 50%
- 当日亏损 ≤ 日亏损上限的 50%
- 不是反向平仓（止损/止盈可自动执行）
- 距离上次用户确认 < 4 小时

---

## 参考资源

- **风控规则详解**：`execution-guard/references/risk-rules.md`
- **订单规范**：`execution-guard/references/order-spec.md`
- **风控检查器实现**：`execution-guard/scripts/risk_checker.py`
- **数据对象定义**：`shared/schemas/data_objects.md`（ExecutionDecision、SignalEvent）
- **生命周期规范**：`shared/schemas/lifecycle.md`
