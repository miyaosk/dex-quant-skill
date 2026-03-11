# DEX Quant Skill

**加密货币永续合约量化回测 Skill** — 让 AI Agent 用自然语言完成端到端的策略研究、回测与分析。

> "帮我回测一个 BTC 永续合约均线策略，5 倍杠杆，过去一年"
>
> → Agent 自动拉数据 → 编写策略 → 执行回测 → 输出分析报告

## 为什么做这个

加密货币永续合约占市场总交易量的 60%-70%，是量化交易者的主战场。但现有的回测工具要么不支持永续合约特有机制（资金费率、保证金、强平），要么需要复杂的配置和编码。

我们的设计理念：**用户说一句话，AI 替你完成整个回测流程。**

这个 Skill 让 AI Agent（Claude / Codex / Cursor / Copilot 等）具备专业的加密货币量化研究能力，包括：拉取真实行情数据、生成交易信号、构建策略代码、执行回测、分析结果。

---

## 设计架构

```
┌──────────────────────────────────────────────────────────┐
│                    用户（自然语言）                         │
│         "BTC 永续 5 倍杠杆 资金费率套利 回溯半年"           │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│                    AI Agent                               │
│                                                          │
│   1. 读 SKILL.md     → 知道自己有什么能力                  │
│   2. 读 references/  → 学会怎么调 API、怎么写策略           │
│   3. 用 templates/   → 有现成的策略模板可以改               │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│                   两层核心引擎                             │
│                                                          │
│   📊 数据层 (data_client.py)                              │
│   ├── Binance Futures API  → 永续合约 K线/资金费率/持仓量   │
│   ├── Binance Spot API     → 现货 K线                     │
│   ├── CoinGecko API        → PAXG/XAUT 等代币价格         │
│   ├── Yahoo Finance        → 美股/大宗商品/贵金属           │
│   └── DeFi Llama API       → 协议 TVL/手续费               │
│                                                          │
│   ⚙️ 回测层 (backtest_engine.py)                          │
│   ├── 保证金计算（逐仓 + 全仓）                             │
│   ├── 杠杆支持（1x - 125x）                                │
│   ├── 资金费率结算（每 8h，使用真实历史数据）                 │
│   ├── 强制平仓模拟                                         │
│   ├── 止损 / 止盈                                          │
│   └── 手续费 + 滑点模型                                    │
└──────────────────────────────────────────────────────────┘
                         ▼
              📈 回测报告 → 返回用户
```

**核心设计决策：**

- **全部使用公开 API，无需任何 API Key** — 零配置即可使用
- **本地回测引擎** — 不依赖第三方回测服务，数据安全，可离线运行
- **三层渐进式加载** — Agent 只在需要时读取对应的参考文档，节省上下文窗口

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

### 策略模板（开箱即用）

| 模板 | 策略类型 | 说明 |
|------|---------|------|
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

### 方式一：直接运行策略模板

```bash
# BTC 均线策略回测
python assets/templates/perpetual_ma_cross.py

# 资金费率套利回测
python assets/templates/funding_rate_arb.py

# 跨资产组合回测
python assets/templates/cross_asset_portfolio.py
```

### 方式二：Python 代码调用

```python
from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine, BacktestConfig

# 拉数据
client = DataClient()
klines = client.get_perp_klines("BTC-USDT-PERP", "1d", "2024-01-01", "2025-12-31")
funding = client.get_funding_rate("BTC-USDT-PERP", "2024-01-01", "2025-12-31")

# 跑回测
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
│   ├── data_client.py               # 多源数据客户端（5 个 API，20 个方法）
│   └── backtest_engine.py           # 本地回测引擎（保证金/强平/资金费率）
│
├── assets/templates/
│   ├── perpetual_ma_cross.py        # 策略模板：均线交叉
│   ├── funding_rate_arb.py          # 策略模板：资金费率套利
│   └── cross_asset_portfolio.py     # 策略模板：跨资产组合
│
└── references/
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
