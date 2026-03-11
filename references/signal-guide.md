# 信号定制指南

本文档教 Agent 如何将用户的自然语言描述转化为可执行的交易信号。

---

## 核心流程

```
用户自然语言 → Agent 解析 → 选择指标 → 组合条件 → 生成信号 → 装入策略 → 回测验证
```

## 四阶段工作流

| 阶段 | 用户说 | Agent 做 |
|------|--------|----------|
| 1. 信号定制 | "RSI 低于 30 且放量时买入" | 调用 `Indicators.rsi()` + `Condition.below("rsi", 30) & Condition.above("volume_ratio", 1.5)` |
| 2. 策略生成 | "用这个信号做 BTC 永续，5 倍杠杆" | 组装 `SignalStrategy`，配置杠杆、仓位、止损止盈 |
| 3. 交易模拟 | "跑一下去年的行情" | `BacktestEngine` 逐 bar 执行信号 → 开仓/平仓 |
| 4. 回测验证 | "效果怎么样？" | 输出收益率、夏普、最大回撤、资金费率损益等 |

---

## 第一步：从自然语言提取信号要素

### 解析模板

当用户说一句话时，Agent 应提取以下要素：

| 要素 | 示例 |
|------|------|
| **指标** | RSI、均线、MACD、布林带、资金费率、持仓量 |
| **条件** | 大于、小于、交叉上穿、交叉下穿、在…之间 |
| **阈值** | 70、30、0.05%、20 日 |
| **方向** | 做多、做空、平仓 |
| **风控** | 止损 5%、止盈 15%、3 倍杠杆 |

### 自然语言 → 代码映射表

| 用户说 | 转译为 |
|--------|--------|
| "RSI 超过 70" | `Condition.above("rsi", 70)` |
| "RSI 低于 30" | `Condition.below("rsi", 30)` |
| "快速均线上穿慢速均线" | `Condition.cross_above("fast_ma", "slow_ma")` |
| "快速均线下穿慢速均线" | `Condition.cross_below("fast_ma", "slow_ma")` |
| "价格跌破布林带下轨" | `Condition("close < bb_lower", lambda ctx: ctx["close"] < ctx["bb_lower"])` |
| "资金费率大于 0.05%" | `Condition.above("funding_rate", 0.0005)` |
| "成交量放大 1.5 倍" | `Condition.above("volume_ratio", 1.5)` |
| "价格在 60000 到 65000 之间" | `Condition.between("close", 60000, 65000)` |
| "MACD 柱状图由负转正" | `Condition.cross_above("macd_histogram", "zero_line")`（需自定义）|
| "且 / 同时" | `condition_a & condition_b` |
| "或 / 任一" | `condition_a \| condition_b` |
| "做多" | `SignalType.ENTRY_LONG` |
| "做空" | `SignalType.ENTRY_SHORT` |
| "平多 / 卖出" | `SignalType.EXIT_LONG` |
| "平空 / 买回" | `SignalType.EXIT_SHORT` |
| "5 倍杠杆" | `leverage=5` |
| "止损 3%" | `stop_loss_pct=0.03` |
| "止盈 10%" | `take_profit_pct=0.10` |
| "仓位 10%" | `position_size=0.10` |

---

## 第二步：选择/配置指标

### 可用指标一览

| 指标 | `indicators_config` 键 | 参数 | 默认值 |
|------|----------------------|------|--------|
| 简单均线 | `sma_fast` / `sma_slow` | 周期 | 10 / 30 |
| 指数均线 | `ema_fast` / `ema_slow` | 周期 | 12 / 26 |
| RSI | `rsi_period` | 周期 | 14 |
| MACD | `macd: {fast, slow, signal}` | 快/慢/信号 | 12/26/9 |
| 布林带 | `bollinger: {period, std}` | 周期/标准差 | 20/2.0 |
| ATR | `atr_period` | 周期 | 14 |
| 成交量均线 | `volume_ma_period` | 周期 | 20 |

### 指标上下文字段

计算完成后，以下字段会出现在 `ctx` 中供条件使用：

| 字段 | 含义 |
|------|------|
| `close` | 当前收盘价 |
| `high` / `low` | 最高/最低价 |
| `volume` | 当前成交量 |
| `funding_rate` | 资金费率 |
| `open_interest` | 持仓量 |
| `fast_ma` / `slow_ma` | 快/慢简单均线 |
| `fast_ema` / `slow_ema` | 快/慢指数均线 |
| `rsi` | RSI 值 (0-100) |
| `macd` / `macd_signal` / `macd_histogram` | MACD 三线 |
| `bb_upper` / `bb_middle` / `bb_lower` | 布林带三轨 |
| `atr` | 平均真实波幅 |
| `volume_ma` | 成交量均线 |
| `volume_ratio` | 成交量/成交量均线 |
| `prev_*` | 上一个 bar 的对应值（用于交叉判断） |

---

## 第三步：组装策略

### 快捷模式（预设信号组）

Agent 可直接调用预设函数：

