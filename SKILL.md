---
name: dex-quant-skill
description: >
  Crypto perpetual futures quantitative backtesting skill. Fetches real market data from Binance/CoinGecko/Yahoo Finance APIs (no API key needed),
  runs local backtest engine with margin, leverage, funding rate settlement, and liquidation simulation.
  Use when user asks to: (1) backtest crypto trading strategies (e.g. "backtest BTC perpetual MA crossover with 5x leverage");
  (2) fetch crypto market data, funding rates, open interest; (3) build quantitative strategies with margin/leverage/stop-loss;
  (4) run funding rate arbitrage or long-short hedging strategies; (5) cross-asset portfolio backtesting (crypto + stocks + gold);
  (6) analyze DeFi protocol TVL or fees; (7) any crypto perpetual futures research or quantitative analysis task.
  加密货币永续合约量化回测，支持信号生成、策略构建、回测执行与分析。
---

# DEX Quant Skill — Signals · Strategy · Backtest

## Architecture

```
User (natural language / 自然语言)
     ↓
AI Agent (loads this Skill)
     ↓
┌─────────────────────────────────┐
│  scripts/data_client.py        │ ← Data: Binance / CoinGecko / yfinance / DeFi Llama
│  scripts/backtest_engine.py    │ ← Engine: margin / leverage / funding rate / liquidation
└─────────────────────────────────┘
     ↓
Analysis report → User
```

**无需 API Key**（全部使用交易所公开端点），国内访问可配置 `PROXY_URL` 环境变量。

---

## 端到端流程

以"BTC 永续 5 倍杠杆资金费率套利 回溯半年"为例：

1. `data_client.get_exchange_info("BTC-USDT-PERP")` — 查合约规格
2. `data_client.get_perp_klines("BTC-USDT-PERP", "1d", ...)` — 拉半年日线
3. `data_client.get_funding_rate("BTC-USDT-PERP", ...)` — 拉半年资金费率
4. Agent 分析数据，编写策略代码
5. 构建 `BacktestEngine`，逐 bar 执行策略
6. `engine.get_result()` — 获取绩效指标 + 净值曲线 + 交易日志
7. Agent 解读报告，返回用户

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

### Agent 如何编写策略

1. 读取 [references/strategy-sdk.md](references/strategy-sdk.md)
2. 选择模板（见下方），修改信号逻辑和参数
3. 用 `data_client` 拉取数据 → 喂入 `BacktestEngine` 逐 bar 执行
4. 调 `engine.get_result()` 获取结果

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
| `assets/templates/perpetual_ma_cross.py` | 永续合约均线交叉（趋势跟踪） |
| `assets/templates/funding_rate_arb.py` | 资金费率套利（永续+现货对冲） |
| `assets/templates/cross_asset_portfolio.py` | 跨资产组合再平衡 |

---

## 参考文档

| 文档 | 内容 | 何时阅读 |
|------|------|----------|
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
