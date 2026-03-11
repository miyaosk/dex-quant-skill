---
name: dex-quant-skill
description: >
  Crypto perpetual futures quantitative skill with 4-stage workflow: Signal Design → Strategy Building → Trade Execution → Backtesting.
  Users can describe trading signals in natural language (e.g. "when RSI drops below 30 and funding rate is negative, go long BTC with 5x leverage"),
  and the Agent will automatically: (1) parse the signal intent; (2) assemble composable signal conditions using Indicators + Conditions;
  (3) build a complete strategy with leverage, margin, stop-loss/take-profit; (4) run local backtest with real Binance data.
  Fetches market data from Binance/CoinGecko/Yahoo Finance/DeFi Llama (no API key needed).
  Use when user asks to: create/customize trading signals, backtest crypto strategies, analyze funding rates,
  build quantitative strategies, run cross-asset portfolio backtesting (crypto + stocks + gold + DeFi).
  加密货币永续合约量化交易技能，四阶段工作流：信号定制→策略构建→交易执行→回测验证。用户用自然语言描述信号即可。
---

# DEX Quant Skill — Signal · Strategy · Trade · Backtest

## Architecture — 四阶段工作流

```
用户自然语言 (e.g. "RSI 低于 30 且放量时做多 BTC")
     ↓
┌─ Stage 1: 信号定制 ──────────────────────────┐
│  scripts/signal_builder.py                    │
│  · 指标计算 (MA/EMA/RSI/MACD/Bollinger/ATR)  │
│  · 条件组合 (above/below/cross/AND/OR/NOT)   │
│  · 信号输出 (entry_long/short, exit_long/short) │
└──────────────────────────────────────────────┘
     ↓
┌─ Stage 2: 策略生成 ──────────────────────────┐
│  SignalStrategy 组装                          │
│  · 配置杠杆 / 保证金模式 / 仓位大小         │
│  · 配置止损 / 止盈 / 滑点                    │
│  · 策略描述 → 用户确认                       │
└──────────────────────────────────────────────┘
     ↓
┌─ Stage 3: 交易执行 ──────────────────────────┐
│  scripts/data_client.py ← 实时/历史数据      │
│  scripts/backtest_engine.py ← 逐 bar 模拟    │
│  · 保证金 / 强制平仓 / 资金费率结算          │
└──────────────────────────────────────────────┘
     ↓
┌─ Stage 4: 回测验证 ──────────────────────────┐
│  绩效报告                                     │
│  · 收益率 / 夏普 / 最大回撤 / 胜率           │
│  · 资金费率损益 / 强平次数 / 手续费          │
│  · Agent 解读 → 优化建议 → 迭代信号          │
└──────────────────────────────────────────────┘
```

**无需 API Key**（全部使用交易所公开端点），国内访问可配置 `PROXY_URL` 环境变量。

---

## 四阶段流程详解

以用户说 **"当 RSI 低于 30 且资金费率为负时做多 BTC，5 倍杠杆，止损 3%，回测最近一年"** 为例：

### Stage 1 — 信号定制

1. Agent 解析自然语言，提取要素：指标(RSI)、阈值(30)、条件(资金费率<0)、方向(做多)
2. 选择指标：`indicators_config = {"rsi_period": 14}`
3. 组合条件：`Condition.below("rsi", 30) & Condition.below("funding_rate", 0)`
4. 生成信号：`Signal("RSI超卖+负费率→做多", SignalType.ENTRY_LONG, ...)`

信号定制指南见 [references/signal-guide.md](references/signal-guide.md)

### Stage 2 — 策略生成

5. 构建 `SignalStrategy`，配置杠杆=5、逐仓、仓位=20%、止损=3%
6. 调用 `strategy.describe()` 展示完整信号逻辑，让用户确认

### Stage 3 — 交易执行

7. `data_client.get_perp_klines("BTCUSDT", "1d", limit=365)` — 拉一年日线
8. `data_client.get_funding_rate("BTCUSDT", ...)` — 拉资金费率
9. 逐 bar 计算指标 → 评估信号 → 触发时调用 `engine.open_long()` / `close_long()`

### Stage 4 — 回测验证

10. `engine.get_metrics()` — 获取绩效指标
11. Agent 解读：收益率、夏普、最大回撤、资金费率损益、强平次数
12. 如果效果不好，建议用户调整信号参数 → 回到 Stage 1 迭代

更多场景见 [references/interaction-flows.md](references/interaction-flows.md)

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

## 信号层 — signal_builder.py

信号定制引擎，将自然语言转化为可组合的交易信号：

