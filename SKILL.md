---
name: dex-quant-skill
version: 3.4.10
description: |
  加密货币量化交易 AI Skill。用自然语言描述交易规则 → 生成策略脚本 → 服务器回测 → 参数优化 → 实时监控。
  支持 Binance/Hyperliquid 全币种，6 种优化算法，异步进度推送。
  Use when user asks to create a trading strategy, backtest, optimize parameters, or monitor crypto markets.
allowed-tools:
  - Bash
  - Read
  - Write
---

## Preamble (run first)

```bash
_BASE="{baseDir}"
_SCRIPTS="$_BASE/scripts"
_STRATS="$_BASE/strategies"
mkdir -p "$_STRATS" "$_BASE/output"
python3 -c "import httpx, loguru, matplotlib" 2>/dev/null && echo "DEPS_OK" || echo "NEEDS_DEPS"
```

If `NEEDS_DEPS`: run `pip3 install httpx loguru matplotlib 2>/dev/null || pip install httpx loguru matplotlib 2>/dev/null || python3 -m pip install httpx loguru matplotlib 2>/dev/null`. **All three packages are required** — `matplotlib` generates the equity chart PNG. If all fail, tell user to install manually and **STOP**.

## Workflow routing

Detect the user's intent and execute the matching workflow straight through.

| User says | Workflow | Jump to |
|-----------|----------|---------|
| "建策略" "新策略" "做一个 xx 策略" "create strategy" | Create | §1 |
| "回测" "backtest" "跑一下" "验证策略" | Backtest | §2 |
| "优化" "调参" "improve" "找最优" "提高 Sharpe" | Optimize | §3 |
| "监控" "部署" "上线" "跑起来" "live" | Monitor | §4 |
| Spans multiple (e.g. "建策略然后回测") | Chain | §1 → §2 sequentially |

**Automation posture:** prefer direct execution. Run the code and show results rather than listing steps. Use sensible defaults unless user specifies otherwise.

**Only stop to ask when:**
- Strategy logic is genuinely ambiguous (missing entry/exit conditions)
- Optimization target metric unclear
- Live deployment (always confirm — real money)

**Never stop for:**
- Choice of timeframe, symbol, capital (use defaults)
- Whether to show metrics (always show)
- Whether to retry on error (always retry once)

---

## §1 Create Strategy

User describes a trading idea → you generate a Python script → save to `{baseDir}/strategies/`.

### Step 1: Extract parameters

From the user's description, extract:

```
SYMBOL:      Which coin pair         (default: BTCUSDT)
TIMEFRAME:   K-line interval         (default: 4h)
ENTRY:       What triggers buy/long
EXIT:        What triggers sell/close
RISK:        Stop loss, take profit, position sizing
FILTERS:     Volume, volatility, time-of-day
```

If entry/exit conditions are missing, **STOP** and ask. Everything else — use defaults silently.

### Step 2: Generate the script

Save to `{baseDir}/strategies/{name}_strategy.py`. The script is **never executed locally** — its source code is uploaded to the server as a string for backtesting.

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
    volume = df["volume"].values.astype(float)

    # --- Indicators ---
    ema_fast = ind.ema(close, 20)
    ema_slow = ind.ema(close, 60)

    # --- Signals ---
    signals = []
    lookback = 61  # max indicator period + 1
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

### Step 3: Output

Tell user:
1. One-sentence summary of what the strategy does
2. File path where it was saved
3. Suggest next step: "要回测看看效果吗？" — if yes, proceed to §2

### Sandbox rules (CRITICAL — violating these causes server backtest to fail)

| Allowed | Blocked |
|---------|---------|
| `sys`, `numpy`, `data_client`, `indicators` | `os`, `subprocess`, `socket`, `requests`, `httpx`, `pandas` |
| `ind.ema()`, `ind.sma()`, `ind.rsi()` | `df.rolling()`, `df.shift()`, `df.apply()` |
| `df["close"].values.astype(float)` | `df["close"].rolling(20).mean()` |
| `float(df["close"].iloc[i])` | `import pandas as pd` |
| `str(df.iloc[i]["datetime"])` | `df.index[i]` or row index `i` as timestamp |

### Signal fields

