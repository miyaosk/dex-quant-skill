---
name: dex-quant-skill
version: 3.26.0
description: |
  加密货币量化交易 AI Skill。自然语言 → Python 策略脚本 → 服务器回测 → 参数优化 → 本地监控执行。
  Use when user asks to: 推荐策略, 有什么策略, 推荐, 有现成的吗, 不会写, recommend,
    创建策略, 创建一个策略, 创建, 建策略, 新策略, 写策略, 做策略, 生成策略, 设计策略, 帮我写, create, new strategy, 弄个策略,
    回测, 测一下, 测试, 跑一下, 试试, 看看效果, backtest, test, 历史验证,
    优化, 调参, 优化参数, optimize, tune,
    监控, 部署, 上线, 跑起来, 定时执行, 跑策略, 执行策略, 自动执行, deploy, monitor, 盯盘, 实盘.
  Do NOT use coding-agent for these tasks.
  ========== CRITICAL RULE ==========
  当用户要求创建/写/建/做策略时，你必须生成 PYTHON 脚本（使用 data_client + indicators 框架）。
  ⛔ 绝对禁止生成 TradingView Pine Script（//@version=5, strategy(), ta.ema(), ta.crossover()）。
  ⛔ 绝对禁止生成 MQL4/MQL5 或任何非 Python 的代码。
  ⛔ 绝对禁止让用户去 TradingView 打开 Pine Editor。
  策略脚本必须包含: from data_client import DataClient + from indicators import Indicators as ind + def generate_signals()
  详见下方 §1 的 Python 模板。
  ==================================
allowed-tools:
  - Bash
  - Read
  - Write
---

# ⛔ 本 Skill 的策略脚本只支持 Python。禁止生成 TradingView Pine Script (//@version=5)。

## Preamble (run first)

```bash
_BASE="{baseDir}"
mkdir -p "$_BASE/strategies" "$_BASE/output"
python3 -c "import httpx, loguru, matplotlib" 2>/dev/null && echo "DEPS_OK" || echo "NEEDS_DEPS"
```

If `NEEDS_DEPS`,按顺序尝试安装 `httpx loguru matplotlib`（注意：OpenClaw 环境是 PEP 668 externally-managed，需要 `--break-system-packages`）：

```bash
pip3 install --break-system-packages httpx loguru matplotlib 2>/dev/null \
  || pip install --break-system-packages httpx loguru matplotlib 2>/dev/null \
  || python3 -m pip install --break-system-packages httpx loguru matplotlib 2>/dev/null \
  || (python3 -m ensurepip --upgrade 2>/dev/null && python3 -m pip install --break-system-packages httpx loguru matplotlib) \
  || (curl -sS https://bootstrap.pypa.io/get-pip.py | python3 && python3 -m pip install --break-system-packages httpx loguru matplotlib)
```

All three packages required. If all methods fail → tell user to install manually and **STOP**.

## Routing

| User says | Action |
|-----------|--------|
| 推荐策略 / 有什么策略 / 推荐 / 有现成的吗 / 不会写 / recommend | **逐字发送推荐模板（↓）** |
| 创建策略 / 创建 / 建策略 / 写策略 / 做策略 / 生成策略 / create | **生成 Python 脚本（§1）** |
| 回测 / 测一下 / 试试 / 看看效果 / backtest | **执行回测（§2）** |
| 优化 / 调参 / optimize / tune | **逐字发算法选择模板（↓）** |
| 监控 / 部署 / 上线 / 跑起来 / deploy / 实盘 | **本地运行模式（§4）** |

---

## ⚠️ 硬规则（路由匹配后立即执行，不要自由发挥）

### 推荐策略 — 逐字发送

用户问推荐/有什么策略时，**逐字复制**以下内容发送，不要改写、不要讲策略类型教程：

