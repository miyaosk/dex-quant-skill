# DEX Quant Skill

**加密货币永续合约量化交易 Skill** — 用户用自然语言定制信号，AI Agent 自动完成从信号到回测的全链路。

> "当 RSI 低于 30 且资金费率为负时做多 BTC，5 倍杠杆，止损 3%"
>
> → Agent 定制信号 → 生成策略 → 执行交易 → 回测验证 → 输出分析报告

## 为什么做这个

加密货币永续合约占市场总交易量的 60%-70%，是量化交易者的主战场。但现有的回测工具要么不支持永续合约特有机制（资金费率、保证金、强平），要么需要复杂的编码。

我们的设计理念：**用户从定制信号开始，全程用自然语言，AI 完成四阶段闭环。**

这个 Skill 让 AI Agent（Claude / Codex / Cursor / Copilot 等）具备专业的加密货币量化研究能力，包括：定制交易信号、生成策略代码、拉取真实行情数据、执行回测、分析结果、迭代优化。

---

## 设计架构 — 四阶段工作流

```
┌──────────────────────────────────────────────────────────┐
│                    用户（自然语言）                         │
│      "RSI 低于 30 且放量时做多 BTC，5 倍杠杆，止损 3%"      │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌─ Stage 1: 信号定制 ──────────────────────────────────────┐
│  signal_builder.py                                       │
│  ├── 指标计算 → SMA / EMA / RSI / MACD / Bollinger / ATR │
│  ├── 条件组合 → above / below / cross / AND / OR / NOT   │
│  └── 信号输出 → 做多 / 做空 / 平多 / 平空                  │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌─ Stage 2: 策略生成 ──────────────────────────────────────┐
│  SignalStrategy 组装                                     │
│  ├── 配置杠杆 / 保证金模式 / 仓位大小                     │
│  ├── 配置止损 / 止盈 / 滑点                               │
│  └── strategy.describe() → 展示给用户确认                  │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌─ Stage 3: 交易执行 ──────────────────────────────────────┐
│  📊 data_client.py ← 实时/历史数据                        │
│  ├── Binance Futures API  → K线/资金费率/持仓量            │
│  ├── Binance Spot API     → 现货 K线                      │
│  ├── CoinGecko API        → 代币价格                      │
│  ├── Yahoo Finance        → 美股/大宗商品/贵金属            │
│  └── DeFi Llama API       → 协议 TVL/手续费                │
│                                                           │
│  ⚙️ backtest_engine.py ← 逐 bar 模拟交易                  │
│  ├── 保证金计算（逐仓 + 全仓）                              │
│  ├── 杠杆支持（1x - 125x）                                 │
│  ├── 资金费率结算（每 8h，真实历史数据）                     │
│  ├── 强制平仓模拟                                          │
│  └── 止损 / 止盈 / 手续费 / 滑点                           │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌─ Stage 4: 回测验证 ──────────────────────────────────────┐
│  📈 绩效报告                                              │
│  ├── 收益率 / 夏普 / 最大回撤 / 胜率 / 盈亏比              │
│  ├── 资金费率损益 / 强平次数 / 手续费                       │
│  └── Agent 解读 → 优化建议 → 回到 Stage 1 迭代             │
└──────────────────────────────────────────────────────────┘
```

**核心设计决策：**

- **信号优先** — 用户从定制信号开始，不需要直接写代码，全程用自然语言
- **可组合条件** — `Condition.below("rsi", 30) & Condition.above("volume_ratio", 1.5)` 像搭积木一样组合信号
- **全部使用公开 API，无需任何 API Key** — 零配置即可使用
- **本地回测引擎** — 不依赖第三方回测服务，数据安全，可离线运行
- **闭环迭代** — 回测结果不好？调整信号参数，重新跑，Agent 辅助优化

---

## 功能全览

### 数据获取（5 个数据源，20 个方法）

| 数据源 | 覆盖资产 | API Key | 历史深度 |
|--------|---------|---------|---------|
| **Binance Futures** | 永续合约 K线、资金费率、持仓量、多空比、合约信息 | 不需要 | K线/费率：无限；持仓量/多空比：30 天 |
| **Binance Spot** | 加密货币现货 K线 | 不需要 | 无限 |
| **CoinGecko** | PAXG、XAUT、OUSG 等代币价格 | 不需要 | 365 天（免费版） |
| **Yahoo Finance** | 美股（AAPL/SPY/QQQ）、大宗商品（原油/天然气/铜）、贵金属（黄金/白银） | 不需要 | 10-30 年 |
| **DeFi Llama** | 协议 TVL 历史、手续费收入 | 不需要 | 协议上线以来 |

### 回测引擎

永续合约回测与现货有本质区别，我们的引擎完整实现了以下机制：

