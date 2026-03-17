# 策略示例

> 展示从用户自然语言到策略脚本的转换过程。每个示例包含用户输入和对应生成的脚本核心逻辑。

---

## 示例 1：MACD 金叉策略（纯技术指标）

### 用户输入

> "帮我做一个 BTC 的策略，MACD 金叉就买，死叉就卖，成交量要放大才入场"

### AI 提取的规则

| 要素 | 值 |
|------|-----|
| 币种 | BTCUSDT |
| 买入条件 | MACD 金叉 AND 成交量 > 20日均量 × 1.5 |
| 卖出条件 | MACD 死叉 |
| 数据源 | K 线 OHLCV |
| 模板 | `technical_strategy.py` |

### 生成的核心逻辑

```python
# 买入: MACD 金叉 + 放量
if cross_up[i] and volume[i] > vol_ma[i] * 1.5:
    return {"symbol": "BTCUSDT", "action": "buy", "reason": "MACD金叉+放量"}

# 卖出: MACD 死叉
if cross_down[i]:
    return {"symbol": "BTCUSDT", "action": "sell", "reason": "MACD死叉"}
```

---

## 示例 2：RSI 均值回归（技术指标 + 风控）

### 用户输入

> "ETH 的 RSI 低于 25 就买，高于 75 就卖，止损 3%，止盈 8%，4 小时周期"

### 生成的核心逻辑

```python
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.08

rsi = Indicators.rsi(close, 14)

# 买入: RSI 超卖
if rsi[i] < 25:
    return {
        "symbol": "ETHUSDT", "action": "buy",
        "reason": f"RSI 超卖 ({rsi[i]:.0f})",
        "suggested_stop_loss": price * (1 - STOP_LOSS_PCT),
        "suggested_take_profit": price * (1 + TAKE_PROFIT_PCT),
    }

# 卖出: RSI 超买
if rsi[i] > 75:
    return {"symbol": "ETHUSDT", "action": "sell", "reason": f"RSI 超买 ({rsi[i]:.0f})"}
```

---

## 示例 3：推特 KOL 监控（社媒策略）

### 用户输入

> "监控 Elon Musk 的推特，如果他提到 Doge 或者 Shiba 就买，提到 sell 就卖"

### 生成的核心逻辑

```python
WATCHED_ACCOUNTS = ["elonmusk"]
BUY_KEYWORDS = ["doge", "shiba", "dogecoin", "shib"]
SELL_KEYWORDS = ["sell", "dump", "goodbye"]

tweets = fetch_twitter_mentions(["from:elonmusk"], minutes_back=30)

for tweet in tweets:
    text = tweet["text"].lower()
    if any(kw in text for kw in BUY_KEYWORDS):
        return {
            "symbol": "DOGEUSDT", "action": "buy",
            "reason": f"Elon Musk 推文提到 Doge: '{tweet['text'][:50]}'",
            "source_type": "social",
        }
    if any(kw in text for kw in SELL_KEYWORDS):
        return {
            "symbol": "DOGEUSDT", "action": "sell",
            "reason": f"Elon Musk 推文含卖出信号",
            "source_type": "social",
        }
```

---

## 示例 4：技术 + 资金费率混合策略

### 用户输入

> "BTC 均线金叉就买，但如果资金费率太高就不买（大于 0.1%），死叉就卖"

### 生成的核心逻辑

```python
cross_up = Indicators.crossover(sma_10, sma_30)
cross_down = Indicators.crossunder(sma_10, sma_30)
funding_rate = get_funding_rate("BTCUSDT")

# 买入: 金叉 + 资金费率正常
if cross_up[i] and funding_rate < 0.001:
    return {"symbol": "BTCUSDT", "action": "buy",
            "reason": f"均线金叉 + 资金费率正常 ({funding_rate:.4%})",
            "source_type": "mixed"}

# 金叉但资金费率过高 → 不买
if cross_up[i] and funding_rate >= 0.001:
    # 不触发信号，但记录原因
    pass  # 用户问"为什么没信号"时可以解释

# 卖出: 死叉
if cross_down[i]:
    return {"symbol": "BTCUSDT", "action": "sell", "reason": "均线死叉"}
```

---

## 示例 5：多币种轮动策略

### 用户输入

> "同时监控 BTC、ETH、SOL，哪个 RSI 最低且低于 30 就买哪个，RSI 最高且高于 70 就卖"

### 生成的核心逻辑

```python
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
signals = []

rsi_values = {}
for symbol in SYMBOLS:
    df = get_klines(symbol, "4h", limit=100)
    rsi = Indicators.rsi(df["close"].values, 14)
    rsi_values[symbol] = rsi[-1]

# 找 RSI 最低的
min_symbol = min(rsi_values, key=rsi_values.get)
if rsi_values[min_symbol] < 30:
    signals.append({"symbol": min_symbol, "action": "buy",
                    "reason": f"RSI 最低 ({rsi_values[min_symbol]:.0f})，超卖买入"})

# 找 RSI 最高的
max_symbol = max(rsi_values, key=rsi_values.get)
if rsi_values[max_symbol] > 70:
    signals.append({"symbol": max_symbol, "action": "sell",
                    "reason": f"RSI 最高 ({rsi_values[max_symbol]:.0f})，超买卖出"})
```

---

## 示例 6：新闻驱动策略

### 用户输入

> "监控加密货币新闻，如果出现 ETF 相关利好就买 BTC，如果出现监管打压就卖"

### 生成的核心逻辑

```python
BULLISH_PATTERNS = ["etf approved", "etf approval", "institutional buy", "mass adoption"]
BEARISH_PATTERNS = ["ban crypto", "sec lawsuit", "exchange hack", "rug pull"]

news = fetch_crypto_news(["bitcoin", "crypto"], hours_back=2)

for article in news:
    title = article["title"].lower()
    if any(p in title for p in BULLISH_PATTERNS):
        return {"symbol": "BTCUSDT", "action": "buy",
                "reason": f"利好新闻: {article['title'][:60]}",
                "source_type": "social"}
    if any(p in title for p in BEARISH_PATTERNS):
        return {"symbol": "BTCUSDT", "action": "sell",
                "reason": f"利空新闻: {article['title'][:60]}",
                "source_type": "social"}
```
