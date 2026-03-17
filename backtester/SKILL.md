---
name: backtester
description: >
  接收策略脚本生成的信号，调用 dex-quant-server 回测接口，
  Server 拉取 K 线数据（带缓存），用信号驱动引擎模拟交易，返回绩效报告和结论。
  Use when user asks to backtest a strategy, check historical performance,
  or evaluate if a strategy is profitable.
---

# Backtester — 回测

## 目标

接收 strategy-maker 生成的策略脚本，**本地运行脚本**产出信号列表，
然后将信号发送到 `dex-quant-server` 后端执行回测。

Server 负责拉取 K 线数据（带 MySQL 缓存，同币同周期不重复下载），
用信号驱动回测引擎模拟真实交易，返回绩效报告和上线建议。

**核心公式：**
```
策略脚本 → 本地跑出信号 → 调 Server API（发信号）→ Server 拉 K 线 + 回测 → 返回结果
```

---

## 触发条件

当用户表达以下意图时激活本 Skill：

- "帮我回测一下这个策略"
- "用 2024 年的数据跑一下看看"
- "这个策略去年能赚多少？"
- "回测结果怎么样？能上线吗？"
- "帮我测试 5 倍杠杆的效果"
- 任何涉及策略回测、历史验证、绩效分析的请求

---

## 输入

| 输入项 | 是否必须 | 说明 |
|--------|---------|------|
| 策略脚本 | **必须** | strategy-maker 生成的 `.py` 文件 |
| 回测时间范围 | **必须** | 起止日期（如 2024-01-01 ~ 2024-12-31） |
| K 线周期 | 可选 | 15m / 1h / 2h / 1d（默认 1h） |
| 初始资金 | 可选 | 默认 $100,000 |
| 杠杆 | 可选 | 默认 1x |
| 手续费率 | 可选 | 默认 Taker 0.05% |
| 滑点 | 可选 | 默认 5 bps |

---

## 输出

| 输出项 | 说明 |
|--------|------|
| **绩效指标** | 收益率、夏普、Sortino、最大回撤、胜率、盈亏比、Calmar |
| **交易记录** | 每笔交易的开仓/平仓详情、盈亏、原因 |
| **权益曲线** | 账户净值随时间的变化 |
| **评估结论** | 通过(approved) / 先模拟(paper_trade_first) / 驳回(rejected) |
| **信号统计** | 总信号数、已执行信号数 |

---

## 工作流程

### 第 1 步：运行策略脚本（本地）

1. 确认脚本文件存在且实现了 `generate_signals()` 接口
2. 以 backtest 模式运行：

```bash
python my_strategy.py backtest 2024-01-01 2024-12-31
```

3. 收集脚本输出的信号列表

### 第 2 步：调 Server 回测接口

将信号列表 + 配置发送到 `dex-quant-server`：

```python
from backtester.scripts.api_client import QuantAPIClient

client = QuantAPIClient("http://server-address:8000")
result = client.run_backtest(
    strategy_name="BTC MACD 策略",
    symbol="BTCUSDT",
    timeframe="1h",
    start_date="2024-01-01",
    end_date="2024-12-31",
    signals=signals,      # 策略脚本产出的信号列表
    leverage=3,
    initial_capital=100000,
)
```

### 第 3 步：Server 处理（自动）

Server 端自动完成：

1. **拉 K 线数据** — 支持 15m/1h/2h/1d，MySQL 缓存，同币同周期不重复下载
2. **信号驱动回测** — 逐根 K 线回放信号，模拟交易
3. **交易模拟** — 杠杆、保证金、手续费、滑点、资金费率、止损止盈、强平
4. **绩效计算** — Sharpe、Sortino、最大回撤、胜率、Calmar 等
5. **评估结论** — 综合指标给出三选一结论

### 第 4 步：展示结果

```python
client.print_metrics(result)     # 绩效报告
client.print_trades(result)      # 交易明细
client.print_conclusion(result)  # 结论和建议
```

### 第 5 步：迭代优化

用户根据结果调整策略 → 重新生成信号 → 再次回测 → 循环

---

## Server API（dex-quant-server）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/backtest/run` | 核心：接收信号 + 配置，执行回测 |
| GET | `/api/v1/backtest/{id}` | 查询已保存的回测结果 |
| GET | `/api/v1/backtest/{id}/trades` | 交易记录 |
| GET | `/api/v1/backtest/{id}/equity` | 权益曲线 |
| POST | `/api/v1/data/klines` | K 线数据（带缓存） |
| GET | `/api/v1/data/symbols` | 交易对列表 |
| POST | `/api/v1/strategies` | 保存策略 |
| GET | `/api/v1/strategies` | 策略列表 |
| POST | `/api/v1/signals/batch` | 批量保存信号 |
| POST | `/api/v1/signals/query` | 查询信号 |

