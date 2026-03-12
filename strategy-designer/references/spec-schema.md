# StrategySpec 字段详解

> 本文档对 StrategySpec 每个字段进行详细说明，包括有效值、取值范围、使用示例和注意事项。

---

## 基础信息字段

### `strategy_id`
- **类型**：`string`
- **格式**：`strat_<uuid4>`
- **说明**：策略的全局唯一标识符，创建时由系统自动生成。不可修改。
- **示例**：`"strat_a1b2c3d4-e5f6-7890-abcd-ef1234567890"`

### `version`
- **类型**：`string`
- **格式**：语义化版本号 `vX.Y`
- **说明**：每次修改策略时版本号递增。主版本号（X）在重大逻辑变更时递增，次版本号（Y）在参数微调时递增。
- **示例**：`"v1.0"` → `"v1.1"`（参数调整）→ `"v2.0"`（逻辑重构）

### `name`
- **类型**：`string`
- **说明**：策略的人类可读名称，应简洁清晰地反映策略核心逻辑。
- **示例**：
  - `"BTC 1h 均线趋势突破"`
  - `"ETH 4h RSI 均值回归"`
  - `"BTC-ETH 资金费率套利"`

### `description`
- **类型**：`string`
- **说明**：策略的详细描述，包括核心思路、适用市场环境、预期表现等。
- **示例**：`"基于 20/60 周期 SMA 交叉的趋势跟踪策略，配合成交量过滤假突破。适用于 BTC 的趋势行情，震荡行情中可能频繁止损。"`

### `author`
- **类型**：`string`
- **说明**：策略创建者标识。
- **示例**：`"user_123"` 或 `"strategy-designer-agent"`

### `created_at` / `updated_at`
- **类型**：`string (ISO8601)`
- **说明**：创建和最后更新时间，由系统自动管理。
- **示例**：`"2026-03-12T14:30:00Z"`

---

## 市场与标的

### `market`
- **类型**：`string`
- **有效值**：

| 值 | 说明 | 典型标的 |
|----|------|---------|
| `crypto` | 加密货币（永续合约与现货） | BTCUSDT, ETHUSDT, SOLUSDT |
| `rwa_stock` | RWA 代币化股票 | TSLA, AAPL（代币化） |
| `metal` | 贵金属代币 | XAUUSDT（黄金）, XAGUSDT（白银） |
| `commodity` | 商品代币 | 原油、天然气代币 |
| `defi` | DeFi 协议代币 | UNI, AAVE, COMP |

### `venue`
- **类型**：`string[]`
- **有效值**：

| 值 | 说明 |
|----|------|
| `binance_futures` | 币安 U 本位永续合约 |
| `binance_spot` | 币安现货 |
| `okx_futures` | OKX 永续合约 |
| `bybit_futures` | Bybit 永续合约 |
| `dex_uniswap` | Uniswap DEX |
| `dex_gmx` | GMX 去中心化永续 |

- **说明**：可指定多个交易所进行跨所策略。大多数策略只需指定一个。

### `universe`
- **类型**：`string[]`
- **说明**：交易标的列表。格式为交易对符号。
- **示例**：
  - 单标的：`["BTCUSDT"]`
  - 多标的：`["BTCUSDT", "ETHUSDT", "SOLUSDT"]`
  - 跨资产：`["BTCUSDT", "XAUUSDT"]`

### `timeframe`
- **类型**：`string`
- **有效值**：

| 值 | 说明 | 适用场景 |
|----|------|---------|
| `1m` | 1 分钟 | 高频/超短线策略 |
| `5m` | 5 分钟 | 短线策略 |
| `15m` | 15 分钟 | 日内策略 |
| `30m` | 30 分钟 | 日内策略 |
| `1h` | 1 小时 | 中短线策略（最常用） |
| `4h` | 4 小时 | 波段策略 |
| `1d` | 1 天 | 趋势策略 |
| `1w` | 1 周 | 长期趋势策略 |

- **选择建议**：
  - 均线交叉策略推荐 `1h` 或 `4h`
  - 动量策略推荐 `15m` 或 `1h`
  - 均值回归策略推荐 `1h` 或 `4h`
  - 资金费率套利推荐 `1h`（资金费率通常 8 小时结算一次）

### `direction`
- **类型**：`string`
- **有效值**：

| 值 | 说明 | 适用场景 |
|----|------|---------|
| `long_only` | 仅做多 | 看涨趋势、现货策略 |
| `short_only` | 仅做空 | 看跌趋势、对冲策略 |
| `long_short` | 多空双向 | 大多数永续合约策略 |

---

## 数据需求

### `data_requirements`

