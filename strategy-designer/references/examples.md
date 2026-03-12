# 策略示例

> 本文档提供 5 个典型策略示例，展示从用户自然语言输入到 StrategySpec JSON 输出的完整转换过程。

---

## 示例 1：BTC 1h 趋势突破 + 成交量过滤

### 用户输入

> "帮我做一个 BTC 的趋势突破策略，1 小时周期，用 20 和 60 均线交叉做信号，要求成交量大于 20 日均量的 1.5 倍才入场。止损 2%，止盈 6%，杠杆 3 倍，只做永续。"

### 生成的 StrategySpec

```json
{
  "strategy_id": "strat_f1a2b3c4-d5e6-7890-abcd-ef1234567001",
  "version": "v1.0",
  "name": "BTC 1h 均线趋势突破（量价确认）",
  "description": "基于 SMA20/SMA60 交叉的趋势跟踪策略，配合成交量过滤假突破信号。当短周期均线上穿长周期均线且成交量放大时做多，下穿时做空。",
  "author": "",
  "created_at": "2026-03-12T14:00:00Z",
  "updated_at": "2026-03-12T14:00:00Z",
  "market": "crypto",
  "venue": ["binance_futures"],
  "universe": ["BTCUSDT"],
  "timeframe": "1h",
  "direction": "long_short",
  "data_requirements": {
    "ohlcv": true,
    "funding_rate": false,
    "open_interest": false,
    "onchain": false,
    "orderbook_depth": false,
    "custom_feeds": []
  },
  "features": [
    {
      "name": "sma_20",
      "type": "technical",
      "indicator": "SMA",
      "params": {"period": 20},
      "source": "close"
    },
    {
      "name": "sma_60",
      "type": "technical",
      "indicator": "SMA",
      "params": {"period": 60},
      "source": "close"
    },
    {
      "name": "vol_sma_20",
      "type": "technical",
      "indicator": "VolumeSMA",
      "params": {"period": 20},
      "source": "volume"
    }
  ],
  "entry_rules": [
    {
      "id": "entry_long_1",
      "description": "SMA20 上穿 SMA60 且成交量大于 20 日均量的 1.5 倍时做多",
      "condition": "cross_above(sma_20, sma_60) AND volume > vol_sma_20 * 1.5",
      "action": "open_long",
      "priority": 0
    },
    {
      "id": "entry_short_1",
      "description": "SMA20 下穿 SMA60 且成交量大于 20 日均量的 1.5 倍时做空",
      "condition": "cross_below(sma_20, sma_60) AND volume > vol_sma_20 * 1.5",
      "action": "open_short",
      "priority": 0
    }
  ],
  "exit_rules": [
    {
      "id": "exit_sl",
      "description": "止损 2%",
      "condition": "unrealized_pnl_pct <= -0.02",
      "action": "close_all",
      "priority": 0
    },
    {
      "id": "exit_tp",
      "description": "止盈 6%",
      "condition": "unrealized_pnl_pct >= 0.06",
      "action": "close_all",
      "priority": 1
    },
    {
      "id": "exit_reverse_long",
      "description": "持多仓时 SMA20 下穿 SMA60 则平仓",
      "condition": "position == long AND cross_below(sma_20, sma_60)",
      "action": "close_long",
      "priority": 2
    },
    {
      "id": "exit_reverse_short",
      "description": "持空仓时 SMA20 上穿 SMA60 则平仓",
      "condition": "position == short AND cross_above(sma_20, sma_60)",
      "action": "close_short",
      "priority": 2
    }
  ],
  "position_sizing": {
    "mode": "risk_based",
    "risk_per_trade": 0.01,
    "leverage": 3,
    "margin_mode": "isolated"
  },
  "risk_limits": {
    "max_position_pct": 0.3,
    "max_daily_loss": 0.03,
    "max_concurrent_positions": 1,
    "max_drawdown": 0.1,
    "stop_loss": 0.02,
    "take_profit": 0.06,
    "trailing_stop": null
  },
  "execution_constraints": {
    "bar_close_only": true,
    "order_type": "market",
    "allow_pyramiding": false,
    "slippage_bps": 5,
    "fee_rate": 0.0004
  },
  "review_status": "pending",
  "runtime_status": "not_deployed",
  "lifecycle_state": "draft",
  "metadata": {
    "tags": ["trend", "breakout", "sma", "volume", "btc"],
    "notes": "经典均线交叉策略，适用于趋势行情。震荡期可能频繁止损。",
    "source_conversation": ""
  }
}
```

