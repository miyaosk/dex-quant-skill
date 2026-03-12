---
name: dex-quant-skill
description: >
  AI quantitative trading platform with 5 specialized sub-skills. Covers the full workflow from natural language
  strategy design, backtesting, review/approval, real-time signal monitoring, to risk-controlled execution.
  Use when user asks to: design trading strategies, create quant strategies, backtest, analyze backtest results,
  monitor signals, execute trades, manage trading risk, optimize strategy parameters, or anything related to
  quantitative trading for crypto perpetuals, spot, stocks, metals, and commodities.
  AI 量化交易平台，5 个子 Skill 覆盖策略设计→回测→评审→信号监控→执行的完整链路。
---

# DEX Quant Skill — AI 量化 Agent 编排器

本 Skill 是 5 个量化子 Skill 的统一入口。根据用户意图自动路由到正确的子 Skill。

## 子 Skill 路由表

| 用户意图 | 路由到 | 子 Skill 路径 |
|---------|--------|--------------|
| 设计策略、描述交易想法、修改策略 | **strategy-designer** | [strategy-designer/SKILL.md](strategy-designer/SKILL.md) |
| 生成回测代码、跑回测、实现策略 | **backtest-coder** | [backtest-coder/SKILL.md](backtest-coder/SKILL.md) |
| 评审回测、分析结果、是否上线 | **backtest-reviewer** | [backtest-reviewer/SKILL.md](backtest-reviewer/SKILL.md) |
| 部署监控、实时信号、设置告警 | **signal-runtime-builder** | [signal-runtime-builder/SKILL.md](signal-runtime-builder/SKILL.md) |
| 执行交易、风控检查、下单、kill switch | **execution-guard** | [execution-guard/SKILL.md](execution-guard/SKILL.md) |

## 工作流程

```
用户自然语言
    │
    ▼ 路由判断
    │
    ├─ "帮我设计一个 BTC 策略"     → 读取 strategy-designer/SKILL.md
    ├─ "生成回测代码，跑一下"       → 读取 backtest-coder/SKILL.md
    ├─ "回测结果怎么样？能上线吗"   → 读取 backtest-reviewer/SKILL.md
    ├─ "部署信号监控"               → 读取 signal-runtime-builder/SKILL.md
    └─ "执行这个信号 / 检查风控"    → 读取 execution-guard/SKILL.md
```

## 使用指南

1. **识别用户意图** — 判断属于策略设计/回测/评审/监控/执行哪个阶段
2. **读取对应子 Skill** — 按路由表读取对应的 SKILL.md，严格遵循其工作流程
3. **读取 shared schemas** — 需要 StrategySpec 格式时读取 [shared/schemas/strategy_spec.json](shared/schemas/strategy_spec.json)
4. **遵守生命周期** — 策略状态必须按 [shared/schemas/lifecycle.md](shared/schemas/lifecycle.md) 定义的顺序推进
5. **不越权** — 每个子 Skill 有明确的"禁止事项"，不可跨越

## 核心对象

所有子 Skill 围绕同一份 **StrategySpec** 工作（[schema](shared/schemas/strategy_spec.json)）。

全部数据对象定义见 [shared/schemas/data_objects.md](shared/schemas/data_objects.md)：
- StrategySpec — 策略定义（单一真相源）
- BacktestConfig — 回测配置
- ReviewReport — 评审报告
- SignalEvent — 信号事件
- ExecutionDecision — 执行决策

## 生命周期约束

```
draft → spec_ready → backtest_ready → backtest_done
    → review_passed / review_rejected
    → runtime_ready → monitoring_live → execution_enabled
    → paper_trading / live_trading → paused / retired
```

**硬性规则：**
- 未通过 backtest-reviewer → 不得进入 signal-runtime-builder
- 未开启执行权限 → 不得进入 live_trading
- 风控异常 → 任何时候可打回 paused

## 典型对话示例

**用户**：我想做一个 ETH 4h 趋势策略
→ 路由到 strategy-designer，追问入场出场条件、止损止盈、杠杆

**用户**：用这个策略跑 2022-2025 回测
→ 路由到 backtest-coder，生成代码并执行回测

**用户**：表现怎么样？能上线吗？
→ 路由到 backtest-reviewer，8 步评审流程

**用户**：通过了，先部署监控
→ 路由到 signal-runtime-builder，生成信号服务

**用户**：这个信号可以执行吗？
→ 路由到 execution-guard，10 项风控检查

## 支持的资产

| 类型 | 数据源 | 示例 |
|------|--------|------|
| 加密永续合约 | Binance Futures | BTCUSDT, ETHUSDT |
| 加密现货 | Binance Spot | BTC/USDT |
| 代币价格 | CoinGecko | SOL, AVAX |
| 美股/RWA | Yahoo Finance | AAPL, TSLA |
| 贵金属 | Yahoo Finance | GC=F (黄金), SI=F (白银) |
| 大宗商品 | Yahoo Finance | CL=F (原油) |
| DeFi 协议 | DeFi Llama | Uniswap, Aave |
