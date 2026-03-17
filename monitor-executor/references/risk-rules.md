# 风控规则详解

> 本文档详细定义了 execution-guard Skill 的 10 项风控检查规则。每条规则包含描述、检查逻辑、可配置参数和 pass/fail 示例。

---

## 1. 仓位上限检查

### 描述

确保单个仓位和所有仓位的总市值不超过账户资金的允许比例。防止过度集中风险。

### 检查逻辑

```python
def check_position_limit(new_order_value, current_positions, total_capital, config):
    """
    检查仓位上限
    """
    # 单仓位检查
    single_position_pct = new_order_value / total_capital
    if single_position_pct > config.max_position_pct:
        return Fail(f"单仓位占比 {single_position_pct:.1%} 超过上限 {config.max_position_pct:.1%}")

    # 总仓位检查
    total_position_value = sum(p.market_value for p in current_positions) + new_order_value
    total_position_pct = total_position_value / total_capital
    if total_position_pct > config.max_total_position_pct:
        return Fail(f"总仓位占比 {total_position_pct:.1%} 超过上限 {config.max_total_position_pct:.1%}")

    # 持仓数量检查
    if len(current_positions) >= config.max_concurrent_positions:
        return Fail(f"持仓数量 {len(current_positions)} 已达上限 {config.max_concurrent_positions}")

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_position_pct` | `float` | `0.2` | 单仓位最大占比（20%） |
| `max_total_position_pct` | `float` | `0.6` | 总仓位最大占比（60%） |
| `max_concurrent_positions` | `int` | `3` | 最大同时持仓数量 |

### 示例

**Pass**：账户 $10,000，新订单 $1,500（15%），当前持仓 $2,000（20%）。单仓 15% < 20% 上限 ✅，总仓 35% < 60% 上限 ✅。

**Fail**：账户 $10,000，新订单 $3,000（30%），当前持仓 $2,000（20%）。单仓 30% > 20% 上限 ❌。拒绝并建议将订单金额降至 $2,000 以下。

---

## 2. 日内亏损阈值检查

### 描述

监控当日已实现 + 未实现亏损是否超过每日最大允许亏损。防止单日爆亏。

### 检查逻辑

```python
def check_daily_loss(today_realized_pnl, unrealized_pnl, total_capital, config):
    """
    日内亏损阈值检查
    日切时间：UTC 00:00
    """
    total_daily_pnl = today_realized_pnl + min(unrealized_pnl, 0)  # 仅计入负未实现盈亏
    daily_loss_pct = abs(min(total_daily_pnl, 0)) / total_capital

    if daily_loss_pct >= config.max_daily_loss:
        return Fail(f"当日亏损 {daily_loss_pct:.2%} 已达上限 {config.max_daily_loss:.2%}，今日停止交易")

    # 接近阈值时警告
    if daily_loss_pct >= config.max_daily_loss * 0.8:
        return Warning(f"当日亏损 {daily_loss_pct:.2%} 接近上限 {config.max_daily_loss:.2%}")

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_daily_loss` | `float` | `0.02` | 每日最大亏损占比（2%） |
| `daily_reset_utc_hour` | `int` | `0` | 日切时间（UTC 小时） |
| `warning_threshold` | `float` | `0.8` | 接近上限时的警告阈值（80%） |

### 示例

**Pass**：账户 $10,000，当日已亏 $50（0.5%），上限 2%。0.5% < 2% ✅。

**Fail**：账户 $10,000，当日已亏 $180 + 未实现亏损 $30 = $210（2.1%），上限 2%。2.1% > 2% ❌。今日停止所有新开仓交易。

---

## 3. 重复下单防护

### 描述

防止同一信号被重复执行，或在短时间内对同一标的/同方向重复下单。

### 检查逻辑