| 组件 | 说明 |
|------|------|
| `Indicators` | 技术指标库 — SMA / EMA / RSI / MACD / Bollinger / ATR / 成交量均线 |
| `Condition` | 条件组合 — `above()` / `below()` / `cross_above()` / `cross_below()` / `between()` / `&` / `\|` / `~` |
| `Signal` | 信号定义 — 类型(做多/做空/平多/平空) + 条件 + 杠杆 + 仓位 + 止损止盈 |
| `SignalStrategy` | 策略组装 — 指标配置 + 多个信号 + 上下文计算 + 信号评估 |

**预设信号组（快捷构建）:**

| 函数 | 适用场景 | 自然语言触发示例 |
|------|----------|----------------|
| `build_ma_cross_signals()` | 均线交叉趋势跟踪 | "双均线金叉做多死叉做空" |
| `build_rsi_signals()` | RSI 超买超卖反转 | "RSI 低于 30 做多" |
| `build_funding_rate_signals()` | 资金费率套利 | "费率高的时候做空" |
| `build_bollinger_signals()` | 布林带突破 | "跌破布林带下轨抄底" |
| `build_multi_factor_signals()` | 多因子组合 | "金叉 + RSI 没超买 + 费率不高" |

信号定制详细指南见 [references/signal-guide.md](references/signal-guide.md)

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

**核心原则：从信号开始，用户全程用自然语言。**

1. **理解意图** — 用户说一句话，Agent 提取：指标 + 条件 + 方向 + 风控参数
2. **生成信号** — 读取 [references/signal-guide.md](references/signal-guide.md)，用 `signal_builder.py` 组装信号
3. **展示确认** — 调 `strategy.describe()` 让用户看到完整信号逻辑，确认后继续
4. **执行回测** — 用 `data_client` 拉取数据 → `BacktestEngine` 逐 bar 执行
5. **解读报告** — 调 `engine.get_metrics()` 获取结果
6. **迭代优化** — 如果效果不理想，建议调整信号参数或组合更多条件

### Agent 如何编写策略代码

1. 读取 [references/signal-guide.md](references/signal-guide.md) + [references/strategy-sdk.md](references/strategy-sdk.md)
2. 判断用户是否描述了明确信号 → 用 `signal_builder.py` 快速构建
3. 如果是复杂自定义逻辑 → 用 `Condition(name, lambda)` 编写自定义条件
4. 选择模板（见下方），填充信号和参数
5. 用 `data_client` 拉取数据 → 喂入 `BacktestEngine` 逐 bar 执行

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
| `assets/templates/custom_signal_strategy.py` | **推荐** — 信号驱动策略（用户自然语言定义信号） |
| `assets/templates/perpetual_ma_cross.py` | 永续合约均线交叉（趋势跟踪） |
| `assets/templates/funding_rate_arb.py` | 资金费率套利（永续+现货对冲） |
| `assets/templates/cross_asset_portfolio.py` | 跨资产组合再平衡 |

---

## 参考文档

| 文档 | 内容 | 何时阅读 |
|------|------|----------|
| [references/signal-guide.md](references/signal-guide.md) | **自然语言→信号映射、指标配置、条件组合** | **收到用户信号描述时（首先阅读）** |
| [references/data-sources.md](references/data-sources.md) | 各 API 端点详细参数、限流、数据限制 | 拉数据时 |
| [references/backtest-engine.md](references/backtest-engine.md) | 保证金/杠杆/资金费率/强平计算公式 | 编写策略或分析结果时 |
| [references/data-models.md](references/data-models.md) | Symbol 命名、资产类型、支持的合约列表 | 构造请求时 |
| [references/strategy-sdk.md](references/strategy-sdk.md) | 引擎 API 函数 + 3 个完整策略示例 | 编写策略代码时 |
| [references/interaction-flows.md](references/interaction-flows.md) | 端到端交互场景与验收用例 | 理解完整流程时 |

---

## 仍需协调的数据（3 项）

以下数据没有免费公开 API，需要付费服务或自建采集：

| # | 数据 | 问题 | 推荐方案 |
|---|------|------|----------|
| 1 | **聚合爆仓数据** | Binance 没有聚合爆仓统计端点 | Coinglass API（付费 ~$50/月） |
| 2 | **持仓量/多空比 >30 天历史** | Binance 仅保留最近 30 天 | 自建 cron 定时采集 + 存数据库，或 Coinglass |
| 3 | **DeFi 收益率 APY 历史** | DeFi Llama yields 端点需 Pro Key | 申请 DeFi Llama Pro，或自建链上采集 |
