# 数据源 API 详细规格

## 目录

- [Binance Futures（永续合约）](#binance-futures永续合约)
- [Binance Spot（现货）](#binance-spot现货)
- [CoinGecko（代币价格）](#coingecko代币价格)
- [Yahoo Finance（美股/大宗商品/贵金属）](#yahoo-finance美股大宗商品贵金属)
- [DeFi Llama（协议 TVL/手续费）](#defi-llama协议-tvl手续费)
- [限流与注意事项](#限流与注意事项)
- [代理配置](#代理配置)

---

## Binance Futures（永续合约）

Base URL: `https://fapi.binance.com`

**全部为公开端点，无需 API Key。**

### GET /fapi/v1/klines — 永续合约 K 线

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | Binance 格式，如 `BTCUSDT` |
| interval | string | 是 | `1m / 5m / 15m / 1h / 4h / 1d` |
| startTime | long | 否 | 毫秒时间戳 |
| endTime | long | 否 | 毫秒时间戳 |
| limit | int | 否 | 默认 500，最大 1500 |

**返回格式**（数组，每条）:
```
[open_time, open, high, low, close, volume, close_time,
 quote_volume, trades, taker_buy_volume, taker_buy_quote_volume, ignore]
```

| 属性 | 值 |
|------|-----|
| 历史深度 | **无限制**（合约上线以来全部数据） |
| 单次最多 | 1500 条 |
| 分页方式 | 设置 `startTime = 上一批最后一条的 open_time + 1` |
| 限流 | IP 2400 次/分钟 |

### GET /fapi/v1/fundingRate — 资金费率历史

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 否 | 如 `BTCUSDT` |
| startTime | long | 否 | 毫秒时间戳 |
| endTime | long | 否 | 毫秒时间戳 |
| limit | int | 否 | 默认 100，最大 1000 |

**返回格式**:
```json
{
  "symbol": "BTCUSDT",
  "fundingRate": "0.00010000",
  "fundingTime": 1700000000000,
  "markPrice": "43250.5"
}
```

| 属性 | 值 |
|------|-----|
| 频率 | 每 8 小时一条（00:00, 08:00, 16:00 UTC） |
| 历史深度 | **上线以来全部** |
| 单次最多 | 1000 条 |
| 分页方式 | 设置 `startTime = 上一批最后一条的 fundingTime + 1` |
| 限流 | 500 次 / 5 分钟（与其他 funding 端点共享） |

### GET /fapi/v1/openInterest — 当前持仓量快照

| 参数 | 类型 | 必填 |
|------|------|------|
| symbol | string | 是 |

| 属性 | 值 |
|------|-----|
| 返回 | 仅**当前快照**，无历史 |
| 限流 | 权重 1 |

### GET /futures/data/openInterestHist — 持仓量历史

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| pair | string | 是 | 如 `BTC`（不含 USDT） |
| contractType | string | 是 | `PERPETUAL` |
| period | string | 是 | `5m / 15m / 30m / 1h / 2h / 4h / 6h / 12h / 1d` |
| limit | int | 否 | 默认 30，最大 500 |

| 属性 | 值 |
|------|-----|
| ⚠️ 历史深度 | **仅最近 30 天** |
| 返回字段 | `sumOpenInterest`（张）、`sumOpenInterestValue`（USDT） |
| 限流 | 1000 次 / 5 分钟 |

### GET /futures/data/topLongShortPositionRatio — Top Trader 多空比

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | 如 `BTCUSDT` |
| period | string | 是 | `5m / 15m / 30m / 1h / 2h / 4h / 6h / 12h / 1d` |
| limit | int | 否 | 默认 30，最大 500 |

| 属性 | 值 |
|------|-----|
| ⚠️ 历史深度 | **仅最近 30 天** |
| 样本 | 持仓保证金余额 Top 20% 的用户 |
| 限流 | 1000 次 / 5 分钟 |

### GET /fapi/v1/premiumIndex — 标记价格 + 资金费率

| 参数 | 类型 | 必填 |
|------|------|------|
| symbol | string | 否 |

返回: `markPrice`、`indexPrice`、`lastFundingRate`、`nextFundingTime`

### GET /fapi/v1/exchangeInfo — 合约规格

- 无需参数，返回所有合约的完整规格
- 包含: 合约类型、最小下单量、价格精度、维持保证金率
- 解析后字段: `tick_size`, `min_qty`, `max_qty`, `step_size`, `maintenance_margin_rate`

---

## Binance Spot（现货）

Base URL: `https://api.binance.com`

### GET /api/v3/klines — 现货 K 线

参数和返回格式与 Futures K 线完全相同。

| 属性 | 值 |
|------|-----|
| 历史深度 | **无限制** |
| 限流 | IP 6000 次/分钟 |

---

## CoinGecko（代币价格）

Base URL: `https://api.coingecko.com/api/v3`

### GET /coins/{id}/market_chart — 代币价格历史

| 参数 | 类型 | 说明 |
|------|------|------|
| vs_currency | string | `usd` |
| days | int | 历史天数 |
| interval | string | `daily` |

**已配置的代币 ID 映射**:

| 代币 | CoinGecko ID | 说明 |
|------|-------------|------|
| PAXG | pax-gold | 黄金锚定代币 |
| XAUT | tether-gold | Tether 黄金代币 |
| OUSG | ondo-us-government-bond-fund | 美债基金代币 |
| OMMF | ondo-us-dollar-yield | 美元收益代币 |

| 属性 | 值 |
|------|-----|
| 免费版限流 | **10-30 次/分钟** |
| 免费版日线 | 最多 **365 天** |
| 返回字段 | `prices`、`total_volumes`、`market_caps` |

---

## Yahoo Finance（美股/大宗商品/贵金属）

数据源: `yfinance` Python 包。**免费，无需 API Key。**

### 美股 K 线 — `get_stock_klines()`

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
- 包含股息数据

### 大宗商品期货 — `get_commodity_klines()`

| 我方 Symbol | yfinance Ticker | 说明 |
|------------|----------------|------|
| COMM:WTI | CL=F | WTI 原油期货 |
| COMM:BRENT | BZ=F | 布伦特原油期货 |
| COMM:NG | NG=F | 天然气期货 |
| COMM:COPPER | HG=F | 铜期货 |

- 历史深度: **10+ 年**

### 贵金属现货 — `get_metal_spot_klines()`

| 我方 Symbol | yfinance Ticker | 说明 |
|------------|----------------|------|
| METAL:XAU-SPOT | GC=F | 黄金期货（代理现货） |
| METAL:XAG-SPOT | SI=F | 白银期货（代理现货） |

- 历史深度: **10+ 年**
- 注意: 实际用期货价格代理现货，与伦敦定盘价有微小差异

---

## DeFi Llama（协议 TVL/手续费）

Base URL: `https://api.llama.fi`

**免费端点，无需 API Key。**

### GET /protocol/{name} — 协议 TVL 历史 + 基本信息

返回从协议上线至今的每日 TVL，以及协议基本信息（类别、支持的链等）。

支持的协议（slug）:
`aave` / `compound-v3` / `lido` / `curve-dex` / `uniswap` / `makerdao` / `rocket-pool` / `convex-finance` 等

### GET /fees/{protocol} — 协议手续费/收入

返回协议的手续费和收入数据（24h / 7d / 30d）。

### GET /overview/fees — 所有协议手续费概览

返回所有协议的 24h / 7d / 30d 手续费和收入汇总。

### GET /protocols — 协议列表

返回所有 DeFi 协议基本信息 + 当前 TVL。

---

## 限流与注意事项

| API | 限流 | 建议 |
|-----|------|------|
| Binance Futures K 线 | 2400 次/分钟 | 分页拉取时加 100ms 间隔 |
| Binance Futures 资金费率 | 500 次/5 分钟（共享） | 大量拉取时控速 |
| Binance Futures 数据统计 | 1000 次/5 分钟 | `openInterestHist` / `longShortRatio` |
| Binance Spot | 6000 次/分钟 | 宽松 |
| CoinGecko 免费 | 10-30 次/分钟 | **严格**，建议加缓存 |
| yfinance | 无硬限制 | Yahoo 可能临时封 IP，建议加间隔 |
| DeFi Llama 免费 | 无硬限制 | 偶尔慢，建议缓存 |

### 分页注意事项

- **Binance K 线**: 单次最多 1500 条。`data_client.py` 已实现自动分页，设置 `startTime = 上一批 open_time + 1`。
- **Binance 资金费率**: 单次最多 1000 条。自动分页，设置 `startTime = 上一批 fundingTime + 1`。
- **其他端点**: 无需分页或仅返回快照。

---

## 代理配置

国内访问 Binance API 需配置代理。设置环境变量:

```bash
export PROXY_URL="http://127.0.0.1:7890"
```

`data_client.py` 初始化时自动读取 `PROXY_URL` 环境变量并应用到所有 HTTP 请求。
