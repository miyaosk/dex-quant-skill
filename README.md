# DEX Quant Skill

**加密货币永续合约量化交易 Skill** — 用户用自然语言描述策略意图，AI Agent 自动写策略、产出信号、跑回测、优化参数。

> "帮我做一个 MACD 策略做 BTC，5 倍杠杆"
>
> → Agent 追问细节 → 写策略 → 策略产出交易信号 → 信号驱动回测 → 输出结果 → 遗传寻优找最优参数

## 核心理念

**信号是策略产生的。** 策略定义了什么时候买什么时候卖的规则。策略在历史数据上运行，产出具体的交易信号（币种 + 入场时间 + 入场价格 + 方向 + 止盈止损）。回测引擎基于策略产出的信号执行交易。

用户不需要写代码。用户描述策略意图 → Agent 追问入场条件、盈亏比、杠杆 → Agent 写策略 → 跑回测 → 看结果 → 调参数或自动寻优。

---

## 设计架构

```
┌──────────────────────────────────────────────────────────┐
│                    用户（自然语言）                         │
│          "帮我做一个 MACD 策略做 BTC，5 倍杠杆"             │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌─ Stage 1: Agent 写策略 ──────────────────────────────────┐
│  signal_builder.py                                       │
│  ├── Agent 追问: 入场条件？出场条件？盈亏比？杠杆？          │
│  ├── Indicators: SMA / EMA / RSI / MACD / Bollinger / ATR│
│  ├── Condition: above / below / cross / AND / OR / NOT   │
│  ├── StrategyRule: 条件满足 → 开多/开空/平多/平空           │
│  └── Strategy: 多规则组装 → strategy.describe() → 用户确认 │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌─ Stage 2: 策略产出信号 ──────────────────────────────────┐
│  策略在历史数据上逐 bar 运行                                │
│  ├── 规则满足 → 产出 TradeSignal                           │
│  │   · signal_id / datetime / symbol / side / action      │
│  │   · price / stop_loss / take_profit / reason           │
│  └── SignalLog 存储所有信号 → 导出 JSON / CSV / DataFrame  │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌─ Stage 3: 信号驱动回测 ──────────────────────────────────┐
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
┌─ Stage 4: 结果 + 优化 ──────────────────────────────────┐
│  📈 绩效报告 + 信号列表                                    │
│  ├── 收益率 / 夏普 / 最大回撤 / 胜率 / 盈亏比              │
│  ├── 资金费率损益 / 强平次数 / 手续费                       │
│  ├── 信号表格: 每笔交易的时间/价格/方向/止盈止损/盈亏       │
│  │                                                       │
│  🧬 遗传寻优 (optimizer.py)                               │
│  ├── 定义参数空间 → 50 个体 × 30 代进化                    │
│  ├── 适应度 = 跑回测取夏普比率                              │
│  └── 输出最优参数 + Top N 参数组 + 收敛曲线                 │
└──────────────────────────────────────────────────────────┘
```

**核心设计决策：**

- **策略是 Agent 写的** — 用户只需描述意图，Agent 追问细节后自动组装策略
- **信号是策略的输出** — 每笔交易都有具体的币种、时间、价格、方向、止盈止损和触发原因
- **遗传寻优** — 不知道最优参数？自动搜索（50 个体 × 30 代，锦标赛选择 + 交叉变异）
- **全部使用公开 API，无需任何 API Key** — 零配置即可使用
- **本地回测引擎** — 不依赖第三方，数据安全，可离线运行

---

## 功能全览

### 策略引擎

| 能力 | 说明 |
|------|------|
| **预设策略** | MACD / 均线交叉 / RSI / 布林带 / 资金费率套利，一行代码调用 |
| **自由组合** | `Condition.cross_above() & Condition.below()` 像搭积木一样组合条件 |
| **自定义逻辑** | `Condition(name, lambda ctx: ...)` 支持任意 Python 表达式 |
| **信号产出** | 策略运行自动产出 TradeSignal，包含完整交易细节 |
| **信号存储** | 导出 JSON / CSV / DataFrame，终端表格展示 |

### 遗传寻优

| 能力 | 说明 |
|------|------|
| **参数空间** | 支持整数 / 浮点 / 枚举类型 |
| **遗传算法** | 锦标赛选择 + 均匀交叉 + 变异，精英保留 |
| **提前终止** | 连续 N 代无提升自动停止 |
| **网格搜索** | 小参数空间穷举备选 |
| **结果输出** | 最优参数 + Top N 排名 + 收敛历史 |

### 数据获取（5 个数据源，20 个方法）

| 数据源 | 覆盖资产 | API Key | 历史深度 |
|--------|---------|---------|---------|
| **Binance Futures** | 永续合约 K线、资金费率、持仓量、多空比、合约信息 | 不需要 | K线/费率：无限；持仓量/多空比：30 天 |
| **Binance Spot** | 加密货币现货 K线 | 不需要 | 无限 |
| **CoinGecko** | PAXG、XAUT、OUSG 等代币价格 | 不需要 | 365 天（免费版） |
| **Yahoo Finance** | 美股（AAPL/SPY/QQQ）、大宗商品（原油/天然气/铜）、贵金属（黄金/白银） | 不需要 | 10-30 年 |
| **DeFi Llama** | 协议 TVL 历史、手续费收入 | 不需要 | 协议上线以来 |

### 回测引擎

