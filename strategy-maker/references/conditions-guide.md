# 条件规则指南

> 本文档列出策略脚本中可使用的所有条件类型、数据源和组合方式。

---

## 一、技术指标条件

基于 K 线（OHLCV）数据计算，是最常用的条件类型。

### 可用指标

| 指标 | 函数 | 参数 | 典型用法 |
|------|------|------|---------|
| 简单移动平均线 | `Indicators.sma(close, period)` | period: 周期 | 趋势判断 |
| 指数移动平均线 | `Indicators.ema(close, period)` | period: 周期 | 更灵敏的趋势 |
| RSI 相对强弱 | `Indicators.rsi(close, period)` | period: 通常 14 | 超买超卖 |
| MACD | `Indicators.macd(close, fast, slow, signal)` | 默认 12/26/9 | 趋势动量 |
| 布林带 | `Indicators.bollinger(close, period, std_dev)` | 默认 20/2 | 波动区间 |
| ATR 真实波幅 | `Indicators.atr(high, low, close, period)` | period: 通常 14 | 波动大小 |
| KDJ 随机指标 | `Indicators.kdj(high, low, close, n, m1, m2)` | 默认 9/3/3 | 超买超卖 |
| 成交量均线 | `Indicators.volume_ma(volume, period)` | period: 周期 | 量能判断 |
| 金叉判断 | `Indicators.crossover(fast, slow)` | 两条线 | 买入信号 |
| 死叉判断 | `Indicators.crossunder(fast, slow)` | 两条线 | 卖出信号 |
| N 日最高价 | `Indicators.highest(data, period)` | period: 回看周期 | 突破判断 |
| N 日最低价 | `Indicators.lowest(data, period)` | period: 回看周期 | 支撑判断 |

### 条件编写示例

```python
# MACD 金叉买入
cross_up = Indicators.crossover(macd_dif, macd_dea)
if cross_up[i]:
    signal = "buy"

# RSI 超卖买入
if rsi[i] < 30:
    signal = "buy"

# 价格突破 20 日高点 + 放量
if close[i] > Indicators.highest(high, 20)[i-1] and volume[i] > vol_ma[i] * 1.5:
    signal = "buy"

# 均线排列 + ATR 止损
if sma_10[i] > sma_30[i] > sma_60[i]:
    signal = "buy"
    stop_loss = close[i] - 2 * atr[i]
```

---

## 二、社交媒体条件

监控社交平台的实时信息流，提取交易信号。

### 数据源

| 平台 | API | 说明 |
|------|-----|------|
| Twitter/X | Twitter API v2 | 监控关键词、KOL 推文 |
| Reddit | Reddit API | 子版块热度、提及量 |
| Telegram | Telegram Bot API | 频道消息监控 |
| Discord | Discord Bot | 社群信号 |
| 新闻聚合 | NewsAPI / CryptoPanic | 加密货币新闻 |

### 条件编写示例

```python
# KOL 发了含 "$BTC" 的推文
tweets = fetch_twitter_mentions(["$BTC", "bitcoin"])
for tweet in tweets:
    if tweet["author"] in WATCHED_KOLS:
        signal = "buy"

# 1 小时内 bearish 推文暴增
sentiment = analyze_sentiment(recent_tweets)
if sentiment["bearish"] > sentiment["total"] * 0.7:
    signal = "sell"

# 新闻标题含利好关键词
news = fetch_crypto_news(["bitcoin", "etf", "approved"])
if any("approved" in n["title"].lower() for n in news):
    signal = "buy"
```

### 注意事项

- 社媒数据**无法回测**（历史数据不可用），只能实时验证
- API Key 必须通过环境变量传入，不要硬编码
- 需要处理 API 限流（rate limit）
- 社媒信号噪声大，建议与技术指标结合使用

---

## 三、链上数据条件

来自区块链和交易所的链上数据。

### 数据源

| 数据 | 获取方式 | 说明 | Key |
|------|---------|------|-----|
| 资金费率 | `DataClient.get_funding_rate()` | 永续合约多空情绪 | 无需 |
| 持仓量 | `DataClient.get_open_interest()` | 全市场未平仓合约 | 无需 |
| 标记价格 | `DataClient.get_mark_price()` | 交易所标记价格 | 无需 |
| DeFi TVL | `DataClient.get_protocol_tvl()` | 协议锁仓量 | 无需 |
| DEX 交易对 | DEX Screener API | 价格/成交量/流动性 | 无需 |
| 鲸鱼大额转账 | Whale Alert API | 大额链上转账（BTC/ETH/USDT 等） | 免费 Key |
| 钱包地址交易 | Etherscan API | 任意地址的链上交易记录 | 免费 Key |
| 钱包持仓查询 | DeBank OpenAPI | EVM 地址持仓、DeFi 仓位 | 免费 Key |
| Gas 费 | Owlracle API | 多链 Gas 费查询（ETH/BSC/Polygon） | 免费 |
| Gas 费 | Etherscan Gas Oracle | 以太坊实时 Gas 价格 | 免费 Key |

