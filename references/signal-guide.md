# 策略与信号指南

**核心原则（Eric 定义）：信号是策略产生的。**

策略定义了"什么时候买什么时候卖"的规则。策略在历史数据上运行，产出具体的交易信号。
信号 = 具体的币种 + 入场时间 + 入场价格 + 方向 + 止盈止损。
回测引擎基于策略产出的信号去执行交易。

---

## 完整流程

```
用户自然语言 (e.g. "帮我做一个 MACD 策略")
     │
     ▼
Agent 追问细节：入场条件？盈亏比？杠杆？仓位？
     │
     ▼
Agent 写策略（Strategy + StrategyRule）
     │
     ▼
策略在历史数据上逐 bar 运行
     │
     ▼
策略产出信号（TradeSignal: 币种/时间/价格/方向/止盈止损）
     │
     ▼
信号驱动回测引擎执行交易
     │
     ▼
输出回测结果 + 信号列表
     │
     ├─→ 用户满意 → 策略稳定跑起来
     └─→ 用户不满意 → 调参数 / 用遗传寻优自动找最优参数
```

---

## Agent 必须追问的信息

当用户说 "帮我做一个 XXX 策略" 时，Agent 需要确认：

| 信息 | 示例 | 默认值 |
|------|------|--------|
| **标的** | BTC-USDT-PERP | 必填 |
| **入场条件** | MACD 金叉 / RSI < 30 / 布林带突破 | 必填 |
| **出场条件** | MACD 死叉 / RSI > 50 / 价格回归中轨 | 必填（或用止盈止损） |
| **杠杆** | 5x | 3x |
| **仓位比例** | 每次投入总资金的 20% | 20% |
| **止损** | 价格回撤 5% 平仓 | 5% |
| **止盈** | 价格上涨 15% 平仓 | 15% |
| **盈亏比** | 至少 1:3 | 如果用户指定了盈亏比，Agent 反算止盈=止损×盈亏比 |
| **回测区间** | 最近一年 | 365 天 |
| **数据频率** | 日线 / 4h / 1h | 1d |

如果用户没指定，用默认值直接跑，回测结果出来后再问是否调整。

---

## 策略写法

### 方式 1：预设策略（一行调用）

```python
from scripts.signal_builder import (
    build_macd_strategy,        # MACD 策略
    build_ma_cross_strategy,    # 均线交叉
    build_rsi_strategy,         # RSI 超买超卖
    build_funding_rate_strategy,# 资金费率套利
    build_bollinger_strategy,   # 布林带突破
)

# 用户说: "做一个 MACD 策略，BTC，5x 杠杆，止损 5%"
strategy = build_macd_strategy(
    symbol="BTC-USDT-PERP",
    fast=12, slow=26, signal=9,
    leverage=5,
    stop_loss_pct=0.05,
    take_profit_pct=0.15,
)
```

### 方式 2：自由组合规则

```python
from scripts.signal_builder import Strategy, StrategyRule, RuleAction, Condition

strategy = Strategy(
    name="MACD+RSI 复合策略",
    symbol="ETH-USDT-PERP",
    indicators_config={
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "rsi_period": 14,
    },
)

# 入场：MACD 金叉 且 RSI < 65
strategy.add_rule(StrategyRule(
    "MACD金叉+RSI未超买→做多",
    RuleAction.OPEN_LONG,
    Condition.cross_above("macd", "macd_signal") & Condition.below("rsi", 65),
    leverage=5, position_size=0.2,
    stop_loss_pct=0.05, take_profit_pct=0.15,
))

# 出场：MACD 死叉
strategy.add_rule(StrategyRule(
    "MACD死叉→平多",
    RuleAction.CLOSE_LONG,
    Condition.cross_below("macd", "macd_signal"),
))
```

### 方式 3：完全自定义条件

```python
# 用户有特殊逻辑？用 lambda 写任意 Python 条件
strategy.add_rule(StrategyRule(
    "价格突然拉升 3%→做空",
    RuleAction.OPEN_SHORT,
    Condition("5min涨幅>3%",
              lambda ctx: (ctx["close"] - ctx.get("prev_close", ctx["close"]))
                          / ctx.get("prev_close", ctx["close"]) > 0.03),
    leverage=3, stop_loss_pct=0.02,
))
```

---

## 信号格式

策略运行后产出的每个 TradeSignal 包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `signal_id` | string | 唯一标识 |
| `datetime` | string | 入场/出场时间 |
| `symbol` | string | 币种，如 BTC-USDT-PERP |
| `side` | string | "long" 或 "short" |
| `action` | string | "open"（开仓）或 "close"（平仓） |
| `price` | float | 入场/出场价格 |
| `quantity` | float | 仓位比例 |
| `leverage` | int | 杠杆倍数 |
| `stop_loss` | float | 止损价格 |
| `take_profit` | float | 止盈价格 |
| `reason` | string | 触发原因，如 "macd cross above macd_signal" |
| `pnl` | float | 平仓时的已实现盈亏 |

### 信号展示（终端表格）

```
══════════════════════════════════════════════════════════════════════════
时间                | 币种             | 方向        | 价格         | 止损       止盈       | 盈亏       | 触发原因
──────────────────────────────────────────────────────────────────────────
2025-03-15 00:00 | BTC-USDT-PERP    | long  open  | $84,250.00   | SL:$80,037 TP:$96,887 | -          | macd cross above macd_signal
2025-04-02 00:00 | BTC-USDT-PERP    | long  close | $87,100.00   | -          -          | +2,850.00  | macd cross below macd_signal
══════════════════════════════════════════════════════════════════════════
```