---

## 示例 2：ETH 4h RSI 均值回归

### 用户输入

> "用 RSI 做 ETH 的均值回归策略，4 小时周期。RSI 低于 30 做多，高于 70 做空。同时用布林带确认——价格跌破下轨做多，突破上轨做空。杠杆 2 倍，止损 3%，回撤超 15% 暂停。"

### 生成的 StrategySpec

```json
{
  "strategy_id": "strat_f1a2b3c4-d5e6-7890-abcd-ef1234567002",
  "version": "v1.0",
  "name": "ETH 4h RSI+布林带均值回归",
  "description": "利用 RSI 超买超卖信号结合布林带通道确认的均值回归策略。当 RSI 进入超卖区且价格触及布林下轨时做多，反之做空。",
  "author": "",
  "created_at": "2026-03-12T14:00:00Z",
  "updated_at": "2026-03-12T14:00:00Z",
  "market": "crypto",
  "venue": ["binance_futures"],
  "universe": ["ETHUSDT"],
  "timeframe": "4h",
  "direction": "long_short",
  "data_requirements": {
    "ohlcv": true,
    "funding_rate": false,
    "open_interest": false,
    "onchain": false,
    "orderbook_depth": false,
    "custom_feeds": []
  },
  "features": [
    {
      "name": "rsi_14",
      "type": "technical",
      "indicator": "RSI",
      "params": {"period": 14},
      "source": "close"
    },
    {
      "name": "bb_upper",
      "type": "technical",
      "indicator": "Bollinger",
      "params": {"period": 20, "std_dev": 2, "output": "upper"},
      "source": "close"
    },
    {
      "name": "bb_lower",
      "type": "technical",
      "indicator": "Bollinger",
      "params": {"period": 20, "std_dev": 2, "output": "lower"},
      "source": "close"
    },
    {
      "name": "bb_mid",
      "type": "technical",
      "indicator": "Bollinger",
      "params": {"period": 20, "std_dev": 2, "output": "middle"},
      "source": "close"
    }
  ],
  "entry_rules": [
    {
      "id": "entry_long_1",
      "description": "RSI 低于 30 且价格跌破布林下轨时做多",
      "condition": "rsi_14 < 30 AND close <= bb_lower",
      "action": "open_long",
      "priority": 0
    },
    {
      "id": "entry_short_1",
      "description": "RSI 高于 70 且价格突破布林上轨时做空",
      "condition": "rsi_14 > 70 AND close >= bb_upper",
      "action": "open_short",
      "priority": 0
    }
  ],
  "exit_rules": [
    {
      "id": "exit_long_target",
      "description": "多仓价格回归布林中轨时平仓",
      "condition": "position == long AND close >= bb_mid",
      "action": "close_long",
      "priority": 1
    },
    {
      "id": "exit_short_target",
      "description": "空仓价格回归布林中轨时平仓",
      "condition": "position == short AND close <= bb_mid",
      "action": "close_short",
      "priority": 1
    },
    {
      "id": "exit_sl",
      "description": "止损 3%",
      "condition": "unrealized_pnl_pct <= -0.03",
      "action": "close_all",
      "priority": 0
    }
  ],
  "position_sizing": {
    "mode": "risk_based",
    "risk_per_trade": 0.01,
    "leverage": 2,
    "margin_mode": "isolated"
  },
  "risk_limits": {
    "max_position_pct": 0.25,
    "max_daily_loss": 0.03,
    "max_concurrent_positions": 1,
    "max_drawdown": 0.15,
    "stop_loss": 0.03,
    "take_profit": null,
    "trailing_stop": null
  },
  "execution_constraints": {
    "bar_close_only": true,
    "order_type": "market",
    "allow_pyramiding": false,
    "slippage_bps": 5,
    "fee_rate": 0.0004
  },
  "review_status": "pending",
  "runtime_status": "not_deployed",
  "lifecycle_state": "draft",
  "metadata": {
    "tags": ["mean_reversion", "rsi", "bollinger", "eth"],
    "notes": "均值回归策略在震荡行情中表现良好，趋势行情中可能连续止损。建议配合 ADX 过滤趋势强度。",
    "source_conversation": ""
  }
}
```

---

## 示例 3：资金费率套利

### 用户输入

> "我想做 BTC 的资金费率套利。当资金费率为正且高于 0.01% 时做空永续，同时做多现货对冲。资金费率转负时平仓。不要杠杆，风险要低。"

### 生成的 StrategySpec

