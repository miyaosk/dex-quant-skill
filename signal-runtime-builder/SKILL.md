---
name: signal-runtime-builder
description: >
  Convert an approved StrategySpec into a real-time or near-real-time signal monitoring service.
  Generates signal computation logic, state machine, dedup rules, alert templates, and logging structure.
  Use when user asks to deploy monitoring, watch for signals, set up alerts, or check real-time strategy status.
  将通过评审的策略定义转成实时/准实时信号监控服务，生成信号计算逻辑、状态机、告警模板。
---

# Signal Runtime Builder Skill

## 目标

将通过评审的 StrategySpec 转化为可运行的实时信号监控服务。本 Skill 是策略从"纸上谈兵"到"真实监控"的桥梁——它不做交易决策，只负责准确、可靠地生成信号。

本 Skill 的职责是：**验证评审状态 → 解析策略逻辑 → 构建信号引擎 → 配置状态机 → 设定去重/冷却 → 生成告警模板 → 输出运行时配置**。

---

## 准入门卡

**硬性要求**：策略必须满足以下条件之一才能进入信号构建：

- `review_status == "passed"` 且 `lifecycle_state == "review_passed"`
- `review_status == "conditional"` 且用户显式确认接受附加条件

未通过评审的策略**绝对不可**构建信号服务。如果用户要求对未评审策略构建信号，应拒绝并引导用户先完成评审（backtest-reviewer Skill）。

---

## 触发条件

当用户表达以下意图时激活本 Skill：

- "帮我部署这个策略的信号监控"
- "把这个策略跑起来看看"
- "设置一下实时信号推送"
- "这个策略通过了，帮我配置实时监控"
- "我想看实时信号"
- 任何涉及信号部署、实时监控、告警配置的请求

---

## 输入

| 输入项 | 是否必须 | 说明 |
|--------|---------|------|
| StrategySpec（已通过评审） | **必须** | 完整的策略定义，`review_status` 必须为 `passed` 或 `conditional` |
| 运行频率 | 建议提供 | 信号计算频率，默认等于策略的 `timeframe` |
| 数据源配置 | 建议提供 | 实时数据来源（默认 Binance WebSocket/REST） |
| 通知配置 | 可选 | 告警通知方式（日志/Webhook/Telegram 等） |
| 去重/冷却规则 | 可选 | 自定义去重和冷却参数（默认使用标准配置） |

---

## 输出

| 输出项 | 说明 |
|--------|------|
| 运行时配置 | 信号引擎的完整运行参数 |
| 信号状态机 | 状态转换定义和图示 |
| 触发逻辑 | 基于 StrategySpec 的信号判断代码 |
| 告警模板 | 信号触发时的通知消息格式 |
| 日志结构 | 运行日志的格式和存储规范 |
| SignalEvent | 生成的信号事件，遵循 `shared/schemas/data_objects.md` 中的 SignalEvent 定义 |

---

## 工作流程

### 第 1 步：准入验证

检查策略是否满足信号构建的前置条件：

1. 确认 `review_status` 为 `passed` 或 `conditional`
2. 确认 `lifecycle_state` 为 `review_passed`
3. 如果是 `conditional`，列出附加条件并要求用户确认
4. 如果未通过评审，拒绝并说明原因

### 第 2 步：解析策略逻辑

从 StrategySpec 提取信号生成所需的全部信息：

1. 提取 `features` 列表 → 确定需要计算的指标及其参数
2. 提取 `entry_rules` → 构建入场信号判断逻辑
3. 提取 `exit_rules` → 构建出场信号判断逻辑
4. 提取 `data_requirements` → 确定需要订阅的数据类型
5. 提取 `timeframe` → 确定信号计算频率
6. 提取 `universe` → 确定需要监控的交易对

### 第 3 步：构建信号计算流程

定义每根 K 线到达时的处理流程（详见 `references/runtime-spec.md`）：

```
K 线收盘 → 获取最新数据 → 计算全部指标 → 检查入场/出场规则
    → 触发信号 → 生成 SignalEvent → 发送告警
    → 未触发 → 记录"未触发原因"日志
```

### 第 4 步：配置状态机

根据策略逻辑配置信号状态机（详见 `references/state-machine.md`）：

