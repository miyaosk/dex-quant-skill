---
name: dex-quant-skill
description: >
  Crypto perpetual futures quantitative trading skill. Users describe strategy intent in natural language
  (e.g. "build me a MACD strategy for BTC with 5x leverage"), Agent asks for entry/exit conditions and risk params,
  writes the strategy, runs it on historical data to produce trade signals (symbol + time + price + direction + SL/TP),
  feeds signals to backtest engine, outputs performance report. Includes genetic optimizer for auto parameter search.
  Use when user asks to: create/build trading strategies, backtest crypto strategies, optimize strategy parameters,
  analyze trade signals, run funding rate arbitrage, cross-asset portfolio backtesting (crypto + stocks + gold + DeFi).
  信号是策略产生的。策略跑数据产出信号，信号驱动回测。支持遗传寻优自动找最优参数。
---

# DEX Quant Skill — Strategy · Signal · Backtest · Optimize

## 核心理念

**信号是策略产生的。** 策略定义交易规则，在历史数据上运行产出具体信号（币种 + 时间 + 价格 + 方向 + 止盈止损），信号驱动回测引擎执行交易。

## Architecture

```
用户自然语言 (e.g. "帮我做一个 MACD 策略做 BTC")
     │
     ▼
┌─ Stage 1: Agent 写策略 ──────────────────────┐
│  · Agent 追问: 入场条件？盈亏比？杠杆？        │
│  · 用 Strategy + StrategyRule + Condition 组装 │
│  · strategy.describe() → 用户确认              │
└──────────────────────────────────────────────┘
     │
     ▼
┌─ Stage 2: 策略产出信号 ──────────────────────┐
│  · 策略在历史数据上逐 bar 运行                │
│  · 规则满足 → 产出 TradeSignal                │
│  · 信号 = 币种 + 时间 + 价格 + 方向 + SL/TP   │
│  · SignalLog 存储所有信号，可导出 JSON/CSV     │
└──────────────────────────────────────────────┘
     │
     ▼
┌─ Stage 3: 信号驱动回测 ──────────────────────┐
│  · data_client.py ← 拉取 Binance/yfinance 数据│
│  · backtest_engine.py ← 保证金/强平/资金费率   │
│  · 信号 → engine.open_long() / close_short()  │
└──────────────────────────────────────────────┘
     │
     ▼
┌─ Stage 4: 结果 + 优化 ──────────────────────┐
│  · 绩效报告 + 信号列表 → 返回用户             │
│  · 效果不好？→ 调参数重跑                     │
│  · 用 GeneticOptimizer 自动搜索最优参数        │
└──────────────────────────────────────────────┘
```

**无需 API Key**（全部使用交易所公开端点），国内访问可配置 `PROXY_URL` 环境变量。

---

## 流程详解

以用户说 **"帮我做一个 MACD 策略做 BTC，5 倍杠杆"** 为例：

### Stage 1 — Agent 写策略

1. Agent 追问：入场条件？→ "MACD 金叉做多，死叉做空"。盈亏比？→ "1:3"。止损？→ "5%"
2. Agent 组装策略：`build_macd_strategy(symbol="BTC-USDT-PERP", leverage=5, stop_loss_pct=0.05, take_profit_pct=0.15)`
3. 调 `strategy.describe()` 展示规则，用户确认

### Stage 2 — 策略产出信号

4. 拉数据：`data_client.get_perp_klines("BTCUSDT", "1d", limit=365)`
5. 逐 bar 运行策略 → 规则满足时产出 TradeSignal
6. 每个信号包含：币种、时间、价格、方向、止损价、止盈价、触发原因

### Stage 3 — 信号驱动回测

7. 信号 → `engine.open_long()` / `close_long()` / `open_short()` / `close_short()`
8. 引擎处理：保证金、杠杆、资金费率结算、强平检查

### Stage 4 — 结果 + 优化

9. 输出绩效报告 + 信号列表表格
10. 效果不好 → 建议调参数，或用 `GeneticOptimizer` 自动找最优
11. 最优参数 → 重新跑完整回测 → 策略稳定跑起来

策略与信号详细指南见 [references/signal-guide.md](references/signal-guide.md)