```json
{
  "strategy_id": "strat_f1a2b3c4-d5e6-7890-abcd-ef1234567003",
  "version": "v1.0",
  "name": "BTC 资金费率正套利（永续空头+现货多头）",
  "description": "当永续合约资金费率持续为正时，做空永续、做多现货进行 delta 中性套利。持有期间赚取资金费率收入，资金费率转负时退出。",
  "author": "",
  "created_at": "2026-03-12T14:00:00Z",
  "updated_at": "2026-03-12T14:00:00Z",
  "market": "crypto",
  "venue": ["binance_futures", "binance_spot"],
  "universe": ["BTCUSDT"],
  "timeframe": "1h",
  "direction": "long_short",
  "data_requirements": {
    "ohlcv": true,
    "funding_rate": true,
    "open_interest": true,
    "onchain": false,
    "orderbook_depth": false,
    "custom_feeds": []
  },
  "features": [
    {
      "name": "funding_rate_current",
      "type": "fundamental",
      "indicator": "FundingRate",
      "params": {"lookback": 1},
      "source": "close"
    },
    {
      "name": "funding_rate_sma_24",
      "type": "fundamental",
      "indicator": "FundingRateSMA",
      "params": {"period": 24},
      "source": "close"
    }
  ],
  "entry_rules": [
    {
      "id": "entry_arb_1",
      "description": "当前资金费率 > 0.01% 且 24 小时均值 > 0.005% 时建仓：做空永续 + 做多现货",
      "condition": "funding_rate_current > 0.0001 AND funding_rate_sma_24 > 0.00005",
      "action": "open_short",
      "priority": 0
    }
  ],
  "exit_rules": [
    {
      "id": "exit_arb_1",
      "description": "资金费率转负时平仓退出",
      "condition": "funding_rate_current < 0",
      "action": "close_all",
      "priority": 0
    },
    {
      "id": "exit_arb_sl",
      "description": "基差偏离超过 1% 时止损（防止基差风险）",
      "condition": "unrealized_pnl_pct <= -0.01",
      "action": "close_all",
      "priority": 0
    }
  ],
  "position_sizing": {
    "mode": "fixed_pct",
    "risk_per_trade": 0.002,
    "leverage": 1,
    "margin_mode": "isolated"
  },
  "risk_limits": {
    "max_position_pct": 0.5,
    "max_daily_loss": 0.01,
    "max_concurrent_positions": 1,
    "max_drawdown": 0.05,
    "stop_loss": 0.01,
    "take_profit": null,
    "trailing_stop": null
  },
  "execution_constraints": {
    "bar_close_only": false,
    "order_type": "limit",
    "allow_pyramiding": false,
    "slippage_bps": 3,
    "fee_rate": 0.0004
  },
  "review_status": "pending",
  "runtime_status": "not_deployed",
  "lifecycle_state": "draft",
  "metadata": {
    "tags": ["arbitrage", "funding_rate", "delta_neutral", "btc", "low_risk"],
    "notes": "资金费率套利为低风险策略，年化收益取决于资金费率水平。需同时在现货和永续合约市场操作。需注意基差风险和资金费率突变风险。",
    "source_conversation": ""
  }
}
```

---

## 示例 4：BTC + 黄金跨资产组合

### 用户输入

> "我想做一个 BTC 和黄金代币的组合策略。BTC 用动量策略——涨幅超过 5 日均涨幅 2 倍时做多；黄金用趋势跟踪——价格在 50 日均线上方做多。两个标的等权分配，杠杆 2 倍，每日最大亏损 2%。日线级别。"

### 生成的 StrategySpec