```python
def check_duplicate(signal, recent_orders, config):
    """
    重复下单检查
    """
    # 同信号 ID 不可重复
    for order in recent_orders:
        if order.source_signal_id == signal.signal_id:
            return Fail(f"信号 {signal.signal_id} 已被执行过")

    # 同标的同方向去重
    for order in recent_orders:
        if (order.symbol == signal.symbol
            and order.direction == signal_direction(signal)
            and (now() - order.created_at).total_seconds() < config.dedup_window_seconds):
            return Fail(
                f"标的 {signal.symbol} 方向 {signal_direction(signal)} "
                f"在 {config.dedup_window_seconds}s 内已有订单"
            )

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `dedup_window_seconds` | `int` | `3600` | 去重窗口（秒） |
| `check_signal_id` | `bool` | `true` | 是否按 signal_id 去重 |
| `check_direction` | `bool` | `true` | 是否按标的+方向去重 |

### 示例

**Pass**：信号 sig_abc123 首次到达，最近无同标的同方向订单。✅

**Fail**：信号 sig_abc123 第二次到达（可能是网络重传），已被执行过。❌

---

## 4. 冷却期检查

### 描述

确保上一笔交易完成后经过足够的等待时间，避免情绪化/连续亏损交易。

### 检查逻辑

```python
def check_cooldown(symbol, last_trade_time, current_time, config):
    """
    冷却期检查
    """
    if last_trade_time is None:
        return Pass()

    elapsed = (current_time - last_trade_time).total_seconds()
    if elapsed < config.cooldown_seconds:
        remaining = config.cooldown_seconds - elapsed
        return Fail(f"冷却期中，距上次交易 {elapsed:.0f}s，需等待 {remaining:.0f}s")

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cooldown_seconds` | `int` | `7200` | 冷却期（秒），默认 2 小时 |
| `cooldown_scope` | `str` | `"per_symbol"` | 冷却范围：`per_symbol` / `global` |
| `cooldown_after_loss` | `int` | `null` | 亏损交易后的额外冷却期（秒） |

### 示例

**Pass**：上次交易 3 小时前完成，冷却期 2 小时。3h > 2h ✅。

**Fail**：上次交易 40 分钟前完成，冷却期 2 小时。40min < 2h ❌。还需等待 1 小时 20 分钟。

---

## 5. 交易所可用性检查

### 描述

确认目标交易所的 API 连接正常、交易对可交易、无系统维护。

### 检查逻辑

```python
def check_venue_health(venue, symbol, config):
    """
    交易所健康检查
    """
    # API 连通性
    if not venue.is_connected():
        return Fail("交易所 API 连接中断")

    # 交易对状态
    if not venue.is_tradable(symbol):
        return Fail(f"交易对 {symbol} 当前不可交易（可能暂停/退市）")

    # 系统维护
    if venue.is_maintenance():
        return Fail("交易所正在系统维护")

    # 延迟检查
    latency_ms = venue.ping()
    if latency_ms > config.max_latency_ms:
        return Fail(f"API 延迟 {latency_ms}ms 超过阈值 {config.max_latency_ms}ms")

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_latency_ms` | `int` | `5000` | 最大允许延迟（毫秒） |
| `health_check_interval` | `int` | `60` | 健康检查间隔（秒） |
| `retry_count` | `int` | `3` | 失败后重试次数 |

### 示例

**Pass**：Binance Futures API 正常连接，BTCUSDT 可交易，延迟 120ms。✅

**Fail**：Binance 正在进行系统升级维护（预计 30 分钟后恢复）。❌ 建议等待维护结束。

---

## 6. 账户余额检查

### 描述

确保账户有足够的可用保证金来支撑新订单，并保留安全余量。

### 检查逻辑

```python
def check_margin(signal, account, config):
    """
    保证金充足性检查
    """
    order_value = signal.price_at_signal * signal.suggested_quantity
    required_margin = order_value / config.leverage
    safety_buffer = account.total_balance * config.safety_margin_pct

    available = account.available_balance - safety_buffer
    if available < required_margin:
        return Fail(
            f"可用保证金不足：需要 ${required_margin:.2f}，"
            f"可用 ${available:.2f}（含安全余量 ${safety_buffer:.2f}）"
        )

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `safety_margin_pct` | `float` | `0.1` | 安全余量占比（保留 10% 不可用于开仓） |
| `min_available_usd` | `float` | `100` | 最低可用余额（美元） |

### 示例

**Pass**：账户余额 $10,000，安全余量 $1,000，可用 $9,000。新订单需保证金 $2,000。$9,000 > $2,000 ✅。

**Fail**：账户余额 $10,000，已用保证金 $8,500，安全余量 $1,000，可用 $500。新订单需保证金 $2,000。$500 < $2,000 ❌。