---

## 策略层 — signal_builder.py

Agent 写策略的核心模块：

| 组件 | 说明 |
|------|------|
| `Indicators` | 技术指标 — SMA / EMA / RSI / MACD / Bollinger / ATR / KDJ / 成交量均线 |
| `Condition` | 条件组合 — `above()` / `below()` / `cross_above()` / `cross_below()` / `&` / `\|` / `~` |
| `StrategyRule` | 策略规则 — 当条件满足执行动作（开多/开空/平多/平空）+ 杠杆/仓位/止损止盈 |
| `Strategy` | 策略组装 — 多规则 + 指标配置 + 逐 bar 评估 → 产出 TradeSignal |
| `TradeSignal` | 策略产出的信号 — 币种 + 时间 + 价格 + 方向 + 止盈止损 |
| `SignalLog` | 信号存储 — 查询/导出 JSON/CSV/DataFrame + 统计 |

**预设策略（一行调用）：**

| 函数 | 适用场景 | 用户说 |
|------|----------|--------|
| `build_macd_strategy()` | MACD 交叉 | "做一个 MACD 策略" |
| `build_ma_cross_strategy()` | 均线交叉 | "双均线金叉做多" |
| `build_rsi_strategy()` | RSI 反转 | "RSI 低于 30 做多" |
| `build_funding_rate_strategy()` | 费率套利 | "费率高做空收费率" |
| `build_bollinger_strategy()` | 布林带突破 | "跌破下轨做多" |

---

## 寻优层 — optimizer.py

用户不确定最优参数？遗传算法自动搜索。

| 组件 | 说明 |
|------|------|
| `ParameterSpace` | 定义参数搜索范围（int/float/choice） |
| `GeneticOptimizer` | 遗传算法 — 50 个体 × 30 代，锦标赛选择 + 均匀交叉 + 变异，支持提前终止 |
| `GridSearch` | 网格搜索 — 适合参数空间小的场景 |
| `OptimizationResult` | 结果 — 最优参数 + Top N + 收敛历史 |

**适应度函数 = 跑回测取夏普比率**（或用户指定的其他指标）。

---

## 数据层 — data_client.py

基于交易所公开 API，无需注册：

**加密货币（Binance）:**

| 方法 | 说明 |
|------|------|
| `get_perp_klines()` | 永续合约 K 线，1m-1d，自动分页，无限历史 |
| `get_funding_rate()` | 资金费率历史，每 8h 一条，自动分页 |
| `get_open_interest()` | 当前持仓量快照 |
| `get_open_interest_hist()` | 持仓量历史（⚠️ 仅 30 天） |
| `get_long_short_ratio()` | Top Trader 多空比（⚠️ 仅 30 天） |
| `get_mark_price()` | 当前标记价格 + 资金费率 |
| `get_exchange_info()` | 合约规格（杠杆上限/最小下单量等） |
| `get_spot_klines()` | 现货 K 线 |
| `get_token_history()` | PAXG/XAUT 等代币价格（CoinGecko，日线 365 天） |
| `list_perp_symbols()` | 列出所有永续合约 |

**美股 / 大宗商品 / 贵金属（yfinance）:**

| 方法 | 说明 |
|------|------|
| `get_stock_klines()` | 美股/ETF K 线（RWA:AAPL / RWA:SPY 等），30+ 年历史 |
| `get_commodity_klines()` | 大宗商品期货（COMM:WTI / COMM:NG / COMM:COPPER），10+ 年 |
| `get_metal_spot_klines()` | 贵金属现货（METAL:XAU-SPOT / METAL:XAG-SPOT），10+ 年 |

**DeFi（DeFi Llama）:**

| 方法 | 说明 |
|------|------|
| `get_protocol_tvl()` | 协议 TVL 历史（aave / compound / lido / curve 等） |
| `get_protocol_info()` | 协议当前信息（TVL、类别、链） |
| `get_defi_fees()` | 协议手续费/收入（24h / 7d / 30d） |
| `list_defi_protocols()` | 所有 DeFi 协议列表 |

详细参数与限制见 [references/data-sources.md](references/data-sources.md)

---

## 回测层 — backtest_engine.py

