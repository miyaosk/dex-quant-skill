# 订单规范

> 本文档定义了 execution-guard Skill 支持的订单类型、执行模式、订单计划格式、执行后状态写入和错误处理机制。

---

## 订单类型

### 市价单（Market Order）

| 属性 | 值 |
|------|---|
| `order_type` | `"market"` |
| 特点 | 以当前市场最优价格立即成交 |
| 优势 | 成交快、确定性高 |
| 劣势 | 有滑点、大单可能冲击市场 |
| 适用场景 | 大部分策略的默认选择；止损/止盈出场 |

### 限价单（Limit Order）

| 属性 | 值 |
|------|---|
| `order_type` | `"limit"` |
| 特点 | 以指定价格或更优价格成交 |
| 优势 | 无滑点、可控制成交价 |
| 劣势 | 可能不成交、需要管理挂单 |
| 适用场景 | 流动性较差的标的；对成本敏感的策略 |

### 限价单有效期类型

| 类型 | 代码 | 说明 |
|------|------|------|
| 撤销前有效 | `GTC` | 订单一直有效直到成交或手动撤销 |
| 立即成交或取消 | `IOC` | 立即尽量成交，未成交部分取消 |
| 全部成交或取消 | `FOK` | 全部成交或全部取消，不接受部分成交 |

---

## 执行模式

### 人工确认模式（Manual）

```
信号到达 → 风控检查 → 生成订单计划 → 展示给用户 → 等待用户确认 → 执行
                                                    │
                                              用户拒绝 → 记录并取消
```

**行为规则**：

- 每一笔订单都必须经过用户显式确认（输入 "确认执行" 或类似指令）
- 确认超时（默认 5 分钟）自动取消
- 展示完整的订单详情和风控检查结果
- 记录用户确认/拒绝的决定和时间

### 半自动模式（Semi-Auto）

```
信号到达 → 风控检查 → 判断风险等级
    │
    ├─ 低风险 → 自动执行 → 通知用户
    │
    └─ 高风险 → 生成订单计划 → 等待用户确认 → 执行
```

**低风险条件（全部满足才算低风险）**：

| 条件 | 阈值 |
|------|------|
| 订单金额 | ≤ 单笔上限的 50% |
| 当日亏损 | ≤ 日亏损上限的 50% |
| 订单类型 | 入场单 / 止损止盈出场（非手动平仓） |
| 用户最近确认 | 距上次确认 < 4 小时 |
| 杠杆 | ≤ 5x |

### 全自动模式（Auto）

```
信号到达 → 风控检查 → 通过 → 自动执行 → 通知用户
                    │
                    └─ 不通过 → 拒绝 → 通知用户
```

**行为规则**：

- 用户必须显式开启全自动模式（需二次确认）
- 通过风控的订单自动执行，无需等待确认
- 每次执行后向用户发送通知
- 保留 kill switch 紧急停止能力
- 每日首次交易仍需用户确认（安全机制）

---

## 订单计划格式

### OrderPlan 结构

```json
{
  "plan_id": "plan_<uuid4>",
  "signal_id": "sig_xxx",
  "strategy_id": "strat_xxx",
  "created_at": "2026-03-12T14:00:00Z",

  "orders": [
    {
      "order_id": "ord_<uuid4>",
      "sequence": 1,
      "symbol": "BTCUSDT",
      "side": "buy",
      "order_type": "market",
      "quantity": 0.015,
      "price": null,
      "stop_price": null,
      "leverage": 3,
      "margin_mode": "isolated",
      "reduce_only": false,
      "time_in_force": "GTC",
      "purpose": "entry"
    },
    {
      "order_id": "ord_<uuid4>",
      "sequence": 2,
      "symbol": "BTCUSDT",
      "side": "sell",
      "order_type": "stop_market",
      "quantity": 0.015,
      "price": null,
      "stop_price": 66083.85,
      "leverage": 3,
      "margin_mode": "isolated",
      "reduce_only": true,
      "time_in_force": "GTC",
      "purpose": "stop_loss"
    }
  ],

  "execution_mode": "manual",
  "requires_confirmation": true,
  "risk_check_summary": {
    "all_passed": true,
    "checks_count": 10,
    "warnings_count": 0,
    "detail": "全部 10 项风控检查通过"
  },

  "estimated_impact": {
    "estimated_margin_used": 335.54,
    "estimated_fee": 0.54,
    "new_position_pct": 15.0,
    "remaining_available": 8664.46
  }
}
```

