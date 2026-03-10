# 端到端交互场景

## 目录

- [场景 1：BTC 永续单币种回测](#场景-1btc-永续单币种回测)
- [场景 2：资金费率套利策略](#场景-2资金费率套利策略)
- [场景 3：多合约对冲回测](#场景-3多合约对冲回测)
- [场景 4：跨资产组合回测](#场景-4跨资产组合回测)
- [场景 5：强平场景验证](#场景-5强平场景验证)
- [场景 6：错误处理](#场景-6错误处理)
- [场景 7：迭代优化流程](#场景-7迭代优化流程)

---

## 场景 1：BTC 永续单币种回测

**用户：** "帮我回测一个 BTC 永续合约均线策略，5 倍杠杆，过去一年"

```
步骤 1: client.get_exchange_info("BTC-USDT-PERP")
  → 确认 maintenance_margin_rate, tick_size, min_qty

步骤 2: client.get_perp_klines("BTC-USDT-PERP", "1d", "2025-03-10", "2026-03-10")
  → 拉取 365 条日线数据

步骤 3: client.get_funding_rate("BTC-USDT-PERP", "2025-03-10", "2026-03-10")
  → 拉取约 1095 条资金费率记录（每天 3 条）

步骤 4: Agent 编写策略代码
  基于 assets/templates/perpetual_ma_cross.py
  参数: fast_period=10, slow_period=30, leverage=5

步骤 5: 构建 BacktestEngine + BacktestConfig
  initial_capital=100000, default_leverage=5,
  margin_mode="isolated", enable_funding=True

步骤 6: 逐 bar 执行策略
  每个 bar: engine.on_bar() → 信号判断 → 开/平仓

步骤 7: engine.get_result()
  获取绩效指标 + 净值曲线 + 交易日志

步骤 8: Agent 生成分析
  "BTC 双均线策略过去一年表现:
   - 年化 45.2%, 夏普 1.85, 最大回撤 12.3%
   - 累计资金费率净支出 $2,340
   - 总手续费 $1,890, 0 次强平
   建议: 夏普接近 2, 策略有效"
```

---

## 场景 2：资金费率套利策略

**用户：** "BTC 永续资金费率套利策略，回溯半年"

```
步骤 1: client.get_perp_klines + client.get_funding_rate
  半年数据

步骤 2: Agent 分析资金费率分布
  平均 0.008%, 最大 0.15%, 最小 -0.05%

步骤 3: Agent 编写套利策略
  funding_rate > 0.05% → 做空永续
  funding_rate < -0.03% → 做多永续
  |funding_rate| < 0.015% → 平仓

步骤 4: BacktestEngine 执行
  enable_funding=True, leverage=1

步骤 5: 结果分析
  "资金费率套利半年表现:
   年化 32%, 夏普 2.1, 最大回撤 8%
   净资金费率收益 $4,200（核心收益来源）
   0 次强平"
```

---

## 场景 3：多合约对冲回测

**用户：** "同时做多 BTC 做空 ETH，对冲策略"

```
步骤 1: 分别拉取 BTC 和 ETH 的 K 线 + 资金费率

步骤 2: Agent 编写对冲策略
  BTC/ETH 价格比值均值回归

步骤 3: BacktestEngine 同时管理两个仓位
  逐仓模式: 保证金独立
  全仓模式: 保证金共享

步骤 4: 验证
  逐仓: 某仓位强平不影响另一仓位
```

---

## 场景 4：跨资产组合回测

**用户：** "BTC 永续 + PAXG 黄金 + 代币化 SPY"

```
步骤 1: 分别拉取数据
  client.get_perp_klines("BTC-USDT-PERP", ...)
  client.get_token_history("PAXG", days=365)
  # SPY: 需用 yfinance 等外部库（CoinGecko 不覆盖）

步骤 2: 时间对齐
  Crypto 24/7 vs 美股交易时段
  用 forward fill 填充非交易时段

步骤 3: 策略执行
  按 40%/30%/30% 分配，每 30 天再平衡

步骤 4: 报告
  各资产收益归因 + 相关性矩阵
```

---

## 场景 5：强平场景验证

**用户：** "50 倍杠杆 BTC 多单，包含极端行情"

```
步骤 1: 查合约信息确认 50x 可用

步骤 2: 选择包含大跌的区间（如 2024-08-05 黑色星期一）

步骤 3: engine = BacktestEngine(BacktestConfig(
    default_leverage=50, enable_liquidation=True
))

步骤 4: 验证
  开仓价 $60,000, 50x 杠杆, 维持保证金率 0.5%
  强平价 = $60,000 × (1 - 1/50 + 0.005) = $59,100
  BTC 下跌 1.5% 即触发强平

步骤 5: 结果
  trade_log 中有 action="liquidation" 记录
  liquidation_count > 0
  逐仓模式下其他仓位不受影响
```

---

## 场景 6：错误处理

### 6a. 数据拉取失败

```
client.get_perp_klines("FAKE-USDT-PERP", ...)
→ Binance 返回 400 Bad Request
→ Agent: "合约 FAKE-USDT-PERP 不存在"
→ 调用 client.list_perp_symbols() 展示可用列表
```

### 6b. 余额不足开仓

```
engine.open_long(qty=100, leverage=1)  # 需要远超余额的保证金
→ 引擎日志: "余额不足: 需要 X, 可用 Y"
→ Agent: "初始资金不足以开此仓位，建议减少数量或提高杠杆"
```

### 6c. Binance API 限流

```
大量请求触发 429
→ data_client 自动等待 Retry-After 后重试
→ Agent 无感
```

---

## 场景 7：迭代优化流程

```
第 1 轮: "BTC 均线策略 5x"
  → 年化 45%, 夏普 1.85, 回撤 12%

第 2 轮: "试试 10x"
  → Agent 修改 leverage=10 重新执行
  → 年化 78%, 但回撤 25%, 1 次强平
  → Agent: "回撤翻倍且出现强平, 建议降回 5x 或加止损"

第 3 轮: "保持 10x 加 3% 止损"
  → Agent 加 set_stop_loss(price * 0.97)
  → 年化 62%, 回撤 15%, 0 次强平
  → Agent: "止损有效, 夏普从 1.2 提升到 1.9"

第 4 轮: "加上 ETH 做对冲"
  → Agent 扩展为双币种
  → 年化 55%, 回撤 8%, 夏普 2.4
  → Agent: "对冲显著降低回撤, 推荐此方案"
```