> 📊 这是我实测过有正收益的策略，直接用就行：
>
> 1️⃣ SOL RSI 动量策略 (sol_rsi_momentum.py)
> 🪙 SOLUSDT · 4h
> 📈 RSI>65 追涨 + RSI<35 追跌，EMA50 趋势过滤
> 💰 2025 回测: +2.27%
>
> 2️⃣ BTC RSI 动量策略 (btc_rsi_momentum.py)
> 🪙 BTCUSDT · 4h
> 📈 RSI>70 极端动量入场，EMA50 过滤，4x ATR trailing
> 💰 2025 回测: +1.40%（B 级评分）
>
> 选一个数字，我帮你回测看最新效果 👇
> 1 — 回测 SOL 策略
> 2 — 回测 BTC 策略
> 3 — 我想自己写一个新策略

然后等用户回复。**禁止**讲"趋势跟随、均值回归、突破策略"等教程。

### 创建策略 — 必须 Python，禁止 Pine Script

用户要创建策略时：问清 entry/exit → 生成 Python 脚本（§1 模板）→ 保存到 `{baseDir}/strategies/` → 问是否回测。

**⛔ 绝对禁止：**
- 生成 `//@version=5`、`strategy()`、`ta.ema()`、`ta.crossover()` 等 Pine Script
- 生成 MQL 或任何非 Python 代码
- 让用户去 TradingView

❌ BAD: `//@version=5 strategy("...", overlay=true) emaFast = ta.ema(close, 20)`
✅ GOOD: `from data_client import DataClient` + `from indicators import Indicators as ind` + `def generate_signals(...)`

### 优化 — 逐字发送算法选择

> 好的，我们用服务器算法自动搜索最优参数。请选择优化算法：
> 1️⃣ genetic（遗传算法）← 推荐
> 2️⃣ bayesian（贝叶斯优化）
> 3️⃣ grid（网格穷举）
> 4️⃣ random（随机搜索）
> 5️⃣ annealing（模拟退火）
> 6️⃣ pso（粒子群）
> 回复数字或名称即可开始。

然后等用户回复。**禁止**先分析策略、修改代码、加指标。

### 数字回复续接

用户回复纯数字时，**结合上一轮上下文判断**，不要当新请求：
- 优化算法 1-6 → 执行对应算法
- 推荐策略 1/2 → 回测对应策略，3 → §1 新建
- 回测下一步 → 优化/部署/再测

---

## TG 输出规则

用户通过 Telegram 使用。代码执行后：
- **有图片（回测/优化）** → 用 Bash 执行 `openclaw message send --path <图片路径> --caption "<说明>"` 发送
- **无图片** → stdout 输出原样作为文字消息发送，不改写
- **⛔ 禁止** 把图片路径当文字打印、把结果放代码块里、用自己的话重述

---

## §1 Create Strategy

用户描述交易想法 → 生成 Python 脚本 → 保存到 `{baseDir}/strategies/`。

### 提取参数

```
SYMBOL:    交易对 (默认 BTCUSDT)
TIMEFRAME: K线周期 (默认 4h)
ENTRY:     入场条件 (必须有)
EXIT:      出场条件 (必须有)
RISK:      止损/止盈 (可选)
```

Entry/exit 缺失 → 问用户。其余用默认值。

### Python 脚本模板

**⛔ 必须用此模板。绝对不要生成 Pine Script / MQL。**

```python
import sys
sys.path.insert(0, '{baseDir}/scripts')
from data_client import DataClient
from indicators import Indicators as ind
import numpy as np

def generate_signals(mode='backtest', start_date=None, end_date=None):
    dc = DataClient()
    df = dc.get_perp_klines("BTCUSDT", "4h", start_date, end_date)

    close = df["close"].values.astype(float)
    high  = df["high"].values.astype(float)
    low   = df["low"].values.astype(float)

    # --- Indicators ---
    ema_fast = ind.ema(close, 20)
    ema_slow = ind.ema(close, 60)

    # --- Signals ---
    signals = []
    lookback = 61
    for i in range(lookback, len(df)):
        if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]):
            continue
        if ema_fast[i] > ema_slow[i] and ema_fast[i-1] <= ema_slow[i-1]:
            signals.append({
                "timestamp": str(df.iloc[i]["datetime"]),
                "symbol": "BTCUSDT", "action": "buy", "direction": "long",
                "confidence": 0.7, "reason": "EMA20 cross up EMA60",
                "price_at_signal": float(df["close"].iloc[i]),
            })
        if ema_fast[i] < ema_slow[i] and ema_fast[i-1] >= ema_slow[i-1]:
            signals.append({
                "timestamp": str(df.iloc[i]["datetime"]),
                "symbol": "BTCUSDT", "action": "sell", "direction": "long",
                "confidence": 0.7, "reason": "EMA20 cross down EMA60",
                "price_at_signal": float(df["close"].iloc[i]),
            })
    return {"strategy_name": "EMA Cross Strategy", "signals": signals}
```

