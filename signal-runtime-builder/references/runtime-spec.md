# 信号运行时规范

> 本文档定义了信号计算的完整流程、状态管理、去重冷却机制、告警格式和崩溃恢复行为。

---

## 信号计算流程

### 主循环

每当一根 K 线收盘时，信号引擎执行以下流程：

```
┌─────────────────────┐
│  K 线收盘事件到达    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  获取最新数据         │  ← 从数据源拉取最新 OHLCV / 资金费率 / 持仓量等
│  （含足够的预热数据）  │     预热数据量 = warmup_bars（默认 50 根）
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  计算全部指标         │  ← 按 StrategySpec.features 逐个计算
│  （SMA/RSI/MACD...） │     保存指标值快照
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  检查入场/出场规则    │  ← 按 priority 排序，逐条检查
│  （匹配策略 rules）   │     优先级越小越先检查
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
  有触发       无触发
     │           │
     ▼           ▼
┌──────────┐ ┌──────────────────┐
│ 去重检查  │ │ 记录"未触发"日志   │
│          │ │ - 各规则条件值     │
│          │ │ - 哪些条件未满足   │
│          │ │ - 距离触发的距离   │
└────┬─────┘ └──────────────────┘
     │
  ┌──┴──┐
  │     │
  ▼     ▼
通过   被去重跳过
  │        │
  ▼        ▼
┌──────────┐ ┌────────────────┐
│ 冷却检查  │ │ 记录"去重跳过"  │
│          │ │ 日志           │
└────┬─────┘ └────────────────┘
     │
  ┌──┴──┐
  │     │
  ▼     ▼
通过   冷却中
  │        │
  ▼        ▼
┌────────────────┐ ┌────────────────┐
│ 生成 SignalEvent│ │ 记录"冷却中"   │
│ 发送告警通知    │ │ 跳过日志       │
│ 更新状态机      │ └────────────────┘
│ 持久化状态      │
└────────────────┘
```

### 数据获取

#### 必需数据

| 数据类型 | 获取方式 | 更新频率 | 说明 |
|---------|---------|---------|------|
| OHLCV | Binance REST/WebSocket | 每个 bar | 开高低收量 |
| 资金费率 | Binance REST | 每 8 小时 | 永续合约资金费率（如策略需要） |
| 持仓量 | Binance REST | 每个 bar | 未平仓合约量（如策略需要） |
| 订单簿深度 | Binance WebSocket | 实时 | 买卖盘口（如策略需要） |

#### 数据校验

每次获取数据后必须校验：

- 数据时间戳是否正确（不能有缺失或重复的 bar）
- OHLCV 数据是否完整（不能有 null 值）
- 数据量是否满足指标计算所需的最小长度
- 如果校验失败，记录错误日志并跳过本次计算（不生成信号）

---

## 指标计算规范

### 计算顺序

1. 基础指标（直接基于 OHLCV）优先计算
2. 衍生指标（基于其他指标的指标）按依赖顺序计算
3. 所有指标计算完成后，保存完整的指标值快照

### 指标缓存

- 维护滑动窗口缓存，避免每次重新计算全部历史
- 缓存大小 = max(所有指标所需最大回望长度) + 安全余量（默认 +50）
- 重启后从持久化状态恢复缓存，或重新获取足够长度的历史数据

---

## 去重规则

### 目的

防止在相似条件下生成大量重复信号。

### 规则

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `dedup_window` | 3 × timeframe | 同方向信号在此窗口内不重复触发 |
| `dedup_key` | `(symbol, signal_type)` | 去重的维度 |
| `allow_reverse` | `true` | 反方向信号不受去重限制 |

### 逻辑

```python
def should_dedup(new_signal, recent_signals, dedup_window):
    """
    检查新信号是否应被去重跳过
    """
    for recent in recent_signals:
        # 同标的、同方向的信号在去重窗口内不重复
        if (recent.symbol == new_signal.symbol
            and recent.signal_type == new_signal.signal_type
            and (new_signal.timestamp - recent.timestamp) < dedup_window):
            return True
    return False
```

---

## 冷却期配置

### 目的

在上一笔交易完成后，给策略一段"冷静期"，避免情绪化连续交易。

### 规则

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `cooldown_bars` | 2 × timeframe 的 bar 数 | 冷却期长度（以 bar 为单位） |
| `cooldown_trigger` | `exit_triggered` | 触发冷却的事件 |
| `cooldown_scope` | `per_symbol` | 冷却范围：按标的独立 |

### 逻辑

```python
def is_in_cooldown(symbol, last_exit_time, current_time, cooldown_bars, bar_duration):
    """
    检查指定标的是否处于冷却期
    """
    if last_exit_time is None:
        return False
    cooldown_duration = cooldown_bars * bar_duration
    return (current_time - last_exit_time) < cooldown_duration
```

---

## 告警消息格式

### 信号触发告警