```json
{
  "strategy_id": "strat_f1a2b3c4-d5e6-7890-abcd-ef1234567004",
  "version": "v1.0",
  "name": "BTC+黄金 跨资产动量趋势组合",
  "description": "BTC 使用短周期动量信号入场，黄金使用长周期趋势跟踪。两个标的等权分配资金，通过不同资产的低相关性分散风险。",
  "author": "",
  "created_at": "2026-03-12T14:00:00Z",
  "updated_at": "2026-03-12T14:00:00Z",
  "market": "crypto",
  "venue": ["binance_futures"],
  "universe": ["BTCUSDT", "XAUUSDT"],
  "timeframe": "1d",
  "direction": "long_only",
  "data_requirements": {
    "ohlcv": true,
    "funding_rate": false,
    "open_interest": false,
    "onchain": false,
    "orderbook_depth": false,
    "custom_feeds": []
  },
  "features": [
    {
      "name": "daily_return",
      "type": "technical",
      "indicator": "Return",
      "params": {"period": 1},
      "source": "close"
    },
    {
      "name": "avg_return_5d",
      "type": "technical",
      "indicator": "SMA",
      "params": {"period": 5, "input": "daily_return"},
      "source": "close"
    },
    {
      "name": "sma_50",
      "type": "technical",
      "indicator": "SMA",
      "params": {"period": 50},
      "source": "close"
    },
    {
      "name": "atr_14",
      "type": "technical",
      "indicator": "ATR",
      "params": {"period": 14},
      "source": "close"
    }
  ],
  "entry_rules": [
    {
      "id": "entry_btc_momentum",
      "description": "[BTC] 日涨幅超过 5 日均涨幅的 2 倍时做多",
      "condition": "symbol == BTCUSDT AND daily_return > avg_return_5d * 2 AND daily_return > 0",
      "action": "open_long",
      "priority": 0
    },
    {
      "id": "entry_gold_trend",
      "description": "[黄金] 价格在 50 日均线上方时做多",
      "condition": "symbol == XAUUSDT AND close > sma_50",
      "action": "open_long",
      "priority": 0
    }
  ],
  "exit_rules": [
    {
      "id": "exit_btc_momentum_fade",
      "description": "[BTC] 日涨幅回落至均值以下时平仓",
      "condition": "symbol == BTCUSDT AND position == long AND daily_return < avg_return_5d * 0.5",
      "action": "close_long",
      "priority": 1
    },
    {
      "id": "exit_gold_trend_break",
      "description": "[黄金] 价格跌破 50 日均线时平仓",
      "condition": "symbol == XAUUSDT AND position == long AND close < sma_50",
      "action": "close_long",
      "priority": 1
    },
    {
      "id": "exit_sl",
      "description": "ATR 止损：浮亏超过 2 倍 ATR 时止损",
      "condition": "unrealized_pnl <= -2 * atr_14",
      "action": "close_all",
      "priority": 0
    }
  ],
  "position_sizing": {
    "mode": "equal_weight",
    "risk_per_trade": 0.01,
    "leverage": 2,
    "margin_mode": "isolated"
  },
  "risk_limits": {
    "max_position_pct": 0.5,
    "max_daily_loss": 0.02,
    "max_concurrent_positions": 2,
    "max_drawdown": 0.12,
    "stop_loss": null,
    "take_profit": null,
    "trailing_stop": 0.05
  },
  "execution_constraints": {
    "bar_close_only": true,
    "order_type": "market",
    "allow_pyramiding": false,
    "slippage_bps": 5,
    "fee_rate": 0.0004
  },
  "review_status": "pending",
  "runtime_status": "not_deployed",
  "lifecycle_state": "draft",
  "metadata": {
    "tags": ["portfolio", "cross_asset", "momentum", "trend", "btc", "gold"],
    "notes": "跨资产组合策略利用 BTC 与黄金的低相关性分散风险。BTC 子策略适用于波动放大的行情，黄金子策略提供稳定趋势收益。",
    "source_conversation": ""
  }
}
```

---

## 示例 5：多指标组合策略

### 用户输入

> "做一个 SOL 的多指标策略，15 分钟周期。入场条件：MACD 金叉 + RSI 在 40-60 之间（非超买超卖区）+ ADX 大于 25（趋势明确）+ 价格在 EMA50 上方。出场用追踪止损 3% + 固定止盈 8%。5 倍杠杆，单笔风险 1%。"

### 生成的 StrategySpec