本地 Python 回测引擎，支持永续合约全部特性：

| 能力 | 说明 |
|------|------|
| 多空双向 | `open_long` / `open_short` / `close_long` / `close_short` |
| 杠杆 | 1x-125x |
| 保证金 | 逐仓（isolated）+ 全仓（cross） |
| 资金费率 | 使用真实历史数据，每 8h 结算 |
| 强制平仓 | 保证金率 <= 维持保证金率时触发 |
| 止损/止盈 | bar 内 high/low 判断触发 |
| 滑点 | 固定 bps 模型 |
| 手续费 | Maker 0.02% / Taker 0.05% |

保证金/强平计算公式见 [references/backtest-engine.md](references/backtest-engine.md)

---

## 使用指令

### Agent 如何处理用户请求

**核心原则：策略是 Agent 写的。信号是策略产出的。用户全程用自然语言。**

1. **理解意图** — 用户说 "帮我做一个 MACD 策略"
2. **追问细节** — 入场条件？出场条件？盈亏比？杠杆？止损？标的？
3. **写策略** — 读 [references/signal-guide.md](references/signal-guide.md)，用 `Strategy` + `StrategyRule` 组装
4. **展示确认** — `strategy.describe()` 展示规则，用户确认
5. **跑回测** — 策略产出信号 → 信号驱动 BacktestEngine → 输出绩效 + 信号列表
6. **解读结果** — 夏普、回撤、胜率、信号表格
7. **迭代优化** — 效果不好？调参数重跑，或用遗传寻优

### Agent 如何解读回测报告

**四个维度必须覆盖：**

1. **收益风险比** — 年化收益、夏普（>2 优秀，1-2 良好，<1 需优化）、最大回撤（>30% 警告）
2. **资金费率损益** — 套利策略的核心收益来源
3. **风控状况** — 强平次数（>0 建议降杠杆）、保证金使用率峰值
4. **交易效率** — 胜率、盈亏比、手续费+滑点占收益比

---

## 策略模板

| 模板 | 适用场景 |
|------|----------|
| `assets/templates/custom_signal_strategy.py` | **推荐** — 策略产出信号 + 回测（用户自然语言定义） |
| `assets/templates/optimize_strategy.py` | 遗传寻优 — 自动搜索最优参数 |
| `assets/templates/perpetual_ma_cross.py` | 永续合约均线交叉（趋势跟踪） |
| `assets/templates/funding_rate_arb.py` | 资金费率套利（永续+现货对冲） |
| `assets/templates/cross_asset_portfolio.py` | 跨资产组合再平衡 |

---

## 参考文档

| 文档 | 内容 | 何时阅读 |
|------|------|----------|
| [references/signal-guide.md](references/signal-guide.md) | **策略写法、信号格式、条件映射、遗传寻优用法** | **收到用户策略需求时（首先阅读）** |
| [references/data-sources.md](references/data-sources.md) | 各 API 端点详细参数、限流、数据限制 | 拉数据时 |
| [references/backtest-engine.md](references/backtest-engine.md) | 保证金/杠杆/资金费率/强平计算公式 | 编写策略或分析结果时 |
| [references/data-models.md](references/data-models.md) | Symbol 命名、资产类型、支持的合约列表 | 构造请求时 |
| [references/strategy-sdk.md](references/strategy-sdk.md) | 引擎 API 函数 + 完整策略示例 | 编写策略代码时 |
| [references/interaction-flows.md](references/interaction-flows.md) | 端到端交互场景与验收用例 | 理解完整流程时 |

---

## 仍需协调的数据（3 项）

以下数据没有免费公开 API，需要付费服务或自建采集：

| # | 数据 | 问题 | 推荐方案 |
|---|------|------|----------|
| 1 | **聚合爆仓数据** | Binance 没有聚合爆仓统计端点 | Coinglass API（付费 ~$50/月） |
| 2 | **持仓量/多空比 >30 天历史** | Binance 仅保留最近 30 天 | 自建 cron 定时采集 + 存数据库，或 Coinglass |
| 3 | **DeFi 收益率 APY 历史** | DeFi Llama yields 端点需 Pro Key | 申请 DeFi Llama Pro，或自建链上采集 |
