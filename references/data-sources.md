# 数据源详细规格

## 目录

- [Binance Futures API（永续合约）](#binance-futures-api)
- [Binance Spot API（现货）](#binance-spot-api)
- [CoinGecko API（代币价格）](#coingecko-api)
- [限流与注意事项](#限流与注意事项)
- [找不到的数据接口](#找不到的数据接口)

---

## Binance Futures API

Base URL: `https://fapi.binance.com`

**全部为公开端点，无需 API Key。**

### K 线 — GET /fapi/v1/klines

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | Binance 格式，如 `BTCUSDT` |
| interval | string | 是 | `1m / 5m / 15m / 1h / 4h / 1d` |
| startTime | long | 否 | 毫秒时间戳 |
| endTime | long | 否 | 毫秒时间戳 |
| limit | int | 否 | 默认 500，最大 1500 |

返回数组，每条:
```
[open_time, open, high, low, close, volume, close_time,
 quote_volume, trades, taker_buy_volume, taker_buy_quote_volume, ignore]
```

- 历史深度：**无限制**（上线以来全部数据）
- 单次最多 1500 条，`data_client.py` 已实现自动分页
- 限流: IP 2400 次/分钟

### 资金费率 — GET /fapi/v1/fundingRate

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 否 | 如 `BTCUSDT` |
| startTime | long | 否 | 毫秒时间戳 |
| endTime | long | 否 | 毫秒时间戳 |
| limit | int | 否 | 默认 100，最大 1000 |

返回:
```json
{"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1700000000000, "markPrice": "43250.5"}
```

- 每 8 小时一条
- 历史深度：**上线以来全部**
- `data_client.py` 已实现自动分页拉取
- 限流: 500 次/5 分钟（与其他 funding 端点共享）

### 当前持仓量 — GET /fapi/v1/openInterest

| 参数 | 类型 | 必填 |
|------|------|------|
| symbol | string | 是 |

- 仅返回**当前快照**，无历史
- 限流: 权重 1

### 持仓量历史 — GET /futures/data/openInterestHist

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| pair | string | 是 | 如 `BTC`（不含 USDT） |
| contractType | string | 是 | `PERPETUAL` |
| period | string | 是 | `5m / 15m / 30m / 1h / 2h / 4h / 6h / 12h / 1d` |
| limit | int | 否 | 默认 30，最大 500 |

- **⚠️ 仅最近 30 天数据**
- 返回: `sumOpenInterest`（张）、`sumOpenInterestValue`（USDT）

### Top Trader 多空比 — GET /futures/data/topLongShortPositionRatio

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | 如 `BTCUSDT` |
| period | string | 是 | `5m / 15m / 30m / 1h / 2h / 4h / 6h / 12h / 1d` |
| limit | int | 否 | 默认 30，最大 500 |

- **⚠️ 仅最近 30 天数据**
- 基于持仓保证金余额 Top 20% 的用户

### 标记价格 — GET /fapi/v1/premiumIndex

| 参数 | 类型 | 必填 |
|------|------|------|
| symbol | string | 否 |

返回: `markPrice`、`indexPrice`、`lastFundingRate`、`nextFundingTime`

### 合约信息 — GET /fapi/v1/exchangeInfo

- 无需参数，返回所有合约的完整规格
- 包含: 合约类型、最小下单量、价格精度、维持保证金率等
- `data_client.py` 已解析为统一格式

---

## Binance Spot API

Base URL: `https://api.binance.com`

### 现货 K 线 — GET /api/v3/klines

参数和返回格式与 Futures K 线相同。

- 限流: IP 6000 次/分钟
- 历史深度: 无限制

---

## CoinGecko API

Base URL: `https://api.coingecko.com/api/v3`

### 代币价格历史 — GET /coins/{id}/market_chart

| 参数 | 类型 | 说明 |
|------|------|------|
| vs_currency | string | `usd` |
| days | int | 历史天数 |
| interval | string | `daily` |

已配置的代币 ID 映射:

| 代币 | CoinGecko ID |
|------|-------------|
| PAXG | pax-gold |
| XAUT | tether-gold |
| OUSG | ondo-us-government-bond-fund |
| OMMF | ondo-us-dollar-yield |

- 免费版限流: **10-30 次/分钟**
- 免费版日线最多 **365 天**
- 超过 365 天需 Pro API（付费）

---

## yfinance — 美股 / 大宗商品 / 贵金属

数据源: Yahoo Finance（通过 `yfinance` Python 包）

**免费，无需 API Key，无严格限流。**

### 美股 K 线 — get_stock_klines()

已配置的 Symbol 映射:

| 我方 Symbol | yfinance Ticker | 说明 |
|------------|----------------|------|
| RWA:AAPL | AAPL | 苹果 |
| RWA:NVDA | NVDA | 英伟达 |
| RWA:TSLA | TSLA | 特斯拉 |
| RWA:MSFT | MSFT | 微软 |
| RWA:GOOGL | GOOGL | 谷歌 |
| RWA:AMZN | AMZN | 亚马逊 |
| RWA:META | META | Meta |
| RWA:SPY | SPY | 标普 500 ETF |
| RWA:QQQ | QQQ | 纳斯达克 100 ETF |

- 日线历史: **30+ 年**
- 分钟线: 最近 7 天（1m）/ 60 天（5m/15m）/ 730 天（1h）
- 包含股息数据

### 大宗商品期货 — get_commodity_klines()

| 我方 Symbol | yfinance Ticker | 说明 |
|------------|----------------|------|
| COMM:WTI | CL=F | WTI 原油期货 |
| COMM:BRENT | BZ=F | 布伦特原油期货 |
| COMM:NG | NG=F | 天然气期货 |
| COMM:COPPER | HG=F | 铜期货 |

- 历史深度: **10+ 年**

### 贵金属现货 — get_metal_spot_klines()

| 我方 Symbol | yfinance Ticker | 说明 |
|------------|----------------|------|
| METAL:XAU-SPOT | GC=F | 黄金期货（代理现货） |
| METAL:XAG-SPOT | SI=F | 白银期货（代理现货） |

- 历史深度: **10+ 年**
- 注意: 实际用期货价格代理现货，与伦敦定盘价有微小差异

---

## DeFi Llama — 协议 TVL / 手续费

Base URL: `https://api.llama.fi`

**免费端点，无需 API Key。**

### 协议 TVL 历史 — GET /api/protocol/{slug}

返回从协议上线至今的每日 TVL。

支持协议（slug）:
`aave` / `compound-v3` / `lido` / `curve-dex` / `uniswap` / `makerdao` / `rocket-pool` / `convex-finance` 等

### 协议手续费 — GET /api/overview/fees

返回所有协议的 24h / 7d / 30d 手续费和收入。

### 协议列表 — GET /api/protocols

返回所有协议基本信息 + 当前 TVL。

---

## 限流与注意事项

| API | 限流 | 注意 |
|-----|------|------|
| Binance Futures K 线 | 2400/min | 分页拉取时加 100ms 间隔 |
| Binance Futures 资金费率 | 500/5min（共享） | 大量拉取时控速 |
| Binance Futures 数据统计 | 1000/5min | openInterestHist / longShortRatio |
| Binance Spot | 6000/min | 宽松 |
| CoinGecko 免费 | 10-30/min | 严格，建议加缓存 |
| yfinance | 无硬限制 | Yahoo 可能临时封 IP，建议加间隔 |
| DeFi Llama 免费 | 无硬限制 | 偶尔慢，建议缓存 |

**国内访问**: Binance API 可能需代理，设置环境变量 `PROXY_URL`。

---

## 仍需协调的数据（3 项）

以下数据**没有免费公开 API**，需付费或自建：

### 1. 聚合爆仓数据
- Binance 不提供聚合爆仓统计端点
- **推荐**: Coinglass API（~$50/月），提供 `long_liquidation_usd / short_liquidation_usd`

### 2. 持仓量/多空比 超过 30 天的历史
- Binance `openInterestHist` 和 `topLongShortPositionRatio` 仅保留 30 天
- **推荐**: 自建 cron 定时采集（每小时跑一次存数据库），或 Coinglass

### 3. DeFi 收益率 APY 历史
- DeFi Llama `yields/pools` 端点需 Pro API Key
- TVL 历史已通过免费端点覆盖，但具体池子的 APY 时间序列需 Pro
- **推荐**: 申请 DeFi Llama Pro，或自建链上事件采集