```json
{
  "strategy_id": "strat_f1a2b3c4-d5e6-7890-abcd-ef1234567005",
  "version": "v1.0",
  "name": "SOL 15m 多指标趋势确认",
  "description": "融合 MACD、RSI、ADX、EMA 四重指标确认的趋势策略。MACD 金叉提供方向信号，RSI 过滤超买超卖假信号，ADX 确认趋势强度，EMA 确认大方向。多重过滤提高入场质量。",
  "author": "",
  "created_at": "2026-03-12T14:00:00Z",
  "updated_at": "2026-03-12T14:00:00Z",
  "market": "crypto",
  "venue": ["binance_futures"],
  "universe": ["SOLUSDT"],
  "timeframe": "15m",
  "direction": "long_short",
  "data_requirements": {
    "ohlcv": true,
    "funding_rate": false,
    "open_interest": false,
    "onchain": false,
    "orderbook_depth": false,
    "custom_feeds": []
  },
  "features": [
    {
      "name": "macd_line",
      "type": "technical",
      "indicator": "MACD",
      "params": {"fast": 12, "slow": 26, "signal": 9, "output": "macd"},
      "source": "close"
    },
    {
      "name": "macd_signal",
      "type": "technical",
      "indicator": "MACD",
      "params": {"fast": 12, "slow": 26, "signal": 9, "output": "signal"},
      "source": "close"
    },
    {
      "name": "macd_histogram",
      "type": "technical",
      "indicator": "MACD",
      "params": {"fast": 12, "slow": 26, "signal": 9, "output": "histogram"},
      "source": "close"
    },
    {
      "name": "rsi_14",
      "type": "technical",
      "indicator": "RSI",
      "params": {"period": 14},
      "source": "close"
    },
    {
      "name": "adx_14",
      "type": "technical",
      "indicator": "ADX",
      "params": {"period": 14},
      "source": "close"
    },
    {
      "name": "ema_50",
      "type": "technical",
      "indicator": "EMA",
      "params": {"period": 50},
      "source": "close"
    }
  ],
  "entry_rules": [
    {
      "id": "entry_long_multi",
      "description": "MACD 金叉 + RSI 在 40-60 + ADX > 25 + 价格在 EMA50 上方 → 做多",
      "condition": "cross_above(macd_line, macd_signal) AND rsi_14 >= 40 AND rsi_14 <= 60 AND adx_14 > 25 AND close > ema_50",
      "action": "open_long",
      "priority": 0
    },
    {
      "id": "entry_short_multi",
      "description": "MACD 死叉 + RSI 在 40-60 + ADX > 25 + 价格在 EMA50 下方 → 做空",
      "condition": "cross_below(macd_line, macd_signal) AND rsi_14 >= 40 AND rsi_14 <= 60 AND adx_14 > 25 AND close < ema_50",
      "action": "open_short",
      "priority": 0
    }
  ],
  "exit_rules": [
    {
      "id": "exit_trailing_stop",
      "description": "追踪止损 3%",
      "condition": "trailing_drawdown >= 0.03",
      "action": "close_all",
      "priority": 0
    },
    {
      "id": "exit_take_profit",
      "description": "固定止盈 8%",
      "condition": "unrealized_pnl_pct >= 0.08",
      "action": "close_all",
      "priority": 0
    },
    {
      "id": "exit_trend_fade",
      "description": "ADX 跌破 20 表示趋势消失，平仓",
      "condition": "adx_14 < 20",
      "action": "close_all",
      "priority": 2
    }
  ],
  "position_sizing": {
    "mode": "risk_based",
    "risk_per_trade": 0.01,
    "leverage": 5,
    "margin_mode": "isolated"
  },
  "risk_limits": {
    "max_position_pct": 0.2,
    "max_daily_loss": 0.03,
    "max_concurrent_positions": 1,
    "max_drawdown": 0.1,
    "stop_loss": null,
    "take_profit": 0.08,
    "trailing_stop": 0.03
  },
  "execution_constraints": {
    "bar_close_only": true,
    "order_type": "market",
    "allow_pyramiding": false,
    "slippage_bps": 8,
    "fee_rate": 0.0004
  },
  "review_status": "pending",
  "runtime_status": "not_deployed",
  "lifecycle_state": "draft",
  "metadata": {
    "tags": ["multi_indicator", "macd", "rsi", "adx", "ema", "sol", "trend"],
    "notes": "多指标组合策略牺牲交易频率换取入场质量。四重确认条件较严格，信号较少但准确率预期较高。SOL 波动大，slippage 设为 8bps。",
    "source_conversation": ""
  }
}
```

---

## 各示例对比

| 特性 | 示例 1 | 示例 2 | 示例 3 | 示例 4 | 示例 5 |
|------|--------|--------|--------|--------|--------|
| 策略类型 | 趋势突破 | 均值回归 | 资金费率套利 | 跨资产组合 | 多指标组合 |
| 标的 | BTC | ETH | BTC | BTC+黄金 | SOL |
| 周期 | 1h | 4h | 1h | 1d | 15m |
| 杠杆 | 3x | 2x | 1x | 2x | 5x |
| 核心指标 | SMA+成交量 | RSI+布林带 | 资金费率 | 动量+SMA | MACD+RSI+ADX+EMA |
| 风险等级 | 中等 | 中等 | 低 | 中低 | 中高 |
| 数据需求 | OHLCV | OHLCV | OHLCV+FR+OI | OHLCV | OHLCV |