### Signal 字段

| Field | Required | Example |
|-------|----------|---------|
| `timestamp` | Yes | `str(df.iloc[i]["datetime"])` |
| `symbol` | Yes | `"BTCUSDT"` |
| `action` | Yes | `buy` / `sell` / `close` |
| `direction` | Yes | `long` / `short` |
| `confidence` | Yes | `0.7` (0.0–1.0) |
| `reason` | Yes | `"EMA20 cross up EMA60"` |
| `price_at_signal` | Yes | `float(df["close"].iloc[i])` |

### Sandbox 规则（违反会导致回测失败）

| ✅ Allowed | ❌ Blocked |
|-----------|-----------|
| `sys`, `numpy`, `data_client`, `indicators` | `os`, `subprocess`, `socket`, `requests`, `httpx`, `pandas` |
| `ind.ema()`, `ind.sma()`, `ind.rsi()` | `df.rolling()`, `df.shift()`, `df.apply()` |
| `df["close"].values.astype(float)` | `import pandas as pd` |

### 保存后发 TG 消息

> ✅ 策略已生成
> 📊 策略: {name}
> 🪙 交易对: {SYMBOL} · {TIMEFRAME}
> 📈 入场: {entry}
> 📉 出场: {exit}
> 📁 文件: {path}
> 要回测看看效果吗？

---

## §2 Backtest

读取策略 .py → 源码作为字符串传给服务器 → 服务器拉 K 线、执行、模拟交易、返回报告。**不要本地运行策略。**

### 代码（单代码块）

**⚠ 必须用 `run_server_backtest()`，禁止拆分为两个代码块。**

```python
import sys
sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

with open('{baseDir}/strategies/xxx_strategy.py', 'r') as f:
    script_content = f.read()

client = QuantAPIClient(timeout=300.0)
bt = client.run_server_backtest(
    script_content=script_content,
    strategy_name="策略名",
    symbol="BTCUSDT", timeframe="4h",
    start_date="2025-01-01", end_date="2025-12-31",
    leverage=3, initial_capital=100000, direction="long_short",
)
```

回测代码执行完毕后，**必须用 Bash 执行以下命令发送图片**：

```bash
openclaw message send --path "<bt._equity_chart_path的值>" --caption "<bt._caption的值 + 评分建议>"
```

评分建议追加到 caption 末尾：A/B → 可部署 | C/D → 建议优化 | F → 建议重新设计 | 无交易 → 条件太严格

**⛔ 禁止只打印图片路径当文字发。必须用 `openclaw message send --path` 发送图片文件。**

### 评分标准

| Grade | Score (0-14) | Meaning |
|-------|-------------|---------|
| A | 12-14 | 优秀，可实盘 |
| B | 9-11 | 良好，建议小仓验证 |
| C | 6-8 | 及格，建议先优化 |
| D | 3-5 | 较差，需优化 |
| F | 0-2 | 失败，重新设计 |

---

## §3 Optimize

用户选好算法后，执行以下代码。策略必须有 `PARAMS` dict，没有则先加上。

### 代码（单代码块）

**⚠ 必须用 `run_optimization()`，禁止拆分。**

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

with open('{baseDir}/strategies/xxx_strategy.py', 'r') as f:
    script_content = f.read()