### 信号导出

```python
# JSON
strategy.signal_log.to_json("signals.json")

# CSV
strategy.signal_log.to_csv("signals.csv")

# DataFrame
df = strategy.signal_log.to_dataframe()

# 统计摘要
print(strategy.signal_log.summary())
```

---

## 遗传寻优

当用户不确定最优参数时，用遗传算法自动搜索。

### 流程

```
定义参数空间 → 遗传算法搜索（50 个体 × 30 代）→ 输出最优参数
    │                                                    │
    │   ┌────────────────────────────────────┐           │
    │   │ 每代：                              │           │
    │   │  1. 用每组参数构建策略               │           │
    │   │  2. 策略跑回测 → 得到夏普比率        │           │
    │   │  3. 夏普比率作为适应度               │           │
    │   │  4. 选择 + 交叉 + 变异 → 下一代     │           │
    │   └────────────────────────────────────┘           │
    └──── 收敛/提前终止 ─────────────────────────────────┘
```

### 代码

```python
from scripts.optimizer import GeneticOptimizer, ParameterSpace

# 定义参数空间
space = ParameterSpace()
space.add_int("fast_period", 5, 30)
space.add_int("slow_period", 20, 120)
space.add_float("stop_loss_pct", 0.02, 0.15)
space.add_float("take_profit_pct", 0.05, 0.40)
space.add_int("leverage", 1, 10)

# 适应度函数
def fitness_fn(params):
    strategy = build_ma_cross_strategy(**params)
    # ... 跑回测 ...
    return metrics["sharpe_ratio"]

# 运行
optimizer = GeneticOptimizer(space, fitness_fn, population_size=50, generations=30)
result = optimizer.run()

print(result.best_params)    # {"fast_period": 12, "slow_period": 45, ...}
print(result.best_fitness)   # 2.35
print(result.summary())      # 完整报告
```

### 也支持网格搜索（参数空间小时）

```python
from scripts.optimizer import GridSearch

grid = GridSearch(
    param_grid={
        "fast_period": [5, 10, 15, 20],
        "slow_period": [30, 50, 80],
        "leverage": [3, 5, 10],
    },
    fitness_fn=fitness_fn,
)
result = grid.run()
```

---

## 条件映射表

| 用户说 | Agent 代码 |
|--------|-----------|
| "MACD 金叉" | `Condition.cross_above("macd", "macd_signal")` |
| "MACD 死叉" | `Condition.cross_below("macd", "macd_signal")` |
| "MACD 柱状图由负转正" | `Condition.cross_above("macd_histogram", ...)` + 自定义 |
| "RSI 超过 70" | `Condition.above("rsi", 70)` |
| "RSI 低于 30" | `Condition.below("rsi", 30)` |
| "均线金叉" | `Condition.cross_above("fast_ma", "slow_ma")` |
| "均线死叉" | `Condition.cross_below("fast_ma", "slow_ma")` |
| "跌破布林带下轨" | `Condition("close < bb_lower", lambda ctx: ...)` |
| "资金费率大于 0.05%" | `Condition.above("funding_rate", 0.0005)` |
| "成交量放大 1.5 倍" | `Condition.above("volume_ratio", 1.5)` |
| "且 / 同时" | `condition_a & condition_b` |
| "或 / 任一" | `condition_a \| condition_b` |
| "做多" | `RuleAction.OPEN_LONG` |
| "做空" | `RuleAction.OPEN_SHORT` |
| "平多" | `RuleAction.CLOSE_LONG` |
| "平空" | `RuleAction.CLOSE_SHORT` |
| "盈亏比 1:3" | `stop_loss_pct=0.05, take_profit_pct=0.15` |

---

## 可用指标一览

| 指标 | `indicators_config` 键 | 参数 | ctx 中的字段 |
|------|----------------------|------|------------|
| 简单均线 | `sma_fast` / `sma_slow` | 周期 | `fast_ma` / `slow_ma` |
| 指数均线 | `ema_fast` / `ema_slow` | 周期 | `fast_ema` / `slow_ema` |
| RSI | `rsi_period` | 周期 | `rsi` |
| MACD | `macd: {fast, slow, signal}` | 快/慢/信号 | `macd` / `macd_signal` / `macd_histogram` |
| 布林带 | `bollinger: {period, std}` | 周期/标准差 | `bb_upper` / `bb_middle` / `bb_lower` |
| ATR | `atr_period` | 周期 | `atr` |
| 成交量均线 | `volume_ma_period` | 周期 | `volume_ma` / `volume_ratio` |
| KDJ | `kdj: {k_period, d_period}` | K/D 周期 | `kdj_k` / `kdj_d` / `kdj_j` |

---

## Agent 工作原则

1. **先问再做** — 用户说做策略，追问细节（入场条件、盈亏比、杠杆）
2. **展示策略** — 写完策略调 `strategy.describe()` 让用户确认规则
3. **信号透明** — 回测完展示信号列表和统计，让用户看到每一笔交易
4. **数据说话** — 不主观评价好不好，看夏普、回撤、胜率
5. **迭代优化** — 结果不好建议调参数，或用遗传寻优自动找最优
6. **合理默认** — 杠杆 3x、止损 5%、仓位 20%，用户没指定就用这些
