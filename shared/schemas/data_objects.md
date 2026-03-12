# 核心数据对象定义

> 本文档详细定义了 DEX-Skill 体系中 5 个核心数据对象的完整字段规范。所有 Skill 之间的数据流转均基于这些对象。

---

## 1. StrategySpec（策略定义）

策略的唯一结构化定义，是所有 Skill 协作的"单一数据源"。由 strategy-designer Skill 创建和维护。

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `strategy_id` | `string` | 是 | 自动生成 UUID | 策略唯一标识符，格式 `strat_<uuid4>` |
| `version` | `string` | 是 | `"v1.0"` | 语义化版本号，每次修改递增 |
| `name` | `string` | 是 | — | 策略名称，人类可读，如"BTC 均线趋势突破" |
| `description` | `string` | 否 | `""` | 策略的详细描述，包括核心逻辑和适用场景 |
| `author` | `string` | 否 | `""` | 策略作者标识 |
| `created_at` | `string (ISO8601)` | 是 | 自动填充 | 创建时间，格式 `2026-03-12T14:00:00Z` |
| `updated_at` | `string (ISO8601)` | 是 | 自动填充 | 最后更新时间 |
| `market` | `string` | 是 | `"crypto"` | 市场类型。可选值：`crypto`、`rwa_stock`、`metal`、`commodity`、`defi` |
| `venue` | `string[]` | 是 | `["binance_futures"]` | 交易所/场所列表。可选值：`binance_futures`、`binance_spot`、`okx_futures`、`bybit_futures`、`dex_uniswap`、`dex_gmx` |
| `universe` | `string[]` | 是 | — | 交易标的列表，如 `["BTCUSDT", "ETHUSDT"]` |
| `timeframe` | `string` | 是 | `"1h"` | 主周期。可选值：`1m`、`5m`、`15m`、`30m`、`1h`、`4h`、`1d`、`1w` |
| `direction` | `string` | 是 | `"long_short"` | 方向限制。可选值：`long_only`、`short_only`、`long_short` |
| `data_requirements` | `DataRequirements` | 是 | 见下方 | 数据需求声明 |
| `features` | `Feature[]` | 是 | `[]` | 特征/指标列表，见下方 Feature 定义 |
| `entry_rules` | `Rule[]` | 是 | — | 入场规则列表 |
| `exit_rules` | `Rule[]` | 是 | — | 出场规则列表 |
| `position_sizing` | `PositionSizing` | 是 | 见下方 | 仓位管理配置 |
| `risk_limits` | `RiskLimits` | 是 | 见下方 | 风险限制配置 |
| `execution_constraints` | `ExecutionConstraints` | 是 | 见下方 | 执行约束配置 |
| `review_status` | `string` | 是 | `"pending"` | 评审状态。可选值：`pending`、`passed`、`rejected` |
| `runtime_status` | `string` | 是 | `"not_deployed"` | 运行时状态。可选值：`not_deployed`、`deployed`、`running`、`stopped`、`error` |
| `lifecycle_state` | `string` | 是 | `"draft"` | 生命周期状态，详见 `lifecycle.md` |
| `metadata` | `Metadata` | 否 | `{}` | 元信息 |

### DataRequirements 子对象

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `ohlcv` | `boolean` | 是 | `true` | 是否需要 K 线数据（开高低收量） |
| `funding_rate` | `boolean` | 是 | `false` | 是否需要永续合约资金费率 |
| `open_interest` | `boolean` | 是 | `false` | 是否需要持仓量数据 |
| `onchain` | `boolean` | 是 | `false` | 是否需要链上数据（如钱包活跃度、TVL） |
| `orderbook_depth` | `boolean` | 否 | `false` | 是否需要订单簿深度数据 |
| `custom_feeds` | `string[]` | 否 | `[]` | 自定义数据源标识列表 |