声明策略运行所需的数据类型。回测引擎和运行时监控据此获取数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| `ohlcv` | `boolean` | K 线数据（开盘、最高、最低、收盘、成交量）。几乎所有策略都需要。 |
| `funding_rate` | `boolean` | 永续合约资金费率。资金费率套利策略必需。 |
| `open_interest` | `boolean` | 持仓量数据。用于判断市场情绪和趋势强度。 |
| `onchain` | `boolean` | 链上数据（如巨鲸钱包变动、TVL、活跃地址数）。链上分析策略使用。 |
| `orderbook_depth` | `boolean` | 订单簿深度数据。用于流动性分析和微观结构策略。 |
| `custom_feeds` | `string[]` | 自定义数据源标识。用于接入非标数据。 |

---

## 特征/指标

### `features`

策略使用的技术指标和特征列表。每个 Feature 定义一个可计算的数值指标。

#### 支持的指标类型

**趋势指标**：

| 指标 | `indicator` 值 | 常用参数 | 说明 |
|------|---------------|---------|------|
| 简单移动平均线 | `SMA` | `{"period": 20}` | 最基础的趋势指标 |
| 指数移动平均线 | `EMA` | `{"period": 20}` | 对近期价格更敏感 |
| 加权移动平均线 | `WMA` | `{"period": 20}` | 线性加权 |
| MACD | `MACD` | `{"fast": 12, "slow": 26, "signal": 9}` | 趋势动量指标 |
| 抛物线转向 | `SAR` | `{"af": 0.02, "max_af": 0.2}` | 趋势反转点 |
| ADX | `ADX` | `{"period": 14}` | 趋势强度（不区分方向） |

**震荡指标**：

| 指标 | `indicator` 值 | 常用参数 | 说明 |
|------|---------------|---------|------|
| RSI | `RSI` | `{"period": 14}` | 相对强弱指标，0-100 |
| 随机震荡 | `Stochastic` | `{"k_period": 14, "d_period": 3}` | KD 指标 |
| CCI | `CCI` | `{"period": 20}` | 商品通道指标 |
| Williams %R | `WilliamsR` | `{"period": 14}` | 超买超卖指标 |

**波动率指标**：

| 指标 | `indicator` 值 | 常用参数 | 说明 |
|------|---------------|---------|------|
| 布林带 | `Bollinger` | `{"period": 20, "std_dev": 2}` | 价格波动通道 |
| ATR | `ATR` | `{"period": 14}` | 平均真实波幅 |
| 凯特纳通道 | `Keltner` | `{"period": 20, "atr_mult": 1.5}` | 基于 ATR 的通道 |

**成交量指标**：

| 指标 | `indicator` 值 | 常用参数 | 说明 |
|------|---------------|---------|------|
| 成交量 SMA | `VolumeSMA` | `{"period": 20}` | 成交量均线 |
| OBV | `OBV` | `{}` | 能量潮 |
| VWAP | `VWAP` | `{}` | 成交量加权平均价 |

**自定义特征**：

| 类型 | `type` 值 | 说明 |
|------|----------|------|
| 技术指标 | `technical` | 基于价格/成交量计算的指标 |
| 基本面 | `fundamental` | 基于基本面数据的特征（市值、TVL 等） |
| 链上数据 | `onchain` | 基于链上数据的特征（巨鲸持仓、活跃地址等） |
| 自定义 | `custom` | 用户自定义计算逻辑的特征 |

#### Feature 示例

```json
{
  "name": "sma_20",
  "type": "technical",
  "indicator": "SMA",
  "params": {"period": 20},
  "source": "close"
}
```

```json
{
  "name": "rsi_14",
  "type": "technical",
  "indicator": "RSI",
  "params": {"period": 14},
  "source": "close"
}
```

```json
{
  "name": "bb_upper",
  "type": "technical",
  "indicator": "Bollinger",
  "params": {"period": 20, "std_dev": 2, "output": "upper"},
  "source": "close"
}
```

---

## 入场/出场规则

### `entry_rules` / `exit_rules`

规则由条件表达式和动作组成。条件表达式引用 `features` 中定义的指标名称。

#### 条件表达式语法

| 运算符 | 说明 | 示例 |
|--------|------|------|
| `>` | 大于 | `close > sma_20` |
| `<` | 小于 | `rsi_14 < 30` |
| `>=` | 大于等于 | `volume >= vol_sma_20 * 1.5` |
| `<=` | 小于等于 | `close <= bb_lower` |
| `==` | 等于 | `macd_histogram == 0` |
| `cross_above` | 上穿 | `cross_above(sma_5, sma_20)` |
| `cross_below` | 下穿 | `cross_below(sma_5, sma_20)` |
| `AND` | 逻辑与 | `close > sma_20 AND volume > vol_sma_20` |
| `OR` | 逻辑或 | `rsi_14 > 70 OR close > bb_upper` |

#### 动作类型

**入场动作**：

| 值 | 说明 |
|----|------|
| `open_long` | 开多仓 |
| `open_short` | 开空仓 |