> **无需 Key** = 直接调用  |  **免费 Key** = 免费注册后获取，有调用额度限制

### 条件编写示例

```python
# ── 资金费率过高 → 多头过热 ──
funding_rate = get_funding_rate("BTCUSDT")
if funding_rate > 0.001:  # > 0.1%
    signal = "sell"
    reason = f"资金费率过高 ({funding_rate:.4%})，多头过热"

# ── 持仓量突然增加 ──
oi_change = (current_oi - prev_oi) / prev_oi
if oi_change > 0.2:  # OI 增加 20%
    reason = f"持仓量激增 {oi_change:.0%}"

# ── DEX Screener — 查询某个交易对 ──
import httpx
resp = httpx.get("https://api.dexscreener.com/latest/dex/search?q=PEPE")
pairs = resp.json().get("pairs", [])
if pairs:
    top = pairs[0]
    volume_24h = float(top.get("volume", {}).get("h24", 0))
    liquidity = float(top.get("liquidity", {}).get("usd", 0))
    price_change_1h = float(top.get("priceChange", {}).get("h1", 0))

    if volume_24h > 1_000_000 and price_change_1h > 5:
        signal = "buy"
        reason = f"DEX 24h 量 ${volume_24h:,.0f}，1h 涨 {price_change_1h}%"

    if liquidity < 50_000:
        signal = "sell"
        reason = f"流动性不足 ${liquidity:,.0f}，风险较高"

# ── Whale Alert — 鲸鱼大额转账 ──
# 需要先注册获取免费 Key: https://whale-alert.io/
WHALE_ALERT_KEY = os.getenv("WHALE_ALERT_API_KEY", "")
if WHALE_ALERT_KEY:
    resp = httpx.get(
        "https://api.whale-alert.io/v1/transactions",
        params={"api_key": WHALE_ALERT_KEY, "min_value": 1000000, "currency": "btc"},
    )
    txs = resp.json().get("transactions", [])
    # 大额 BTC 转入交易所 → 可能要卖
    for tx in txs:
        if tx.get("to", {}).get("owner_type") == "exchange":
            signal = "sell"
            reason = f"鲸鱼转入交易所 {tx['amount']:.0f} BTC"

# ── Owlracle — Gas 费查询（无需 Key） ──
resp = httpx.get("https://api.owlracle.info/v4/eth/gas")
gas = resp.json()
if gas.get("speeds"):
    fast_gas = gas["speeds"][-1]["gasPrice"]
    if fast_gas > 100:  # > 100 Gwei
        reason = f"Gas 费飙升 {fast_gas:.0f} Gwei，链上拥堵"

# ── Etherscan — 查询地址交易（免费 Key） ──
ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY", "")
if ETHERSCAN_KEY:
    whale_address = "0x..." # 目标鲸鱼地址
    resp = httpx.get(
        f"https://api.etherscan.io/api",
        params={"module": "account", "action": "txlist", "address": whale_address,
                "startblock": 0, "sort": "desc", "page": 1, "offset": 5,
                "apikey": ETHERSCAN_KEY},
    )
    txs = resp.json().get("result", [])
    # 分析鲸鱼最近交易...
```

---

## 四、大盘/跨资产条件

跨市场联动信号。

### 数据源

| 数据 | 获取方式 |
|------|---------|
| BTC 走势 | `DataClient.get_perp_klines("BTC-USDT-PERP", ...)` |
| 美股指数 | `DataClient.get_stock_klines("^IXIC", ...)` (纳指) |
| 黄金 | `DataClient.get_metal_spot_klines("gold", ...)` |
| 原油 | `DataClient.get_commodity_klines("crude_oil", ...)` |

### 条件编写示例

```python
# BTC 日线收阳 → 山寨币跟涨
btc_df = client.get_perp_klines("BTC-USDT-PERP", "1d", limit=2)
if btc_df.iloc[-1]["close"] > btc_df.iloc[-1]["open"]:
    signal = "buy"  # 买山寨币
    reason = "BTC 日线收阳，山寨联动上涨"
```

---

## 五、条件组合

多个条件可以用 AND / OR 组合。建议在脚本中用打分制：

```python
score = 0.0

# 技术面
if macd_cross_up:  score += 0.4
if rsi < 35:       score += 0.3

# 链上面
if funding_rate < -0.0005:  score += 0.2

# 社媒面
if social_sentiment > 0.7:  score += 0.2

# 综合判断
if score >= 0.5:
    action = "buy"
elif score <= -0.5:
    action = "sell"
else:
    action = "hold"
```

---

## 六、时间周期参考

| 周期 | 适合策略类型 | 交易频率 |
|------|------------|---------|
| 1m / 5m | 高频/剥头皮 | 每天数十次 |
| 15m / 1h | 日内交易 | 每天几次 |
| **4h** | 波段交易（推荐） | 每周几次 |
| 1d | 中长线趋势 | 每月几次 |
| 1w | 长线持有 | 很少交易 |