### Feature 子对象

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `name` | `string` | 是 | 特征名称，如 `"sma_20"`、`"rsi_14"` |
| `type` | `string` | 是 | 特征类型。可选值：`technical`（技术指标）、`fundamental`（基本面）、`onchain`（链上）、`custom`（自定义） |
| `indicator` | `string` | 是 | 指标名，如 `"SMA"`、`"RSI"`、`"MACD"`、`"Bollinger"` |
| `params` | `object` | 是 | 指标参数，如 `{"period": 20}` 或 `{"fast": 12, "slow": 26, "signal": 9}` |
| `source` | `string` | 否 | 数据来源字段，默认 `"close"`。可选值：`open`、`high`、`low`、`close`、`volume` |

### Rule 子对象（入场/出场规则）

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `id` | `string` | 是 | 规则唯一 ID，如 `"entry_1"`、`"exit_sl"` |
| `description` | `string` | 是 | 规则描述，如"收盘价上穿 SMA20 且成交量大于 20 日均量" |
| `condition` | `string` | 是 | 条件表达式，如 `"close > sma_20 AND volume > vol_sma_20"` |
| `action` | `string` | 是 | 动作。入场规则可选值：`open_long`、`open_short`；出场规则可选值：`close_long`、`close_short`、`close_all` |
| `priority` | `integer` | 否 | 规则优先级，数字越小优先级越高，默认 `0` |

### PositionSizing 子对象

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `mode` | `string` | 是 | `"risk_based"` | 仓位模式。可选值：`fixed_size`（固定金额）、`fixed_pct`（固定比例）、`risk_based`（基于风险）、`kelly`（凯利公式）、`equal_weight`（等权） |
| `risk_per_trade` | `number` | 是 | `0.005` | 单笔交易风险比例（占总资金），如 0.005 = 0.5% |
| `leverage` | `number` | 是 | `1` | 杠杆倍数，1 = 无杠杆 |
| `margin_mode` | `string` | 是 | `"isolated"` | 保证金模式。可选值：`isolated`（逐仓）、`cross`（全仓） |

### RiskLimits 子对象

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `max_position_pct` | `number` | 是 | `0.2` | 单个仓位最大占比（占总资金），0.2 = 20% |
| `max_daily_loss` | `number` | 是 | `0.02` | 单日最大亏损比例，0.02 = 2% |
| `max_concurrent_positions` | `integer` | 是 | `1` | 最大同时持仓数量 |
| `max_drawdown` | `number` | 否 | `0.1` | 最大回撤阈值，超过则触发暂停。0.1 = 10% |
| `stop_loss` | `number \| null` | 否 | `null` | 全局止损比例（基于入场价），如 0.02 = 2%。`null` 表示由规则控制 |
| `take_profit` | `number \| null` | 否 | `null` | 全局止盈比例（基于入场价），如 0.06 = 6%。`null` 表示由规则控制 |
| `trailing_stop` | `number \| null` | 否 | `null` | 追踪止损比例，如 0.03 = 3%。`null` 表示不启用 |

### ExecutionConstraints 子对象

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `bar_close_only` | `boolean` | 是 | `true` | 是否仅在 K 线收盘时执行（避免回测偏差） |
| `order_type` | `string` | 是 | `"market"` | 订单类型。可选值：`market`（市价）、`limit`（限价）、`stop_market`（止损市价） |
| `allow_pyramiding` | `boolean` | 是 | `false` | 是否允许加仓（同方向追加仓位） |
| `slippage_bps` | `number` | 否 | `5` | 滑点估算（基点），5 = 0.05% |
| `fee_rate` | `number` | 否 | `0.0004` | 手续费率（单边），0.0004 = 0.04% |

### Metadata 子对象

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `tags` | `string[]` | 否 | 策略标签，如 `["trend", "momentum", "btc"]` |
| `notes` | `string` | 否 | 自由备注 |
| `source_conversation` | `string` | 否 | 来源对话 ID，追溯策略创建上下文 |

---

## 2. BacktestConfig（回测配置）