| 能力 | 说明 |
|------|------|
| **多空双向持仓** | 做多 / 做空 / 反手 / 加仓 / 减仓 |
| **杠杆** | 1x 到 125x，支持运行中调整 |
| **保证金模式** | 逐仓（仓位独立，爆仓隔离）和全仓（共享保证金） |
| **资金费率结算** | 每 8 小时一次（00:00/08:00/16:00 UTC），使用真实历史数据 |
| **强制平仓** | 保证金率 <= 维持保证金率时自动触发，逐仓/全仓逻辑分别处理 |
| **止损 / 止盈** | 标记价格触及时自动市价平仓 |
| **滑点模型** | 固定 bps（BTC/ETH 默认 2bps，其他主流 5bps） |
| **手续费** | Maker 0.02% / Taker 0.05%，可自定义 |

### 信号定制引擎（核心新特性）

| 组件 | 说明 |
|------|------|
| **指标库** | SMA / EMA / RSI / MACD / Bollinger Bands / ATR / 成交量均线 |
| **条件系统** | `above()` / `below()` / `cross_above()` / `cross_below()` / `between()` + AND/OR/NOT 组合 |
| **预设信号组** | 均线交叉 / RSI 超买超卖 / 资金费率套利 / 布林带突破 / 多因子组合 |

**自然语言示例：**

| 用户说 | Agent 生成 |
|--------|-----------|
| "RSI 低于 30 做多" | `Condition.below("rsi", 30)` → `Signal(ENTRY_LONG)` |
| "快速均线上穿慢速均线" | `Condition.cross_above("fast_ma", "slow_ma")` |
| "资金费率 > 0.05% 且 RSI > 70" | `Condition.above("funding_rate", 0.0005) & Condition.above("rsi", 70)` |
| "价格跌破布林带下轨时抄底" | `Condition("close < bb_lower", ...)` → `Signal(ENTRY_LONG)` |

### 策略模板（开箱即用）

| 模板 | 策略类型 | 说明 |
|------|---------|------|
| `custom_signal_strategy.py` | **信号驱动** | 用户自然语言定义信号（推荐入口） |
| `perpetual_ma_cross.py` | 趋势跟踪 | 双均线交叉，自动开多/开空，含止损止盈 |
| `funding_rate_arb.py` | 套利 | 资金费率高于阈值时做空永续收取费率，低于阈值平仓 |
| `cross_asset_portfolio.py` | 组合配置 | BTC + ETH + 黄金（PAXG）按权重分配，定期再平衡 |

### 回测报告输出

每次回测产出四个维度的完整报告：

1. **绩效指标** — 总收益率、年化收益、夏普比率、索提诺比率、最大回撤、卡尔玛比率、胜率、盈亏比
2. **资金费率损益** — 累计支付、累计收到、净损益（套利策略核心指标）
3. **净值曲线 + 回撤曲线** — 逐 bar 记录
4. **交易日志** — 每笔开仓/平仓/强平的完整明细（价格、杠杆、保证金、手续费、滑点、盈亏）

---

## 快速开始

### 安装

```bash
git clone https://github.com/miyaosk/dex-quant-skill.git
cd dex-quant-skill
pip install -r requirements.txt
```

### 方式一：信号驱动策略（推荐）

```python
from scripts.signal_builder import (
    SignalStrategy, Signal, SignalType, Condition,
    build_rsi_signals,
)

# 用自然语言思维定义信号
strategy = SignalStrategy(name="BTC RSI策略", symbol="BTC-USDT-PERP")
config, signals = build_rsi_signals(period=14, overbought=70, oversold=30, leverage=5)
strategy.indicators_config = config
for sig in signals:
    strategy.add_signal(sig)

print(strategy.describe())  # 查看信号逻辑
```

```bash
# 或直接运行模板
python assets/templates/custom_signal_strategy.py
```

### 方式二：直接运行其他策略模板

```bash
python assets/templates/perpetual_ma_cross.py      # 均线交叉
python assets/templates/funding_rate_arb.py         # 资金费率套利
python assets/templates/cross_asset_portfolio.py    # 跨资产组合
```

### 方式三：Python 代码调用

```python
from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine, BacktestConfig

client = DataClient()
klines = client.get_perp_klines("BTC-USDT-PERP", "1d", "2024-01-01", "2025-12-31")
funding = client.get_funding_rate("BTC-USDT-PERP", "2024-01-01", "2025-12-31")

engine = BacktestEngine(BacktestConfig(
    initial_capital=100_000,
    default_leverage=5,
    margin_mode="isolated",
    enable_funding=True,
))

# 逐 bar 执行策略逻辑...
result = engine.get_result()
print(engine.format_summary(result))
```

### 方式三：作为 AI Agent Skill 使用

```bash
# Codex
git clone https://github.com/miyaosk/dex-quant-skill ~/.codex/skills/dex-quant-skill

# Claude Code
git clone https://github.com/miyaosk/dex-quant-skill ~/.claude/skills/dex-quant-skill

# SkillHub
npx skillhub install miyaosk/dex-quant-skill
```