- 定义状态集合：idle → watching → entry_triggered → position_open → exit_triggered → cooldown
- 定义状态转换条件
- 处理多标的的独立状态管理
- 配置异常恢复机制

### 第 5 步：配置去重与冷却

设置信号去重和冷却规则，避免重复信号轰炸：

- **去重规则**：同方向信号在 N 根 K 线内不重复触发（默认 N = 策略 timeframe 的 3 倍）
- **冷却期**：上一笔交易完成后的等待时间（默认 = 策略 timeframe × 2）
- **信号有效期（TTL）**：信号生成后的有效窗口（默认 = 1 个 bar 周期）

### 第 6 步：生成告警模板

构建信号触发时的通知消息格式：

```
📊 [策略名称] 信号触发
━━━━━━━━━━━━━━━
⏰ 时间: 2026-03-12 14:00:00 UTC
📌 标的: BTCUSDT
📈 方向: 做多 (open_long)
💰 当前价格: $67,432.50
🎯 建议入场: $67,432.50
🛑 建议止损: $66,083.85 (-2.0%)
✅ 建议止盈: $71,478.45 (+6.0%)
📊 信号强度: 0.82
🔍 触发规则: entry_long_1
📋 指标快照: SMA20=65,100 SMA60=63,200 Volume=1.5x avg
━━━━━━━━━━━━━━━
⚠️ 此为信号提示，非交易指令。执行需经风控检查。
```

### 第 7 步：配置日志结构

定义运行时的日志记录规范：

1. **信号触发日志**：完整的 SignalEvent + 触发原因 + 指标快照
2. **非触发日志**：当前指标值 + 哪些条件未满足 + 距离触发还差多少
3. **状态变更日志**：状态机每次状态转换的记录
4. **异常日志**：数据获取失败、计算错误、连接中断等
5. **心跳日志**：定期（每 10 个 bar）输出运行状态摘要

### 第 8 步：输出运行时包

将以上配置整合为可部署的运行时包：

1. 运行时配置 JSON
2. 信号计算逻辑（Python 代码或伪代码）
3. 状态机定义
4. 告警模板
5. 日志配置
6. 更新 StrategySpec 的 `lifecycle_state` 为 `runtime_ready`

---

## 禁止事项

| 禁止行为 | 原因 |
|---------|------|
| ❌ 修改策略定义（StrategySpec） | 信号服务必须忠实执行策略逻辑，修改是 strategy-designer 的职责 |
| ❌ 未经评审构建信号服务 | 评审是信号构建的硬性前置条件（生命周期约束 C-01） |
| ❌ 自动进入实盘交易 | 信号服务只生成信号，执行是 execution-guard 的职责 |
| ❌ 丢弃判断上下文 | 每个信号必须携带完整的触发原因和指标快照 |
| ❌ 仅记录触发信号 | 必须同时记录"为什么没有触发"——这对调试和策略优化至关重要 |
| ❌ 忽略去重和冷却 | 无去重的信号系统会产生大量重复告警 |
| ❌ 修改 lifecycle_state 到 `runtime_ready` / `monitoring_live` 以外的状态 | 本 Skill 只能将状态推进到 `runtime_ready` 和 `monitoring_live` |

---

## 最终检查清单

在输出运行时包之前，Agent 必须确认以下事项：

- [ ] 策略已通过评审（`review_status == "passed"` 或 `"conditional"`）
- [ ] 所有 `features` 中定义的指标都有对应的计算逻辑
- [ ] 所有 `entry_rules` 和 `exit_rules` 都已转化为可执行的判断条件
- [ ] 状态机覆盖了所有正常和异常场景
- [ ] 去重和冷却规则已配置
- [ ] 告警模板包含了所有关键信息
- [ ] 日志结构包含"触发"和"未触发"两种情况
- [ ] 崩溃恢复机制已定义（状态持久化 + 重启行为）
- [ ] 多标的场景下每个标的有独立的状态管理

---

## 参考资源

- **运行时规范**：`signal-runtime-builder/references/runtime-spec.md`
- **状态机定义**：`signal-runtime-builder/references/state-machine.md`
- **信号运行时实现**：`signal-runtime-builder/scripts/signal_runtime.py`
- **数据对象定义**：`shared/schemas/data_objects.md`（SignalEvent）
- **生命周期规范**：`shared/schemas/lifecycle.md`