---

## 7. 杠杆限制检查

### 描述

确保订单使用的杠杆不超过策略定义和交易所允许的最大值。

### 检查逻辑

```python
def check_leverage(signal_leverage, strategy_max_leverage, venue_max_leverage, config):
    """
    杠杆限制检查
    """
    effective_max = min(strategy_max_leverage, venue_max_leverage, config.hard_max_leverage)

    if signal_leverage > effective_max:
        return Fail(
            f"杠杆 {signal_leverage}x 超过限制 {effective_max}x "
            f"（策略上限 {strategy_max_leverage}x，交易所上限 {venue_max_leverage}x）"
        )

    # 高杠杆警告
    if signal_leverage > config.leverage_warning_threshold:
        return Warning(f"杠杆 {signal_leverage}x 偏高，请注意爆仓风险")

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `hard_max_leverage` | `int` | `20` | 全局杠杆硬上限（无论策略如何设定） |
| `leverage_warning_threshold` | `int` | `10` | 超过此值发出高杠杆警告 |

### 示例

**Pass**：策略设定 3x 杠杆，交易所允许最大 125x，全局硬上限 20x。实际使用 3x ≤ min(3, 125, 20) = 3x ✅。

**Fail**：策略设定 5x，但全局硬上限 3x。5x > 3x ❌。需降低杠杆至 3x 以下。

---

## 8. 黑名单时段过滤

### 描述

在已知高风险时段（重大新闻发布、流动性极低时段等）禁止开仓交易。

### 检查逻辑

```python
def check_blackout(current_time_utc, config):
    """
    黑名单时段过滤
    """
    # 检查自定义黑名单
    for period in config.blackout_periods:
        if period.start <= current_time_utc <= period.end:
            return Fail(f"当前处于黑名单时段 {period.name}（{period.start} - {period.end}）")

    # 检查周期性低流动性时段
    hour = current_time_utc.hour
    weekday = current_time_utc.weekday()
    if weekday >= 5 and hour in config.weekend_low_liquidity_hours:
        return Warning("周末低流动性时段，滑点可能增大")

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `blackout_periods` | `list[Period]` | `[]` | 自定义黑名单时段列表 |
| `auto_blackout_events` | `bool` | `false` | 是否自动屏蔽重大事件时段 |
| `weekend_low_liquidity_hours` | `list[int]` | `[2,3,4,5]` | 周末低流动性 UTC 小时 |

### 示例

**Pass**：周二 14:00 UTC，无特殊事件，正常交易时段。✅

**Fail**：用户配置了"FOMC 利率决议发布"黑名单时段 2026-03-18 18:00-19:00 UTC。当前时间在此窗口内。❌

---

## 9. 相关性暴露检查

### 描述

防止在高度相关的资产上持有过度集中的同方向仓位，降低系统性风险。

### 检查逻辑

```python
def check_correlation_exposure(new_signal, current_positions, config):
    """
    相关性暴露检查
    """
    # 加密货币相关性分组
    correlation_groups = {
        "btc_ecosystem": ["BTCUSDT", "BCHUSDT", "LTCUSDT"],
        "eth_ecosystem": ["ETHUSDT", "MATICUSDT", "ARBUSDT", "OPUSDT"],
        "defi": ["UNIUSDT", "AAVEUSDT", "COMPUSDT", "MKRUSDT"],
        "meme": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT"],
    }

    new_group = find_group(new_signal.symbol, correlation_groups)
    if new_group is None:
        return Pass()

    # 计算同组暴露
    same_group_positions = [
        p for p in current_positions
        if find_group(p.symbol, correlation_groups) == new_group
    ]
    same_direction = [
        p for p in same_group_positions
        if p.direction == signal_direction(new_signal)
    ]

    if len(same_direction) >= config.max_correlated_positions:
        return Fail(
            f"相关性组 '{new_group}' 已有 {len(same_direction)} 个同方向仓位，"
            f"上限 {config.max_correlated_positions}"
        )

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_correlated_positions` | `int` | `2` | 同相关性组最大同方向仓位数 |
| `correlation_groups` | `dict` | 内置分组 | 自定义相关性分组 |
| `check_enabled` | `bool` | `true` | 是否启用相关性检查 |