安装后对 Agent 说自然语言即可，Agent 会自动调用 Skill 中的代码和参考文档。

---

## 支持的资产

### 加密货币永续合约（Top 30）

| 分类 | 合约 |
|------|------|
| 主流币 | BTC-USDT-PERP, ETH-USDT-PERP, SOL-USDT-PERP, BNB-USDT-PERP, XRP-USDT-PERP |
| Layer1 | ADA-USDT-PERP, AVAX-USDT-PERP, DOT-USDT-PERP, ATOM-USDT-PERP, SUI-USDT-PERP |
| Layer2 | ARB-USDT-PERP, OP-USDT-PERP, MATIC-USDT-PERP |
| DeFi | UNI-USDT-PERP, AAVE-USDT-PERP, LINK-USDT-PERP, MKR-USDT-PERP |
| Meme | DOGE-USDT-PERP, SHIB-USDT-PERP, PEPE-USDT-PERP, WIF-USDT-PERP |
| AI 概念 | FET-USDT-PERP, RENDER-USDT-PERP, TAO-USDT-PERP |
| 其他 | LTC-USDT-PERP, ETC-USDT-PERP, FIL-USDT-PERP, APT-USDT-PERP, INJ-USDT-PERP, TIA-USDT-PERP |

### 其他资产

| 类型 | Symbol 示例 | 数据源 |
|------|------------|--------|
| 加密现货 | BTC-USDT-SPOT | Binance |
| 贵金属代币 | PAXG, XAUT | CoinGecko |
| 贵金属现货 | METAL:XAU-SPOT, METAL:XAG-SPOT | Yahoo Finance |
| 美股 / ETF | RWA:AAPL, RWA:SPY, RWA:QQQ | Yahoo Finance |
| 大宗商品 | COMM:WTI, COMM:NG, COMM:COPPER | Yahoo Finance |
| DeFi 协议 | aave, compound, lido, curve | DeFi Llama |

---

## 项目结构

```
dex-quant-skill/
├── SKILL.md                         # AI Agent 入口文件（自动被 Agent 识别）
├── clawhub.json                     # Skill 市场元数据
├── requirements.txt                 # Python 依赖
│
├── scripts/
│   ├── signal_builder.py            # 信号定制引擎（指标 + 条件 + 信号 + 策略组装）
│   ├── data_client.py               # 多源数据客户端（5 个 API，20 个方法）
│   └── backtest_engine.py           # 本地回测引擎（保证金/强平/资金费率）
│
├── assets/templates/
│   ├── custom_signal_strategy.py    # 策略模板：自定义信号驱动（推荐入口）
│   ├── perpetual_ma_cross.py        # 策略模板：均线交叉
│   ├── funding_rate_arb.py          # 策略模板：资金费率套利
│   └── cross_asset_portfolio.py     # 策略模板：跨资产组合
│
└── references/
    ├── signal-guide.md              # 信号定制指南（自然语言→信号映射）
    ├── data-sources.md              # 各 API 端点详细文档 + 限流说明
    ├── backtest-engine.md           # 保证金/强平/资金费率计算公式
    ├── data-models.md               # Symbol 命名规范 + 合约列表
    ├── strategy-sdk.md              # 引擎 API 函数 + 完整策略示例
    └── interaction-flows.md         # 7 个端到端交互场景
```

---

## 保证金与强平计算

永续合约回测的核心，完整实现了交易所级别的计算逻辑：

```
初始保证金     = 仓位价值 / 杠杆
维持保证金     = 仓位价值 × 维持保证金率
强平价格（多） = 开仓均价 × (1 - 1/杠杆 + 维持保证金率)
强平价格（空） = 开仓均价 × (1 + 1/杠杆 - 维持保证金率)
资金费用       = 仓位价值 × 资金费率（每 8h 结算一次）
```

**数值示例：** BTC 多单，开仓价 $60,000，5x 杠杆

- 初始保证金 = $60,000 / 5 = **$12,000**
- 强平价格 = $60,000 × (1 - 0.2 + 0.005) = **$48,300**
- BTC 跌到 $48,300（跌幅 19.5%）触发强平

---

## 技术栈

| 组件 | 技术 |
|------|------|
| HTTP 客户端 | httpx（异步友好，支持代理） |
| 数据处理 | pandas + numpy |
| 美股/商品 | yfinance |
| 日志 | loguru |
| 最低 Python 版本 | 3.10+ |

---

## 已知限制

| 数据 | 限制 | 替代方案 |
|------|------|----------|
| 持仓量/多空比历史 | Binance 仅 30 天 | 自建定时采集或 Coinglass（付费） |
| 聚合爆仓数据 | Binance 无此端点 | Coinglass（付费 ~$50/月） |
| DeFi APY 历史 | DeFi Llama 需 Pro Key | 申请 Pro 或自建链上采集 |

---

## License

MIT