| Field | Required | Example |
|-------|----------|---------|
| `timestamp` | Yes | `str(df.iloc[i]["datetime"])` |
| `symbol` | Yes | `"BTCUSDT"` |
| `action` | Yes | `buy` / `sell` / `close` / `hold` |
| `direction` | Yes | `long` / `short` |
| `confidence` | Yes | `0.7` (0.0–1.0) |
| `reason` | Yes | `"EMA20 cross up EMA60"` |
| `price_at_signal` | Yes | `float(df["close"].iloc[i])` |
| `suggested_stop_loss` | No | stop loss price |
| `suggested_take_profit` | No | take profit price |

---

## §2 Backtest (server-side, free, unlimited)

**How it works:** Read strategy `.py` → pass source code as string → server fetches K-lines, executes script, simulates trades, returns metrics. You never run the strategy script locally.

```
LOCAL                          SERVER
┌──────────┐  script_content  ┌─────────────────┐
│ Read .py │ ───────────────▶ │ Fetch K-lines   │
│ Submit   │  job_id          │ Execute script   │
│ Poll     │ ◀─────────────── │ Simulate trades  │
│ Display  │  metrics+trades  │ Return report    │
└──────────┘                  └─────────────────┘
```

### Step 1: Submit (first code block)

```python
import sys
sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

with open('{baseDir}/strategies/xxx_strategy.py', 'r') as f:
    script_content = f.read()

client = QuantAPIClient(timeout=300.0)
job_id = client.submit_backtest(
    script_content=script_content,
    strategy_name="策略名",
    symbol="BTCUSDT",
    timeframe="4h",
    start_date="2025-01-01",
    end_date="2025-12-31",
    leverage=3,
    initial_capital=100000,
    direction="long_short",
)
print(f"任务ID: {job_id}，等待 15 秒后查询结果...")
```

Tell user **immediately** that the task is submitted. Two code blocks = user sees "submitted" right away instead of waiting in silence.

### Step 2: Poll result (second code block, after 15s)

```python
import time; time.sleep(15)
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient(timeout=300.0)
bt = client.check_backtest("{job_id}")
if bt["status"] == "completed":
    client.print_metrics(bt)
elif bt["status"] == "running":
    print("⏳ 还在执行中，请稍后再查询...")
else:
    print(f"❌ 回测失败: {bt.get('error', '')}")
```

**⚠ 代码执行后你 MUST 这样回复：**
1. 读取 `bt["_equity_chart_path"]` 的 PNG 文件
2. 用 `bt["_caption"]` 的文字作为图片 caption
3. **只发一条图片附件消息**（caption 里已包含关键指标）
4. 不要单独发文字消息（会被系统 heartbeat 吞掉）

If still `running`: wait 10s, poll again in a third block. Up to 5 retries.

### Quick backtest (single block, for platforms with streaming output)

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

with open('{baseDir}/strategies/xxx_strategy.py', 'r') as f:
    script_content = f.read()