回测引擎所需的完整配置，由 backtester Skill 根据 StrategySpec 生成。

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `backtest_id` | `string` | 是 | 自动生成 | 回测唯一标识，格式 `bt_<uuid4>` |
| `strategy_id` | `string` | 是 | — | 关联的策略 ID，引用 StrategySpec |
| `strategy_version` | `string` | 是 | — | 关联的策略版本号 |
| `start_date` | `string (ISO8601)` | 是 | — | 回测开始日期，如 `"2024-01-01"` |
| `end_date` | `string (ISO8601)` | 是 | — | 回测结束日期，如 `"2025-12-31"` |
| `initial_capital` | `number` | 是 | `10000` | 初始资金（USDT） |
| `benchmark` | `string` | 否 | `"BTCUSDT"` | 基准标的，用于对比收益 |
| `commission_rate` | `number` | 是 | `0.0004` | 手续费率（单边） |
| `slippage_model` | `string` | 是 | `"fixed_bps"` | 滑点模型。可选值：`fixed_bps`、`volume_pct`、`none` |
| `slippage_value` | `number` | 是 | `5` | 滑点数值（与模型配合使用） |
| `funding_rate_enabled` | `boolean` | 是 | `false` | 是否计入资金费率 |
| `funding_rate_interval` | `string` | 否 | `"8h"` | 资金费率结算周期 |
| `warmup_bars` | `integer` | 是 | `50` | 预热 K 线数量（指标计算所需） |
| `data_source` | `string` | 是 | `"binance_api"` | 数据来源。可选值：`binance_api`、`local_csv`、`coingecko` |
| `output_format` | `string` | 是 | `"full"` | 输出格式。可选值：`full`（完整）、`summary`（摘要）、`trades_only`（仅交易记录） |
| `created_at` | `string (ISO8601)` | 是 | 自动填充 | 配置创建时间 |

### BacktestResult 子对象（回测结果，嵌入或关联）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `total_return` | `number` | 总收益率，如 0.45 = 45% |
| `annual_return` | `number` | 年化收益率 |
| `sharpe_ratio` | `number` | 夏普比率 |
| `sortino_ratio` | `number` | 索提诺比率 |
| `max_drawdown` | `number` | 最大回撤 |
| `max_drawdown_duration` | `string` | 最大回撤持续时间 |
| `win_rate` | `number` | 胜率 |
| `profit_factor` | `number` | 盈亏比 |
| `total_trades` | `integer` | 总交易次数 |
| `avg_trade_return` | `number` | 平均每笔交易收益率 |
| `avg_holding_period` | `string` | 平均持仓时间 |
| `calmar_ratio` | `number` | 卡尔玛比率（年化收益/最大回撤） |
| `volatility` | `number` | 年化波动率 |
| `benchmark_return` | `number` | 基准收益率 |
| `alpha` | `number` | 超额收益 |
| `beta` | `number` | 市场贝塔 |
| `trade_log` | `TradeRecord[]` | 完整交易记录列表 |
| `equity_curve` | `EquityPoint[]` | 权益曲线数据点 |

### TradeRecord 子对象

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `trade_id` | `string` | 交易唯一 ID |
| `symbol` | `string` | 交易标的 |
| `direction` | `string` | 方向：`long` / `short` |
| `entry_time` | `string (ISO8601)` | 入场时间 |
| `entry_price` | `number` | 入场价格 |
| `exit_time` | `string (ISO8601)` | 出场时间 |
| `exit_price` | `number` | 出场价格 |
| `quantity` | `number` | 交易数量 |
| `pnl` | `number` | 盈亏金额（USDT） |
| `pnl_pct` | `number` | 盈亏比例 |
| `fee_paid` | `number` | 支付手续费 |
| `exit_reason` | `string` | 出场原因：`signal`、`stop_loss`、`take_profit`、`trailing_stop`、`timeout` |

---

## 3. ReviewReport（评审报告）