| 能力 | 说明 |
|------|------|
| **多空双向持仓** | 做多 / 做空 / 反手 / 加仓 / 减仓 |
| **杠杆** | 1x 到 125x |
| **保证金模式** | 逐仓（爆仓隔离）和全仓（共享保证金） |
| **资金费率结算** | 每 8 小时，使用真实历史数据 |
| **强制平仓** | 保证金率 <= 维持保证金率时触发 |
| **止损 / 止盈** | 标记价格触及时自动平仓 |
| **滑点 + 手续费** | 固定 bps 滑点 + Maker 0.02% / Taker 0.05% |

---

## 快速开始

### 安装

```bash
git clone https://github.com/miyaosk/dex-quant-skill.git
cd dex-quant-skill
pip install -r requirements.txt
```

### 方式一：策略回测（推荐入口）

```bash
# MACD 策略回测 — 产出信号 + 绩效报告
python assets/templates/custom_signal_strategy.py
```

### 方式二：遗传寻优

```bash
# 自动搜索均线策略最优参数
python assets/templates/optimize_strategy.py
```

### 方式三：Python 代码

```python
from scripts.signal_builder import build_macd_strategy

# 用户说: "做一个 MACD 策略，BTC，5x 杠杆，止损 5%"
strategy = build_macd_strategy(
    symbol="BTC-USDT-PERP",
    leverage=5,
    stop_loss_pct=0.05,
    take_profit_pct=0.15,
)

# 查看策略规则
print(strategy.describe())

# ... 拉数据 → 逐 bar 运行 → 产出信号 → 驱动回测 ...

# 查看策略产出的信号
strategy.signal_log.print_table()
strategy.signal_log.to_json("signals.json")
print(strategy.signal_log.summary())
```

### 方式四：遗传寻优 API

```python
from scripts.optimizer import GeneticOptimizer, ParameterSpace

space = ParameterSpace()
space.add_int("fast_period", 5, 30)
space.add_int("slow_period", 20, 120)
space.add_float("stop_loss_pct", 0.02, 0.15)
space.add_int("leverage", 1, 10)

optimizer = GeneticOptimizer(space, fitness_fn=my_backtest, population_size=50, generations=30)
result = optimizer.run()
print(result.summary())    # 最优参数 + Top 5 + 收敛历史
```

### 方式五：作为 AI Agent Skill 使用

```bash
# Codex
git clone https://github.com/miyaosk/dex-quant-skill ~/.codex/skills/dex-quant-skill

# Claude Code
git clone https://github.com/miyaosk/dex-quant-skill ~/.claude/skills/dex-quant-skill

# SkillHub
npx skillhub install miyaosk/dex-quant-skill
```

安装后对 Agent 说自然语言：
- "帮我做一个 MACD 策略做 BTC，5 倍杠杆，跑过去一年"
- "RSI 低于 30 做多 ETH，止损 5%，盈亏比 1:3"
- "帮我找到均线策略的最优参数"
- "资金费率高的时候做空 BTC"

---

## 信号格式

策略产出的每个 TradeSignal：

| 字段 | 说明 |
|------|------|
| `signal_id` | 唯一标识 |
| `datetime` | 入场/出场时间 |
| `symbol` | 币种（如 BTC-USDT-PERP） |
| `side` | long / short |
| `action` | open / close |
| `price` | 入场/出场价格 |
| `stop_loss` | 止损价格 |
| `take_profit` | 止盈价格 |
| `reason` | 触发原因（如 "macd cross above macd_signal"） |

**信号表格示例：**

```
时间              | 币种             | 方向        | 价格         | 止损       止盈       | 盈亏       | 触发原因
2025-03-15 00:00 | BTC-USDT-PERP    | long  open  | $84,250.00   | $80,037    $96,887    | -          | macd cross above macd_signal
2025-04-02 00:00 | BTC-USDT-PERP    | long  close | $87,100.00   | -          -          | +2,850.00  | macd cross below macd_signal
```

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
├── SKILL.md                         # AI Agent 入口文件
├── clawhub.json                     # Skill 市场元数据
├── requirements.txt                 # Python 依赖
│
├── scripts/
│   ├── signal_builder.py            # 策略引擎（指标 + 条件 + 规则 + 信号产出 + 存储）
│   ├── optimizer.py                 # 遗传寻优 + 网格搜索
│   ├── data_client.py               # 多源数据客户端（5 个 API，20 个方法）
│   └── backtest_engine.py           # 本地回测引擎（保证金/强平/资金费率）
│
├── assets/templates/
│   ├── custom_signal_strategy.py    # 策略模板：策略产出信号 + 回测（推荐入口）
│   ├── optimize_strategy.py         # 策略模板：遗传寻优找最优参数
│   ├── perpetual_ma_cross.py        # 策略模板：均线交叉
│   ├── funding_rate_arb.py          # 策略模板：资金费率套利
│   └── cross_asset_portfolio.py     # 策略模板：跨资产组合
│
└── references/
    ├── signal-guide.md              # 策略与信号指南（写法 + 条件映射 + 寻优）
    ├── data-sources.md              # 各 API 端点详细文档 + 限流说明
    ├── backtest-engine.md           # 保证金/强平/资金费率计算公式
    ├── data-models.md               # Symbol 命名规范 + 合约列表
    ├── strategy-sdk.md              # 引擎 API 函数 + 完整策略示例
    └── interaction-flows.md         # 7 个端到端交互场景
```

---

## 保证金与强平计算

```
初始保证金     = 仓位价值 / 杠杆
维持保证金     = 仓位价值 × 维持保证金率
强平价格（多） = 开仓均价 × (1 - 1/杠杆 + 维持保证金率)
强平价格（空） = 开仓均价 × (1 + 1/杠杆 - 维持保证金率)
资金费用       = 仓位价值 × 资金费率（每 8h 结算一次）
```

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
