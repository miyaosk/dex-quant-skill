# 策略 SDK 函数参考

## 目录

- [BacktestEngine 交易函数](#backtestengine-交易函数)
- [BacktestEngine 风控函数](#backtestengine-风控函数)
- [BacktestEngine 查询函数](#backtestengine-查询函数)
- [DataClient 数据函数](#dataclient-数据函数)
- [策略编写模式](#策略编写模式)
- [完整策略示例](#完整策略示例)

---

## BacktestEngine 交易函数

### engine.open_long(symbol, qty, price, mark_price, dt, leverage)

开多仓。

```python
engine.open_long("BTC-USDT-PERP", qty=0.1, price=bar["close"],
                 mark_price=bar["close"], dt=bar["datetime"], leverage=5)
```

### engine.open_short(symbol, qty, price, mark_price, dt, leverage)

开空仓。

```python
engine.open_short("ETH-USDT-PERP", qty=1.0, price=bar["close"],
                  mark_price=bar["close"], dt=bar["datetime"], leverage=10)
```

### engine.close_long(symbol, qty, price, mark_price, dt)

平多仓。`qty` 为平仓数量。

```python
engine.close_long("BTC-USDT-PERP", qty=0.1, price=bar["close"],
                  mark_price=bar["close"], dt=bar["datetime"])
```

### engine.close_short(symbol, qty, price, mark_price, dt)

平空仓。

```python
engine.close_short("ETH-USDT-PERP", qty=1.0, price=bar["close"],
                   mark_price=bar["close"], dt=bar["datetime"])
```

---

## BacktestEngine 风控函数

### engine.set_leverage(symbol, leverage)

```python
engine.set_leverage("BTC-USDT-PERP", 10)
```

### engine.set_margin_mode(symbol, mode)

`mode`: `"isolated"` 或 `"cross"`

```python
engine.set_margin_mode("BTC-USDT-PERP", "isolated")
```

### engine.set_stop_loss(symbol, price)

标记价格触及时自动市价平仓。

```python
engine.set_stop_loss("BTC-USDT-PERP", 58000)
```

### engine.set_take_profit(symbol, price)

```python
engine.set_take_profit("BTC-USDT-PERP", 72000)
```

---

## BacktestEngine 查询函数

### engine.get_position(symbol) → dict

```python
pos = engine.get_position("BTC-USDT-PERP")
# 返回: {"side", "quantity", "avg_entry_price", "unrealized_pnl",
#        "liquidation_price", "leverage", "margin", "margin_ratio"}
```

### engine.get_result() → dict

回测结束后调用，返回完整报告。

### engine.format_summary(result) → str

格式化回测结果为可读文本。

---

## DataClient 数据函数

### client.get_perp_klines(symbol, interval, start_date, end_date)

```python
from scripts.data_client import DataClient
client = DataClient()
df = client.get_perp_klines("BTC-USDT-PERP", "1d", "2024-01-01", "2025-12-31")
# 返回 DataFrame: datetime, open, high, low, close, volume, volume_usd, ...
```

### client.get_funding_rate(symbol, start_date, end_date)

```python
df = client.get_funding_rate("BTC-USDT-PERP", "2024-01-01", "2025-12-31")
# 返回: datetime, funding_rate, mark_price
```

### client.get_exchange_info(symbol)

```python
info = client.get_exchange_info("BTC-USDT-PERP")
# 返回: base_asset, tick_size, min_qty, maintenance_margin_rate, ...
```

### client.get_spot_klines(symbol, interval, start_date, end_date)

```python
df = client.get_spot_klines("BTC-USDT-SPOT", "1d", "2024-01-01", "2025-12-31")
```

### client.get_token_history(token, days)

```python
df = client.get_token_history("PAXG", days=365)
# 返回: datetime, close, volume_usd, market_cap
```

### client.list_perp_symbols()

```python
symbols = client.list_perp_symbols()
# 返回: ["BTC-USDT-PERP", "ETH-USDT-PERP", ...]
```

---

## 策略编写模式

### 基本模式：拉数据 → 逐 bar 回测

```python
from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine, BacktestConfig

client = DataClient()
engine = BacktestEngine(BacktestConfig(
    initial_capital=100_000,
    default_leverage=5,
    margin_mode="isolated",
    enable_funding=True,
    enable_liquidation=True,
))

# 1. 拉数据
klines = client.get_perp_klines("BTC-USDT-PERP", "1d", "2024-01-01", "2025-12-31")
funding = client.get_funding_rate("BTC-USDT-PERP", "2024-01-01", "2025-12-31")

# 2. 构建 funding_rate 查找表
funding_map = {}
for _, row in funding.iterrows():
    key = row["datetime"].strftime("%Y-%m-%d %H:%M")
    funding_map[key] = row["funding_rate"]

# 3. 逐 bar 回测
for i, bar in klines.iterrows():
    dt = str(bar["datetime"])
    prices = {"BTC-USDT-PERP": {
        "close": bar["close"], "high": bar["high"],
        "low": bar["low"], "mark_price": bar["close"],
    }}

    # 检查是否有资金费率结算
    fr_key = bar["datetime"].strftime("%Y-%m-%d %H:%M")
    funding_rates = {}
    if fr_key in funding_map:
        funding_rates["BTC-USDT-PERP"] = funding_map[fr_key]

    engine.on_bar(dt, prices, funding_rates)

    # === 策略逻辑写在这里 ===
    # ...

# 4. 获取结果
result = engine.get_result()
print(engine.format_summary(result))
```

### 资金费率判断模式

资金费率结算时刻为 00:00, 08:00, 16:00 UTC。K 线为日线时，每天包含 3 次结算。使用分钟/小时线回测时，需匹配具体结算时间。

---

## 完整策略示例

### 示例 1：BTC 双均线策略

```python
import numpy as np
from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine, BacktestConfig

client = DataClient()
engine = BacktestEngine(BacktestConfig(
    initial_capital=100_000, default_leverage=5,
    margin_mode="isolated", slippage_bps=2,
))

klines = client.get_perp_klines("BTC-USDT-PERP", "1d", "2024-01-01", "2025-12-31")
funding = client.get_funding_rate("BTC-USDT-PERP", "2024-01-01", "2025-12-31")
funding_map = {row["datetime"].strftime("%Y-%m-%d %H:%M"): row["funding_rate"]
               for _, row in funding.iterrows()}

fast_period, slow_period = 10, 30
closes = []

for i, bar in klines.iterrows():
    dt = str(bar["datetime"])
    price = bar["close"]
    closes.append(price)

    prices = {"BTC-USDT-PERP": {
        "close": price, "high": bar["high"],
        "low": bar["low"], "mark_price": price,
    }}
    fr_key = bar["datetime"].strftime("%Y-%m-%d %H:%M")
    fr = {("BTC-USDT-PERP"): funding_map[fr_key]} if fr_key in funding_map else {}
    engine.on_bar(dt, prices, fr)

    if len(closes) < slow_period:
        continue

    fast_ma = np.mean(closes[-fast_period:])
    slow_ma = np.mean(closes[-slow_period:])
    pos = engine.get_position("BTC-USDT-PERP")

    if fast_ma > slow_ma and pos["side"] != "long":
        if pos["side"] == "short":
            engine.close_short("BTC-USDT-PERP", pos["quantity"], price, price, dt)
        engine.open_long("BTC-USDT-PERP", 0.1, price, price, dt, leverage=5)
        engine.set_stop_loss("BTC-USDT-PERP", price * 0.95)
        engine.set_take_profit("BTC-USDT-PERP", price * 1.15)

    elif fast_ma < slow_ma and pos["side"] != "short":
        if pos["side"] == "long":
            engine.close_long("BTC-USDT-PERP", pos["quantity"], price, price, dt)
        engine.open_short("BTC-USDT-PERP", 0.1, price, price, dt, leverage=5)
        engine.set_stop_loss("BTC-USDT-PERP", price * 1.05)
        engine.set_take_profit("BTC-USDT-PERP", price * 0.85)

result = engine.get_result()
print(engine.format_summary(result))
```

### 示例 2：资金费率套利

```python
from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine, BacktestConfig

client = DataClient()
engine = BacktestEngine(BacktestConfig(
    initial_capital=100_000, default_leverage=1,
    margin_mode="isolated", enable_funding=True,
))

klines = client.get_perp_klines("BTC-USDT-PERP", "1d", "2024-06-01", "2025-12-31")
funding = client.get_funding_rate("BTC-USDT-PERP", "2024-06-01", "2025-12-31")
funding_map = {row["datetime"].strftime("%Y-%m-%d %H:%M"): row["funding_rate"]
               for _, row in funding.iterrows()}

OPEN_THRESHOLD = 0.0005    # 0.05%
CLOSE_THRESHOLD = 0.00015  # 0.015%

for i, bar in klines.iterrows():
    dt = str(bar["datetime"])
    price = bar["close"]
    prices = {"BTC-USDT-PERP": {"close": price, "high": bar["high"],
                                 "low": bar["low"], "mark_price": price}}
    fr_key = bar["datetime"].strftime("%Y-%m-%d %H:%M")
    current_fr = funding_map.get(fr_key, 0)
    fr = {"BTC-USDT-PERP": current_fr} if fr_key in funding_map else {}
    engine.on_bar(dt, prices, fr)

    pos = engine.get_position("BTC-USDT-PERP")

    if pos["side"] == "none" and current_fr > OPEN_THRESHOLD:
        engine.open_short("BTC-USDT-PERP", 0.5, price, price, dt, leverage=1)
    elif pos["side"] == "none" and current_fr < -OPEN_THRESHOLD:
        engine.open_long("BTC-USDT-PERP", 0.5, price, price, dt, leverage=1)
    elif pos["side"] != "none" and abs(current_fr) < CLOSE_THRESHOLD:
        if pos["side"] == "short":
            engine.close_short("BTC-USDT-PERP", pos["quantity"], price, price, dt)
        elif pos["side"] == "long":
            engine.close_long("BTC-USDT-PERP", pos["quantity"], price, price, dt)

result = engine.get_result()
print(engine.format_summary(result))
```