### 示例

**Pass**：做多 BTCUSDT，无其他 BTC 生态持仓。✅

**Fail**：已做多 BTCUSDT 和 BCHUSDT（BTC 生态组已有 2 个同方向仓位）。新信号要求做多 LTCUSDT（同属 BTC 生态组）。❌ 建议先平掉一个已有仓位或等待不同方向信号。

---

## 10. Kill Switch / 熔断机制

### 描述

全局紧急停止机制。一旦激活，拒绝所有新订单。可手动激活/关闭，也可由系统自动触发。

### 自动触发条件

| 条件 | 触发阈值 | 说明 |
|------|---------|------|
| 账户净值回撤 | > max_drawdown | 账户净值从峰值下降超过阈值 |
| 连续亏损 | > N 笔连续亏损 | 防止策略失效时持续亏钱 |
| 异常波动 | 15 分钟涨跌 > 10% | 闪崩/暴涨等极端行情 |
| 系统异常 | 数据延迟 > 30 秒 | 数据源或系统故障 |

### 检查逻辑

```python
def is_kill_switch_active(kill_switch_state, account, config):
    """
    Kill switch 检查
    """
    # 手动激活
    if kill_switch_state.manually_activated:
        return Fail(
            f"Kill switch 已手动激活 | 激活者: {kill_switch_state.activated_by} | "
            f"时间: {kill_switch_state.activated_at} | 原因: {kill_switch_state.reason}"
        )

    # 自动触发：回撤检查
    drawdown = (account.peak_balance - account.current_balance) / account.peak_balance
    if drawdown > config.max_drawdown:
        activate_kill_switch(f"账户回撤 {drawdown:.2%} 超过阈值 {config.max_drawdown:.2%}")
        return Fail(f"Kill switch 自动触发：账户回撤 {drawdown:.2%}")

    # 自动触发：连续亏损
    if account.consecutive_losses >= config.max_consecutive_losses:
        activate_kill_switch(f"连续亏损 {account.consecutive_losses} 笔")
        return Fail(f"Kill switch 自动触发：连续亏损 {account.consecutive_losses} 笔")

    return Pass()
```

### 可配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_drawdown` | `float` | `0.1` | 自动触发回撤阈值（10%） |
| `max_consecutive_losses` | `int` | `5` | 连续亏损笔数阈值 |
| `extreme_volatility_pct` | `float` | `0.1` | 极端波动阈值（15 分钟内涨跌 > 10%） |
| `auto_deactivate_hours` | `int` | `null` | 自动关闭时间（小时），null = 需手动关闭 |

### Kill Switch 操作

| 操作 | 触发方式 | 效果 |
|------|---------|------|
| 激活 | 手动 / 自动 | 拒绝所有新开仓订单；允许减仓/平仓 |
| 关闭 | 仅手动 | 恢复正常交易 |
| 查询 | 随时 | 返回当前状态和历史记录 |

### 示例

**Pass**：Kill switch 未激活，账户回撤 5%（< 10% 阈值），无连续亏损。✅

**Fail（手动）**：用户执行了 `activate_kill_switch("休息一天")`。所有新订单被拒绝。❌

**Fail（自动）**：BTC 15 分钟内下跌 12%，触发极端波动熔断。❌ 等待市场稳定后手动关闭 kill switch。

---

## 风控检查优先级

检查按以下顺序执行，任一步骤失败即立即拒绝（不继续后续检查）：

| 优先级 | 检查项 | 原因 |
|--------|--------|------|
| 1 | Kill Switch | 最高级别安全机制，一票否决 |
| 2 | 信号有效性 | 无效信号无需后续检查 |
| 3 | 重复下单 | 快速排除重复 |
| 4 | 交易所可用性 | 交易所不可用则无法执行 |
| 5 | 黑名单时段 | 禁止时段内无需继续 |
| 6 | 日内亏损 | 当日超限则今日停止 |
| 7 | 冷却期 | 冷却中不接受新单 |
| 8 | 余额检查 | 余额不足无法执行 |
| 9 | 仓位上限 | 仓位达限拒绝 |
| 10 | 杠杆限制 | 杠杆超限调整 |
| 11 | 相关性暴露 | 最后检查暴露集中度 |