### Order 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `order_id` | `string` | 订单唯一标识，格式 `ord_<uuid4>` |
| `sequence` | `int` | 执行顺序（1 = 先执行） |
| `symbol` | `string` | 交易对 |
| `side` | `string` | 方向：`buy` / `sell` |
| `order_type` | `string` | 订单类型：`market` / `limit` / `stop_market` |
| `quantity` | `float` | 交易数量（标的单位，如 BTC 个数） |
| `price` | `float / null` | 限价价格（市价单为 null） |
| `stop_price` | `float / null` | 止损触发价 |
| `leverage` | `int` | 杠杆倍数 |
| `margin_mode` | `string` | 保证金模式：`isolated` / `cross` |
| `reduce_only` | `bool` | 是否为仅减仓单 |
| `time_in_force` | `string` | 有效期：`GTC` / `IOC` / `FOK` |
| `purpose` | `string` | 订单目的：`entry` / `stop_loss` / `take_profit` / `exit_signal` |

---

## 执行后状态写入

### 写入时机

每笔订单执行完成后（成交确认），必须立即写入以下状态：

### 写入内容

```json
{
  "execution_record": {
    "record_id": "exec_<uuid4>",
    "order_id": "ord_xxx",
    "signal_id": "sig_xxx",
    "strategy_id": "strat_xxx",
    "timestamp": "2026-03-12T14:00:05Z",

    "execution_result": {
      "status": "filled",
      "filled_quantity": 0.015,
      "filled_price": 67435.20,
      "fee_paid": 0.54,
      "slippage_bps": 0.4
    },

    "position_after": {
      "symbol": "BTCUSDT",
      "direction": "long",
      "quantity": 0.015,
      "entry_price": 67435.20,
      "unrealized_pnl": 0.0,
      "margin_used": 337.18,
      "leverage": 3,
      "liquidation_price": 45290.13
    },

    "account_after": {
      "total_balance": 10000.00,
      "available_balance": 9662.28,
      "margin_used": 337.18,
      "unrealized_pnl": 0.0,
      "today_realized_pnl": 0.0
    }
  }
}
```

### 写入规则

| 规则 | 说明 |
|------|------|
| 先写后确认 | 状态写入成功后才能确认执行完成 |
| 写入失败回滚 | 如果状态写入失败，标记执行记录为 `write_failed` 并告警 |
| 原子性 | 订单执行和状态写入作为一个逻辑事务 |
| 幂等性 | 同一 `record_id` 多次写入不产生重复 |

---

## 错误处理与回滚

### 错误类型与处理

| 错误类型 | 处理方式 | 回滚操作 |
|---------|---------|---------|
| 风控检查失败 | 拒绝执行，返回原因 | 无需回滚 |
| 交易所下单失败 | 重试 3 次，仍失败则放弃 | 无需回滚（未成交） |
| 部分成交 | 记录已成交部分，取消剩余 | 根据策略决定是否保留部分仓位 |
| 状态写入失败 | 告警，标记为异常 | 不影响已执行订单，但暂停后续执行 |
| 网络超时 | 查询订单状态确认是否成交 | 根据实际状态决定处理方式 |
| 余额不足（执行时） | 取消订单 | 无需回滚 |

### 超时处理

| 场景 | 超时时间 | 处理 |
|------|---------|------|
| 用户确认等待 | 5 分钟 | 自动取消订单计划 |
| 交易所下单响应 | 10 秒 | 重试 |
| 成交确认等待 | 30 秒 | 查询订单状态 |
| 状态写入 | 5 秒 | 重试 3 次 |

---

## 审计日志

每个执行决策必须产生审计日志，用于事后追溯：

```json
{
  "audit_id": "aud_<uuid4>",
  "timestamp": "2026-03-12T14:00:00Z",
  "event_type": "execution_decision",
  "signal_id": "sig_xxx",
  "strategy_id": "strat_xxx",
  "decision": "execute",
  "risk_checks": {
    "position_limit": {"passed": true, "value": 0.15, "limit": 0.20},
    "daily_loss": {"passed": true, "value": 0.005, "limit": 0.02},
    "duplicate": {"passed": true},
    "cooldown": {"passed": true, "elapsed_s": 7500, "required_s": 7200},
    "venue_health": {"passed": true, "latency_ms": 120},
    "margin": {"passed": true, "available": 9000, "required": 2000},
    "leverage": {"passed": true, "actual": 3, "max": 20},
    "blackout": {"passed": true},
    "correlation": {"passed": true},
    "kill_switch": {"passed": true, "active": false}
  },
  "order_plan_id": "plan_xxx",
  "execution_mode": "manual",
  "user_confirmed": true,
  "confirmed_at": "2026-03-12T14:00:30Z"
}
```