client = QuantAPIClient(timeout=300.0)
bt = client.run_server_backtest(
    script_content=script_content,
    strategy_name="策略名", symbol="BTCUSDT", timeframe="4h",
    start_date="2025-01-01", end_date="2025-12-31",
    leverage=3, initial_capital=100000, direction="long_short",
)
client.print_metrics(bt)
```

**⚠ 代码执行后你 MUST 这样回复：**
1. 读取 `bt["_equity_chart_path"]` 的 PNG 文件
2. 用 `bt["_caption"]` 作为图片 caption
3. **只发一条图片附件消息**（不要单独发文字，会被 heartbeat 吞掉）

### Backtest parameters

| Param | Default | Options |
|-------|---------|---------|
| `symbol` | `BTCUSDT` | Any Binance perpetual pair |
| `timeframe` | `4h` | `1m` `5m` `15m` `1h` `4h` `1d` |
| `start_date` | `2025-01-01` | YYYY-MM-DD |
| `end_date` | `2025-12-31` | YYYY-MM-DD |
| `leverage` | `3` | 1–125 |
| `initial_capital` | `100000` | USD |
| `direction` | `long_short` | `long_only` `short_only` `long_short` |

### Error handling

| Error | Auto-action |
|-------|-------------|
| `脚本安全检查未通过` | Fix strategy (sandbox violation) — see §1 Sandbox rules |
| `status: failed` | Retry once automatically, then report |
| `status: running` after 60s | Poll every 15s, up to 5 minutes |
| Network error / timeout | Retry once, then report |

### Display rules

`print_trades(bt)` prints full trade table — only needed if user asks for more details.

After completion, suggest next step **based on grade**:
  - A/B 级 → "效果不错！要优化参数吗？" (→ §3) 或 "可以考虑小仓实盘"
  - C 级 → "及格但不够好，要优化参数还是调整逻辑？"
  - D 级 → "策略需要优化，建议调整入场/出场逻辑后重测"
  - F 级 → "策略失败，建议重新设计策略逻辑" (→ §1)
  - Zero trades → "没有交易信号，入场条件可能太严格。" (→ §1)

### Strategy evaluation standard

Server returns a scorecard with 7 metrics, each scored 0-2 (max 14):

| Metric | 🟢 优 (2分) | 🟡 及格 (1分) | 🔴 差 (0分) |
|--------|------------|--------------|------------|
| 收益率 | >20% | >0% | ≤0% |
| Sharpe | >1.5 | >0.5 | ≤0.5 |
| 最大回撤 | <10% | <20% | ≥20% |
| 胜率 | >50% | >35% | ≤35% |
| 盈亏比 | >1.5 | >1.0 | ≤1.0 |
| 交易数 | ≥30 | ≥10 | <10 |
| 爆仓 | 0次 | — | >0次 |

| Grade | Score | Conclusion | Meaning |
|-------|-------|------------|---------|
| A | 12-14 | approved | 优秀策略，可直接实盘 |
| B | 9-11 | approved | 良好策略，建议小仓实盘验证 |
| C | 6-8 | paper_trade_first | 及格策略，建议先模拟观察 |
| D | 3-5 | rejected | 较差策略，需要优化后再测 |
| F | 0-2 | rejected | 失败策略，建议重新设计 |

---

## §3 Optimize (server-side, free, unlimited)

**CRITICAL: When user says "优化" / "调参" / "improve" / "找最优" — MUST use this workflow. Never manually tweak parameters and re-backtest — that's guessing, not optimizing.**

### Step 0: Check if strategy is parameterized

The strategy must have a `PARAMS` dict at the top. If not, refactor it first:

**Before (hardcoded — cannot optimize):**
```python
ema_fast = ind.ema(close, 20)
ema_slow = ind.ema(close, 60)
```

**After (parameterized — ready to optimize):**
```python
PARAMS = {'fast_ema': 20, 'slow_ema': 60, 'rsi_th': 55, 'sl_atr': 1.5, 'tp_atr': 3.0}

def generate_signals(mode='backtest', start_date=None, end_date=None):
    fast = PARAMS['fast_ema']
    slow = PARAMS['slow_ema']
    ema_fast = ind.ema(close, fast)
    ema_slow = ind.ema(close, slow)
```

If the strategy needs refactoring, do it silently, save, then continue.

### Step 1: Run optimization

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

with open('{baseDir}/strategies/xxx_strategy.py', 'r') as f:
    script_content = f.read()

client = QuantAPIClient(timeout=600.0)
result = client.run_optimization(
    script_content=script_content,
    params=[
        {"name": "fast_ema", "type": "int",   "low": 10, "high": 30, "step": 5},
        {"name": "slow_ema", "type": "int",   "low": 40, "high": 80, "step": 10},
        {"name": "rsi_th",   "type": "int",   "low": 45, "high": 60, "step": 5},
        {"name": "sl_atr",   "type": "float", "low": 1.0, "high": 2.0, "step": 0.2},
        {"name": "tp_atr",   "type": "float", "low": 2.0, "high": 4.0, "step": 0.5},
    ],
    strategy_name="策略优化",
    symbol="BTCUSDT", timeframe="4h",
    start_date="2025-01-01", end_date="2025-12-31",
    fitness_metric="sharpe_ratio",
    max_combinations=100,
    method="genetic",
)
client.print_optimization(result)
```

### Optimization methods

| Method | Best for | When to pick |
|--------|----------|--------------|
| `genetic` | Large param space | **Default** |
| `bayesian` | Few evaluations | User says "快速" |
| `grid` | ≤200 combos | User says "穷举" |
| `random` | High-dimensional | Exploratory |
| `annealing` | Escape local optima | Stuck in bad region |
| `pso` | Continuous params | All-float params |

### Fitness metrics

| Metric | Default |
|--------|---------|
| `sharpe_ratio` | **Yes** — risk-adjusted return |
| `total_return` | Raw total return |
| `max_drawdown` | Minimize drawdown |
| `win_rate` | Maximize win rate |
| `profit_factor` | Gross profit / gross loss |

### Step 2: Output + apply