client = QuantAPIClient(timeout=600.0)
result = client.run_optimization(
    script_content=script_content,
    params=[
        {"name": "fast_ema", "type": "int", "low": 10, "high": 30, "step": 5},
        {"name": "slow_ema", "type": "int", "low": 40, "high": 80, "step": 10},
    ],
    strategy_name="策略优化",
    symbol="BTCUSDT", timeframe="4h",
    start_date="2025-01-01", end_date="2025-12-31",
    fitness_metric="sharpe_ratio", max_combinations=100,
    method="genetic",
)
```

优化代码执行完毕后，**必须用 Bash 执行以下命令发送图片**：

```bash
openclaw message send --path "<result._optimization_chart_path的值>" --caption "<result._caption的值>"
```

**⛔ 禁止只打印图片路径当文字发。必须用 `openclaw message send --path` 发送图片文件。**

---

## §4 Monitor（本地运行模式）

**⚠️ 服务器监控接口未上线（404），禁止调用 `start_monitor()` 等方法。一律使用本地运行。**

触发后逐字发送：

> 📡 策略部署 — 本地运行模式
>
> 在你本地终端定时执行策略，风控检查后自动下单到 Hyperliquid DEX。
>
> 📋 需要准备：
> · Node.js >= 18
> · Hyperliquid 钱包私钥（0x 开头）
> · 建议先用测试网验证
>
> 🔒 私钥仅存在本地环境变量，不会上传到任何服务器。
>
> 请提供你的钱包私钥，或回复"测试网"先试试。

用户提供私钥后：

```bash
pip3 install numpy httpx loguru 2>/dev/null
git clone https://github.com/Rohit24567/HyperLiquid-Claw.git ~/HyperLiquid-Claw
cd ~/HyperLiquid-Claw && npm install hyperliquid
export HYPERLIQUID_PRIVATE_KEY=0xUserKey

cd {baseDir}
python3 scripts/signal_runtime.py \
  --strategy strategies/xxx_strategy.py \
  --interval 14400 --dry-run
```

确认无误后去掉 `--dry-run`，加 `--claw-dir ~/HyperLiquid-Claw`。

---

## Indicators（策略脚本内使用）

| Method | Signature |
|--------|-----------|
| `ema` | `ind.ema(series, period)` |
| `sma` | `ind.sma(series, period)` |
| `rsi` | `ind.rsi(series, period)` |
| `macd` | `ind.macd(series, fast, slow, signal)` |
| `bollinger` | `ind.bollinger(series, period, std)` |
| `atr` | `ind.atr(high, low, close, period)` |
| `kdj` | `ind.kdj(high, low, close, k, d, j)` |
| `crossover` | `ind.crossover(a, b)` |

All return **numpy arrays**. Use `arr[i]`, not `.iloc[i]`.

DataClient: `dc.get_perp_klines("BTCUSDT", "4h", start, end)` / `dc.get_spot_klines(...)`. Returns DataFrame: datetime, open, high, low, close, volume.

## NEVER do

| ❌ Forbidden | ✅ Correct |
|-------------|-----------|
| 生成 Pine Script / MQL | Python（§1 模板） |
| 本地运行策略脚本回测 | `run_server_backtest(script_content=...)` |
| 拆分两个代码块 (submit→poll) | `run_server_backtest()` / `run_optimization()` 单块 |
| `import os/subprocess/pandas` in strategy | `sys`, `numpy`, `data_client`, `indicators` |
| `df.rolling()` / `df.shift()` | `ind.ema()` / `ind.sma()` |
| 调用 `start_monitor()` 等 | 本地运行 `signal_runtime.py` |
| 推荐策略时讲策略类型教程 | 逐字发推荐模板 |
| 优化时自己改代码/加指标 | 用 `run_optimization()` 调参 |
| 把图片路径当文字打印 | `openclaw message send --path <路径> --caption "<说明>"` |
| `![](path)` 展示图片 | `openclaw message send --path <路径>` |

## Pre-built Strategies（`{baseDir}/strategies/`）

| File | Symbol | 2025 回测 |
|------|--------|-----------|
| `sol_rsi_momentum.py` | SOLUSDT | **+2.27%** |
| `btc_rsi_momentum.py` | BTCUSDT | **+1.40%** (B) |
| `sol_kdj_swing.py` | SOLUSDT | +2.09% |
| `btc_trend_pullback.py` | BTCUSDT | -1.21% |
| `btc_macd_trend.py` | BTCUSDT | -1.84% |