### 回测请求格式

```json
{
  "strategy_name": "BTC MACD 策略",
  "strategy_id": "strat_abc123",
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "signals": [
    {
      "timestamp": "2024-01-15 08:00:00+00:00",
      "symbol": "BTCUSDT",
      "action": "buy",
      "direction": "long",
      "confidence": 0.85,
      "reason": "MACD 金叉 + RSI < 40",
      "price_at_signal": 42350.0,
      "suggested_stop_loss": 41500.0,
      "suggested_take_profit": 45000.0
    }
  ],
  "initial_capital": 100000,
  "leverage": 3,
  "fee_rate": 0.0005,
  "slippage_bps": 5.0,
  "margin_mode": "isolated",
  "direction": "long_short"
}
```

### 回测响应格式

```json
{
  "backtest_id": "bt_abc123def456",
  "strategy_id": "strat_abc123",
  "strategy_name": "BTC MACD 策略",
  "status": "completed",
  "conclusion": "approved",
  "metrics": {
    "total_return_pct": 0.156,
    "annual_return_pct": 0.178,
    "sharpe_ratio": 1.85,
    "max_drawdown_pct": -0.082,
    "win_rate": 0.55,
    "total_trades": 48,
    "total_signals": 52,
    "signals_executed": 48
  },
  "trades": [...],
  "equity_curve": [...]
}
```

---

## K 线数据缓存

Server 端实现了 MySQL 缓存机制：

| 特性 | 说明 |
|------|------|
| 支持周期 | 15m / 1h / 2h / 1d |
| 缓存策略 | 同币同周期同时间范围命中缓存则不重复下载 |
| 缓存有效期 | 加密货币 1h，股票/商品 6h |
| 数据源 | Binance 永续/现货 |

---

## 回测引擎能力

| 能力 | 说明 |
|------|------|
| 多空双向 | 做多做空均支持 |
| 杠杆 1x-125x | 模拟真实杠杆 |
| 逐仓保证金 | 按仓位隔离 |
| 资金费率 | 8h 结算（永续合约） |
| 止损/止盈 | 按 bar 内高低价判断 |
| 强制平仓 | 保证金不足时爆仓 |
| 手续费 | Taker 0.05% / Maker 0.02% |
| 滑点 | 可配置 bps |

---

## 评估结论标准

| 结论 | 条件 |
|------|------|
| **通过** | 收益 > 10%，夏普 > 1.5，回撤 < 10%，胜率 > 40%，交易 ≥ 30 笔 |
| **先模拟** | 部分指标达标，但不够全面 |
| **驳回** | 亏损 > 10%，或有爆仓，或交易 < 5 笔 |

---

## 可用工具

### API 客户端 — api_client.py

位置：`backtester/scripts/api_client.py`

| 方法 | 说明 |
|------|------|
| `run_backtest()` | 提交信号驱动回测 |
| `get_backtest()` | 查询已保存结果 |
| `get_trades()` | 获取交易明细 |
| `get_equity()` | 获取权益曲线 |
| `get_klines()` | 获取 K 线数据 |
| `list_symbols()` | 交易对列表 |
| `save_strategy()` | 保存策略 |
| `save_signals()` | 批量保存信号 |
| `print_metrics()` | 打印绩效报告 |
| `print_trades()` | 打印交易记录 |
| `print_conclusion()` | 打印结论建议 |

### 本地数据获取 — data_client.py

位置：`backtester/scripts/data_client.py`

策略脚本生成信号时可能需要本地拉数据（用于计算指标）。

### 技术指标库 — indicators.py

位置：`backtester/scripts/indicators.py`

支持：SMA, EMA, RSI, MACD, Bollinger Bands, ATR, KDJ, crossover/crossunder 等 12 种。

---

## 禁止事项

| 禁止行为 | 原因 |
|---------|------|
| ❌ 修改用户的策略脚本 | 修改策略是 strategy-maker 的职责 |
| ❌ 仅因回测盈利就通过 | 还需检查稳健性、过拟合、成本影响 |
| ❌ 用未来数据回测 | 严格按时间顺序，不可前视偏差 |
| ❌ 部署监控或执行交易 | 这是 monitor-executor 的职责 |