```python
from scripts.signal_builder import (
    SignalStrategy,
    build_ma_cross_signals,       # 均线交叉
    build_rsi_signals,            # RSI 超买超卖
    build_funding_rate_signals,   # 资金费率套利
    build_bollinger_signals,      # 布林带突破
    build_multi_factor_signals,   # 多因子组合
)

# 用户说: "用双均线策略做 BTC，5 倍杠杆"
strategy = SignalStrategy(name="BTC 双均线", symbol="BTC-USDT-PERP")
config, signals = build_ma_cross_signals(fast_period=10, slow_period=30, leverage=5)
strategy.indicators_config = config
for sig in signals:
    strategy.add_signal(sig)
```

### 自定义模式（用户自由组合）

```python
from scripts.signal_builder import (
    SignalStrategy, Signal, SignalType, Condition,
)

# 用户说: "RSI 低于 30 且放量 1.5 倍以上时做多 ETH，3 倍杠杆，止损 5%"
strategy = SignalStrategy(
    name="ETH RSI 超卖放量",
    symbol="ETH-USDT-PERP",
    indicators_config={"rsi_period": 14, "volume_ma_period": 20},
)
strategy.add_signal(Signal(
    name="RSI超卖+放量做多",
    signal_type=SignalType.ENTRY_LONG,
    condition=Condition.below("rsi", 30) & Condition.above("volume_ratio", 1.5),
    leverage=3,
    position_size=0.1,
    stop_loss_pct=0.05,
))
strategy.add_signal(Signal(
    name="RSI回归平多",
    signal_type=SignalType.EXIT_LONG,
    condition=Condition.above("rsi", 50),
))
```

---

## 第四步：接入回测引擎

```python
from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine
import numpy as np

# 获取数据
dc = DataClient()
klines = dc.get_perp_klines("BTCUSDT", "1d", limit=365)

closes = np.array([k["close"] for k in klines])
highs = np.array([k["high"] for k in klines])
lows = np.array([k["low"] for k in klines])
volumes = np.array([k["volume"] for k in klines])

# 初始化回测引擎
engine = BacktestEngine(initial_capital=100000)
engine.set_leverage("BTC-USDT-PERP", 5)

# 逐 bar 运行
prev_ctx = None
for i in range(30, len(closes)):  # 跳过指标预热期
    ctx = strategy.compute_context(
        closes[:i+1], highs[:i+1], lows[:i+1], volumes[:i+1],
        prev_ctx=prev_ctx,
    )
    triggered = strategy.evaluate(ctx)
    for sig in triggered:
        if sig.signal_type == SignalType.ENTRY_LONG:
            engine.open_long("BTC-USDT-PERP", sig.position_size, closes[i])
        elif sig.signal_type == SignalType.ENTRY_SHORT:
            engine.open_short("BTC-USDT-PERP", sig.position_size, closes[i])
        elif sig.signal_type == SignalType.EXIT_LONG:
            engine.close_long("BTC-USDT-PERP", closes[i])
        elif sig.signal_type == SignalType.EXIT_SHORT:
            engine.close_short("BTC-USDT-PERP", closes[i])
    prev_ctx = ctx

# 输出结果
metrics = engine.get_metrics()
print(f"总收益率: {metrics['total_return']:.2%}")
print(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
print(f"最大回撤: {metrics['max_drawdown']:.2%}")
```

---

## 常见用户场景 → Agent 应答

### 场景 1: "帮我做一个 RSI 策略"

```
→ 问清楚: RSI 周期？超买超卖阈值？做什么币？杠杆？
→ 如果用户没指定，用默认值: RSI(14)，超买 70，超卖 30
→ 调用 build_rsi_signals()
→ 展示信号描述 → 用户确认 → 运行回测
```

### 场景 2: "BTC 资金费率高的时候做空"

```
→ 确认阈值: "资金费率高于多少算高？默认 0.05%"
→ 调用 build_funding_rate_signals(open_threshold=0.0005)
→ 同时建议搭配现货对冲
```

### 场景 3: "我想在价格跌破布林带下轨时抄底"

```
→ 调用 build_bollinger_signals()
→ 只保留 ENTRY_LONG 和 EXIT_LONG 信号
→ 建议加上 RSI 过滤避免趋势性下跌中抄底
```

### 场景 4: "综合多个指标判断"

```
→ 调用 build_multi_factor_signals()
→ 或用 Condition 的 & / | 自由组合
→ 展示完整条件链让用户确认
```

### 场景 5: "我自己有一个特殊逻辑"

```
→ 用 Condition 的 lambda 模式支持任意 Python 逻辑
→ 如: Condition("自定义条件", lambda ctx: ctx["close"] > ctx["prev_close"] * 1.03)
```

---

## Agent 关键原则

1. **永远先问清楚再动手** — 用户说"做一个策略"时，追问指标、参数、标的、风控
2. **展示信号描述** — 生成后调用 `strategy.describe()` 让用户看到完整信号逻辑
3. **先回测再评价** — 不要主观评价策略好不好，让数据说话
4. **建议合理的默认值** — 杠杆默认 3-5x，止损 3-5%，仓位 10%
5. **多信号组合优先** — 单指标信号噪音大，建议用户组合 2-3 个条件