```
📊 [策略名称] 信号触发
━━━━━━━━━━━━━━━━━━━━━
⏰ 时间: {timestamp}
📌 标的: {symbol}
📈 方向: {signal_type_cn} ({signal_type})
💰 当前价格: ${price_at_signal}
🎯 建议入场: ${suggested_price}
🛑 建议止损: ${stop_loss_price} ({stop_loss_pct}%)
✅ 建议止盈: ${take_profit_price} ({take_profit_pct}%)
📊 信号强度: {strength}
🔍 触发规则: {triggered_by}
📋 指标快照:
{feature_snapshot_formatted}
━━━━━━━━━━━━━━━━━━━━━
⚠️ 此为信号提示，非交易指令。执行需经 execution-guard 风控检查。
```

### 无信号日志格式

```
🔍 [策略名称] 本周期无信号
━━━━━━━━━━━━━━━━━━━━━
⏰ 时间: {timestamp}
📌 标的: {symbol}
📊 当前指标:
{feature_snapshot_formatted}
❌ 未满足条件:
{unmet_conditions}
📏 距离触发:
{distance_to_trigger}
━━━━━━━━━━━━━━━━━━━━━
```

### Signal Type 中文映射

| signal_type | 中文 |
|-------------|------|
| `entry_long` | 做多入场 |
| `entry_short` | 做空入场 |
| `exit_long` | 多仓平仓 |
| `exit_short` | 空仓平仓 |
| `exit_all` | 全部平仓 |
| `adjust_position` | 调整仓位 |

---

## "为什么没有信号" 解释能力

信号引擎必须能够回答"为什么这个 bar 没有产生信号"。实现方式：

### 对每条规则记录

1. **条件拆分**：将复合条件拆成原子条件
2. **逐条评估**：每个原子条件的当前值和目标值
3. **距离计算**：当前值距离触发条件还差多少

### 示例

```json
{
  "rule_id": "entry_long_1",
  "rule_description": "SMA20 上穿 SMA60 且成交量大于 20 日均量 1.5 倍",
  "overall_met": false,
  "conditions": [
    {
      "condition": "cross_above(sma_20, sma_60)",
      "met": false,
      "current_values": {"sma_20": 65100, "sma_60": 66200},
      "distance": "SMA20 需要再上涨 1100 (1.69%) 才能上穿 SMA60"
    },
    {
      "condition": "volume > vol_sma_20 * 1.5",
      "met": true,
      "current_values": {"volume": 15200, "vol_sma_20_x1.5": 12000},
      "distance": "已满足（当前量 15200 > 阈值 12000）"
    }
  ]
}
```

---

## 崩溃恢复

### 状态持久化

信号引擎必须定期持久化以下状态：

| 状态项 | 持久化频率 | 格式 |
|--------|----------|------|
| 当前状态机状态 | 每次状态变更 | JSON |
| 最近 N 个信号（去重用） | 每次信号生成 | JSON |
| 上次计算的 bar 时间戳 | 每个 bar | JSON |
| 指标缓存 | 每 10 个 bar | JSON |
| 冷却期状态 | 每次变更 | JSON |

### 重启行为

1. **加载持久化状态** → 恢复状态机、去重列表、冷却期
2. **检查遗漏 bar** → 计算上次记录的 bar 到当前 bar 之间的缺失数据
3. **补算指标** → 对遗漏的 bar 按顺序重新计算指标
4. **补发信号？** → 如果遗漏期间应该触发信号，标记为"延迟信号"并告警
5. **恢复正常循环** → 从下一个 bar 开始正常监控

### 延迟信号处理

- 如果重启后发现遗漏期间有信号，生成 SignalEvent 并标记 `metadata.delayed = true`
- 延迟信号的 TTL 自动缩短（原始 TTL × 0.5 或剩余有效时间，取较小值）
- 如果信号已过期（超过原始 TTL），不再发送，仅记录日志

---

## 多标的处理

当策略的 `universe` 包含多个交易对时：

1. **独立状态管理**：每个标的维护独立的状态机实例
2. **独立去重**：每个标的的去重窗口互不影响
3. **独立冷却**：每个标的的冷却期互相独立
4. **并行计算**：多标的的指标计算可以并行执行
5. **统一日志**：所有标的的日志写入同一个日志流，通过 `symbol` 字段区分

---

## 心跳机制

每处理 10 个 bar，输出一条心跳日志：

```json
{
  "type": "heartbeat",
  "timestamp": "2026-03-12T14:00:00Z",
  "strategy_id": "strat_xxx",
  "symbols_monitored": ["BTCUSDT", "ETHUSDT"],
  "bars_processed": 150,
  "signals_generated": 3,
  "signals_deduped": 1,
  "current_states": {
    "BTCUSDT": "watching",
    "ETHUSDT": "cooldown"
  },
  "uptime_seconds": 54000,
  "errors_count": 0
}
```