**出场动作**：

| 值 | 说明 |
|----|------|
| `close_long` | 平多仓 |
| `close_short` | 平空仓 |
| `close_all` | 平所有仓位 |

#### 规则示例

```json
{
  "id": "entry_long_1",
  "description": "收盘价上穿 20 日均线且成交量放大 1.5 倍",
  "condition": "cross_above(close, sma_20) AND volume > vol_sma_20 * 1.5",
  "action": "open_long",
  "priority": 0
}
```

```json
{
  "id": "exit_stop_loss",
  "description": "价格下跌 2% 止损",
  "condition": "unrealized_pnl_pct <= -0.02",
  "action": "close_all",
  "priority": 0
}
```

---

## 仓位管理

### `position_sizing`

#### 仓位模式（`mode`）

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| `fixed_size` | 固定金额。每笔交易使用固定 USDT 金额。 | 简单策略、初学者 |
| `fixed_pct` | 固定比例。每笔交易使用总资金的固定比例。 | 通用型策略 |
| `risk_based` | 基于风险。根据止损距离反算仓位大小，使每笔交易风险恒定。 | **推荐**——专业级风险管理 |
| `kelly` | 凯利公式。根据历史胜率和盈亏比计算最优仓位。 | 有充分历史数据的策略 |
| `equal_weight` | 等权分配。多标的策略中每个标的分配相同资金。 | 组合策略 |

#### `risk_per_trade`
- **说明**：单笔交易的最大风险占总资金比例。
- **范围**：`0.001` ~ `0.05`（0.1% ~ 5%）
- **推荐**：`0.005`（0.5%）~ `0.02`（2%）
- **注意**：仅在 `mode = "risk_based"` 时有效。

#### `leverage`
- **说明**：杠杆倍数。
- **范围**：`1` ~ `125`（取决于交易所和标的）
- **推荐**：新手 ≤ 3x，有经验 ≤ 10x，专业 ≤ 20x
- **注意**：高杠杆显著增加爆仓风险。

#### `margin_mode`
- **说明**：保证金模式。
- **`isolated`（逐仓）**：每个仓位独立保证金，爆仓不影响其他仓位。**推荐**。
- **`cross`（全仓）**：所有仓位共享保证金，单个仓位亏损可能影响全部资金。

---

## 风险限制

### `risk_limits`

| 字段 | 推荐范围 | 说明 |
|------|---------|------|
| `max_position_pct` | 0.1 ~ 0.5 | 保守型 0.1，激进型 0.3-0.5 |
| `max_daily_loss` | 0.01 ~ 0.05 | 超过则当日停止交易 |
| `max_concurrent_positions` | 1 ~ 10 | 单标的策略通常为 1 |
| `max_drawdown` | 0.05 ~ 0.3 | 超过则暂停策略 |
| `stop_loss` | 0.01 ~ 0.1 | 固定止损比例，`null` 表示由规则控制 |
| `take_profit` | 0.02 ~ 0.5 | 固定止盈比例，`null` 表示由规则控制 |
| `trailing_stop` | 0.01 ~ 0.1 | 追踪止损回撤比例，`null` 表示不启用 |

---

## 执行约束

### `execution_constraints`

| 字段 | 说明 |
|------|------|
| `bar_close_only` | 设为 `true` 时仅在 K 线收盘时判断信号。避免回测中的未来数据偏差。**强烈推荐 `true`**。 |
| `order_type` | `market`（市价）成交快但有滑点；`limit`（限价）可控制价格但可能不成交。回测中推荐 `market`。 |
| `allow_pyramiding` | 设为 `true` 时允许在已有仓位的基础上追加同方向仓位。大多数策略设为 `false`。 |
| `slippage_bps` | 滑点估算基点数。BTC/ETH 等主流币推荐 5 bps，小币种推荐 10-20 bps。 |
| `fee_rate` | 单边手续费率。Binance Futures taker 费率为 0.0004（0.04%）。 |

---

## 状态字段

### `review_status`

| 值 | 说明 |
|----|------|
| `pending` | 待评审（初始状态） |
| `passed` | 评审通过 |
| `rejected` | 评审驳回 |

### `runtime_status`

| 值 | 说明 |
|----|------|
| `not_deployed` | 未部署（初始状态） |
| `deployed` | 已部署 |
| `running` | 运行中 |
| `stopped` | 已停止 |
| `error` | 运行异常 |

### `lifecycle_state`

完整状态定义请参考 `shared/schemas/lifecycle.md`。

---

## 元信息

### `metadata`

| 字段 | 说明 |
|------|------|
| `tags` | 策略标签，用于分类检索。如 `["trend", "btc", "momentum"]` |
| `notes` | 自由备注信息 |
| `source_conversation` | 来源对话 ID，便于追溯策略创建上下文 |
