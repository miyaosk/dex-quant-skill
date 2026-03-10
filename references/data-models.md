# 数据模型与 Symbol 命名规范

## 目录

- [Symbol 命名规范](#symbol-命名规范)
- [资产类型](#资产类型)
- [统一返回格式](#统一返回格式)
- [永续合约数据规格](#永续合约数据规格)
- [支持的永续合约列表](#支持的永续合约列表)

---

## Symbol 命名规范

| 资产类型 | 格式 | 示例 |
|----------|------|------|
| 加密永续合约 | `{BASE}-{QUOTE}-PERP` | `BTC-USDT-PERP` |
| 加密现货 | `{BASE}-{QUOTE}-SPOT` | `BTC-USDT-SPOT` |
| 代币化美股 | `RWA:{TICKER}` | `RWA:AAPL` |
| 贵金属代币 | `METAL:{SYMBOL}` | `METAL:PAXG` |
| 现货贵金属 | `METAL:{SYMBOL}-SPOT` | `METAL:XAU-SPOT` |
| 大宗商品 | `COMM:{SYMBOL}` | `COMM:WTI` |
| A 股 | `CN:{CODE}` | `CN:600519` |

---

## 资产类型

| asset_type | 说明 | 交易时间 | 计价 |
|------------|------|----------|------|
| `crypto_perp` | 加密永续合约 | 24/7 | USDT |
| `crypto_spot` | 加密现货 | 24/7 | USDT |
| `rwa_stock` | 代币化美股 | 美股交易时段 | USD |
| `metal` | 贵金属（代币+现货） | 24/7（代币）/ 交易时段（现货） | USD |
| `commodity` | 大宗商品期货 | 交易时段 | USD |
| `a_stock` | A 股 | A 股交易时段 | CNY |

---

## 统一返回格式

所有资产共享基础字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | string | 统一 Symbol |
| datetime | string | ISO 8601 UTC |
| open | float | 开盘价（USD/USDT） |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume_usd | float | 成交额（USD） |
| asset_type | string | 资产类型 |

### 永续合约额外字段

| 字段 | 说明 |
|------|------|
| mark_price | 标记价格 |
| index_price | 指数价格 |
| funding_rate | 当期资金费率 |
| open_interest_usd | 持仓量（USDT） |
| long_short_ratio | 多空人数比 |

---

## 永续合约数据规格

### K 线数据

| 项目 | 要求 |
|------|------|
| 数据源 | Binance Futures API（主）+ OKX API（辅） |
| 时间粒度 | `1m` / `5m` / `15m` / `1h` / `4h` / `1d` |
| 历史深度 | 日线 >= 3 年（2023 至今）；分钟线 >= 1 年 |
| 更新频率 | 日线 T+0；分钟线实时或准实时 |
| 字段 | open / high / low / close / volume / volume_usd / trade_count |

### 资金费率数据

| 项目 | 要求 |
|------|------|
| 数据源 | Binance / OKX / Hyperliquid |
| 粒度 | 每 8 小时一条 |
| 历史深度 | >= 3 年 |
| 字段 | funding_rate / funding_time / mark_price / index_price |
| 方向约定 | 正值 → 多头付空头；负值 → 空头付多头 |

### 持仓量数据

| 项目 | 要求 |
|------|------|
| 粒度 | `5m` / `1h` / `4h` / `1d` |
| 历史深度 | >= 2 年 |
| 字段 | open_interest（张）/ open_interest_usd / long_short_ratio / top_trader_long_ratio |

### 爆仓数据（P1）

| 项目 | 要求 |
|------|------|
| 粒度 | `1h` / `4h` / `1d` |
| 字段 | long_liquidation_usd / short_liquidation_usd / total_liquidation_usd |

---

## 支持的永续合约列表

第一期支持 30 个永续合约：

| 分类 | 合约 |
|------|------|
| 主流币 | BTC-USDT-PERP, ETH-USDT-PERP, SOL-USDT-PERP, BNB-USDT-PERP, XRP-USDT-PERP |
| Layer1 | ADA-USDT-PERP, AVAX-USDT-PERP, DOT-USDT-PERP, ATOM-USDT-PERP, SUI-USDT-PERP |
| Layer2 | ARB-USDT-PERP, OP-USDT-PERP, MATIC-USDT-PERP |
| DeFi | UNI-USDT-PERP, AAVE-USDT-PERP, LINK-USDT-PERP, MKR-USDT-PERP |
| Meme | DOGE-USDT-PERP, SHIB-USDT-PERP, PEPE-USDT-PERP, WIF-USDT-PERP |
| AI 概念 | FET-USDT-PERP, RENDER-USDT-PERP, TAO-USDT-PERP |
| 其他 | LTC-USDT-PERP, ETC-USDT-PERP, FIL-USDT-PERP, APT-USDT-PERP, INJ-USDT-PERP, TIA-USDT-PERP |

---

## 跨资产组合

### 时间对齐规则

- Crypto 24/7 与美股交易时段需合理对齐
- 非交易时段使用最近收盘价填充（forward fill）
- 组合回测统一以 UTC 时间戳对齐

### 统一计价

- 全部以 USD / USDT 计价
- 人民币资产按当日汇率折算

### 保证金隔离

- 合约仓位和现货仓位的保证金/资金分开核算
- 支持按比例分配初始资金到不同子策略