评审 Skill 对回测结果的分析报告，决定策略是否可进入下一阶段。

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `review_id` | `string` | 是 | 评审唯一标识，格式 `rev_<uuid4>` |
| `strategy_id` | `string` | 是 | 关联策略 ID |
| `backtest_id` | `string` | 是 | 关联回测 ID |
| `reviewer` | `string` | 是 | 评审者标识（Skill 名称或用户 ID） |
| `review_time` | `string (ISO8601)` | 是 | 评审时间 |
| `verdict` | `string` | 是 | 评审结论。可选值：`passed`（通过）、`rejected`（驳回）、`conditional`（有条件通过） |
| `score` | `number` | 是 | 综合评分（0-100） |
| `metric_checks` | `MetricCheck[]` | 是 | 各指标的逐项检查结果 |
| `risk_assessment` | `RiskAssessment` | 是 | 风险评估 |
| `recommendations` | `string[]` | 否 | 改进建议列表 |
| `rejection_reasons` | `string[]` | 否 | 驳回原因列表（仅 `rejected` 时填写） |
| `conditions` | `string[]` | 否 | 附加条件列表（仅 `conditional` 时填写） |
| `notes` | `string` | 否 | 评审备注 |

### MetricCheck 子对象

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `metric_name` | `string` | 指标名称，如 `"sharpe_ratio"`、`"max_drawdown"` |
| `actual_value` | `number` | 实际值 |
| `threshold` | `number` | 阈值（通过标准） |
| `operator` | `string` | 比较运算符：`>=`、`<=`、`>`、`<`、`==` |
| `passed` | `boolean` | 是否通过 |
| `weight` | `number` | 该指标在综合评分中的权重（0-1） |
| `comment` | `string` | 备注说明 |

### RiskAssessment 子对象

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `overfitting_risk` | `string` | 过拟合风险：`low`、`medium`、`high` |
| `liquidity_risk` | `string` | 流动性风险：`low`、`medium`、`high` |
| `concentration_risk` | `string` | 集中度风险：`low`、`medium`、`high` |
| `regime_sensitivity` | `string` | 市场状态敏感度：`low`、`medium`、`high` |
| `tail_risk` | `string` | 尾部风险：`low`、`medium`、`high` |
| `overall_risk_level` | `string` | 综合风险等级：`low`、`medium`、`high`、`critical` |
| `risk_notes` | `string` | 风险评估详细说明 |

---

## 4. SignalEvent（信号事件）

runtime-monitor Skill 生成的实时交易信号，是策略逻辑的实时输出。

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `signal_id` | `string` | 是 | 信号唯一标识，格式 `sig_<uuid4>` |
| `strategy_id` | `string` | 是 | 来源策略 ID |
| `timestamp` | `string (ISO8601)` | 是 | 信号生成时间 |
| `symbol` | `string` | 是 | 交易标的，如 `"BTCUSDT"` |
| `timeframe` | `string` | 是 | 信号所属时间周期 |
| `signal_type` | `string` | 是 | 信号类型。可选值：`entry_long`、`entry_short`、`exit_long`、`exit_short`、`exit_all`、`adjust_position` |
| `strength` | `number` | 是 | 信号强度（0-1），1 = 最强 |
| `price_at_signal` | `number` | 是 | 信号触发时的当前价格 |
| `triggered_by` | `string[]` | 是 | 触发该信号的规则 ID 列表，如 `["entry_1", "entry_2"]` |
| `feature_snapshot` | `object` | 是 | 信号触发时的特征值快照，如 `{"sma_20": 65432.1, "rsi_14": 72.5}` |
| `suggested_quantity` | `number` | 否 | 建议交易数量（由仓位管理模块计算） |
| `suggested_price` | `number` | 否 | 建议价格（限价单时使用） |
| `stop_loss_price` | `number` | 否 | 建议止损价 |
| `take_profit_price` | `number` | 否 | 建议止盈价 |
| `confidence` | `number` | 否 | 信号置信度（0-1），综合多个因子的置信度 |
| `ttl_seconds` | `integer` | 否 | 信号有效期（秒），过期作废。默认为一个 bar 的时间长度 |
| `metadata` | `object` | 否 | 附加信息 |

---

## 5. ExecutionDecision（执行决策）