1. Show full `print_optimization(result)` — Top 5 combos with metrics.
2. Suggest: "最优参数是 fast_ema=15, slow_ema=50。要更新策略并回测验证吗？"
3. If yes: update `PARAMS` → save → run §2 with the updated script.

---

## §4 Monitor (live, uses quota, 3 free slots)

### Step 0: Pre-flight

If the strategy hasn't been backtested, warn: "这个策略还没有回测过，建议先回测。" If user insists, proceed.

### Step 1: Install dependencies

Live monitoring needs heavier deps than backtest:

```bash
pip3 install numpy pandas httpx loguru yfinance 2>/dev/null || pip install numpy pandas httpx loguru yfinance 2>/dev/null || python3 -m pip install numpy pandas httpx loguru yfinance 2>/dev/null
```

### Step 2: Run live

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from strategies.xxx_strategy import generate_signals

result = generate_signals(mode='live')
print(result)
```

### Step 3: Interpret signals

Show: signal count, per-signal details (symbol, action, direction, confidence, reason, price), which signals pass confidence threshold (≥ 0.6).

**Always include risk disclaimer:** 实盘交易涉及真实资金风险。

---

## API Reference

### DataClient (server-side, inside strategy scripts)

```python
dc = DataClient()
df = dc.get_perp_klines("BTCUSDT", "4h", start_date, end_date)   # perpetual futures
df = dc.get_spot_klines("BTCUSDT", "1h", start_date, end_date)   # spot
# Returns DataFrame: datetime, open, high, low, close, volume
```

Only use `get_perp_klines` and `get_spot_klines`. Do not invent method names.

### Indicators (server-side, inside strategy scripts)

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

### QuantAPIClient (local, calls server)

| Method | Description |
|--------|-------------|
| `submit_backtest(...)` | Submit backtest job → returns `job_id` |
| `check_backtest(job_id)` | Poll status: running / completed / failed |
| `wait_backtest(job_id)` | Poll until complete, print progress |
| `run_server_backtest(...)` | Submit + poll in one call (blocking) |
| `run_optimization(...)` | Submit optimization, poll until complete |
| `print_metrics(result)` | Display backtest report card |
| `print_optimization(result)` | Display optimization Top 5 |
| `print_trades(result)` | Display trade records (only when user asks) |

### Quota

| Feature | Limit |
|---------|-------|
| Strategy generation | Unlimited, free |
| Backtest | Unlimited, free |
| Optimization | Unlimited, free |
| Live monitoring | 3 slots |

---

## NEVER do these

| Forbidden | Why | Correct |
|-----------|-----|---------|
| Run strategy script locally for backtest | Server runs it | `submit_backtest(script_content=...)` |
| `import os/subprocess/socket` in strategy | Sandbox blocks them | Only `sys`, `numpy`, `data_client`, `indicators` |
| `df.rolling()`, `df.shift()`, `df.apply()` | Server pandas restricted | Use `ind.ema()`, `ind.sma()` etc. |
| Install numpy/pandas for backtest | Server has them | Only `httpx loguru matplotlib` locally |
| Build local backtest engine | Server already has one | Use `submit_backtest()` |
| Call `httpx.post()` directly | Missing auth/polling | Use `QuantAPIClient` |
| Manually tweak params + re-backtest | That's guessing | Use §3 `run_optimization()` |
| Send text and image as separate messages | Heartbeat will delete the text message | 只发一条图片附件（caption 含指标摘要） |
| Use `![](path)` for chart image | Telegram can't render local paths | 用平台的文件/图片发送功能作为附件发送 |

---

## Important Rules

1. **Backtest first, optimize second.** Get a working strategy before tuning.
2. **Two code blocks for backtest.** User sees "submitted" immediately.
3. **Always show full report card.** `print_metrics()` / `print_optimization()` — never paraphrase.
4. **Retry once on failure.** Automatic, no need to ask.
5. **Indicators return numpy arrays.** `arr[i]` not `.iloc[i]`.
6. **Timestamps: `str(df.iloc[i]["datetime"])`** — never row index.
7. **`lookback` covers longest indicator.** EMA(60) → at least 61 bars warmup.
8. **Descriptive filenames.** `btc_ema_cross_strategy.py`, not `strategy1.py`.
9. **One strategy per file.** Never bundle.
10. **Local deps: `httpx`, `loguru`, `matplotlib`.** Don't install numpy/pandas — server has them.