executor Skill 接收 SignalEvent 后做出的执行决策，是信号到订单的桥梁。

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `decision_id` | `string` | 是 | 决策唯一标识，格式 `dec_<uuid4>` |
| `signal_id` | `string` | 是 | 关联的信号 ID |
| `strategy_id` | `string` | 是 | 关联的策略 ID |
| `timestamp` | `string (ISO8601)` | 是 | 决策时间 |
| `action` | `string` | 是 | 执行动作。可选值：`execute`（执行）、`reject`（拒绝）、`defer`（延迟）、`modify`（修改后执行） |
| `rejection_reason` | `string` | 否 | 拒绝原因（仅 `reject` 时填写）。常见值：`risk_limit_exceeded`、`insufficient_margin`、`signal_expired`、`manual_override`、`duplicate_signal` |
| `order_params` | `OrderParams` | 否 | 订单参数（仅 `execute` 或 `modify` 时填写） |
| `risk_check_results` | `RiskCheckResult[]` | 是 | 风控检查结果列表 |
| `position_before` | `PositionSnapshot` | 否 | 执行前的持仓快照 |
| `position_after` | `PositionSnapshot` | 否 | 执行后的持仓快照（预估） |
| `execution_mode` | `string` | 是 | 执行模式。可选值：`paper`（模拟）、`live`（实盘） |
| `requires_confirmation` | `boolean` | 是 | 是否需要用户确认才能执行 |
| `notes` | `string` | 否 | 决策备注 |

### OrderParams 子对象

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `symbol` | `string` | 交易标的 |
| `side` | `string` | 方向：`buy`、`sell` |
| `order_type` | `string` | 订单类型：`market`、`limit`、`stop_market` |
| `quantity` | `number` | 交易数量 |
| `price` | `number \| null` | 限价价格（市价单为 `null`） |
| `stop_price` | `number \| null` | 止损触发价（止损单使用） |
| `leverage` | `number` | 杠杆倍数 |
| `margin_mode` | `string` | 保证金模式：`isolated`、`cross` |
| `reduce_only` | `boolean` | 是否为仅减仓单 |
| `time_in_force` | `string` | 有效期：`GTC`（撤销前有效）、`IOC`（立即成交或取消）、`FOK`（全部成交或取消） |

### RiskCheckResult 子对象

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `check_name` | `string` | 检查项名称，如 `"max_position_check"`、`"daily_loss_check"` |
| `passed` | `boolean` | 是否通过 |
| `current_value` | `number` | 当前值 |
| `limit_value` | `number` | 限制值 |
| `message` | `string` | 检查说明 |

### PositionSnapshot 子对象

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `symbol` | `string` | 交易标的 |
| `direction` | `string` | 方向：`long`、`short`、`flat` |
| `quantity` | `number` | 持仓数量 |
| `entry_price` | `number` | 平均入场价 |
| `unrealized_pnl` | `number` | 未实现盈亏 |
| `margin_used` | `number` | 已用保证金 |
| `leverage` | `number` | 当前杠杆 |
| `liquidation_price` | `number` | 强平价格 |

---

## 数据流转关系

```
用户意图
    │
    ▼
┌──────────────────┐
│  StrategySpec     │ ← strategy-designer 创建
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  BacktestConfig   │ ← backtester 根据 StrategySpec 生成
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  BacktestResult   │ ← backtester 执行回测后输出
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  ReviewReport     │ ← reviewer 评审回测结果
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  SignalEvent      │ ← runtime-monitor 实时生成
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  ExecutionDecision│ ← executor 做出执行决策
└──────────────────┘
```

---

## ID 命名规范

| 对象 | ID 前缀 | 示例 |
|------|---------|------|
| StrategySpec | `strat_` | `strat_a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| BacktestConfig | `bt_` | `bt_11223344-5566-7788-99aa-bbccddeeff00` |
| ReviewReport | `rev_` | `rev_aabbccdd-1122-3344-5566-778899001122` |
| SignalEvent | `sig_` | `sig_deadbeef-cafe-babe-face-123456789abc` |
| ExecutionDecision | `dec_` | `dec_01020304-0506-0708-090a-0b0c0d0e0f10` |
