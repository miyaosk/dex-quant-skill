---
name: dex-quant-skill
version: 2.3.1
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
mkdir -p "$_STRATS"
python3 -c "import httpx, loguru" 2>/dev/null && echo "DEPS_OK" || echo "NEEDS_DEPS"
```

If `NEEDS_DEPS`: run `pip3 install httpx loguru 2>/dev/null || pip install httpx loguru 2>/dev/null || python3 -m pip install httpx loguru 2>/dev/null`. If all fail, tell user to install manually.

## Guidelines

- **Prefer direct execution.** When the user asks to backtest or optimize, run the code and show results rather than listing steps.
- **Streamline decisions.** Use sensible defaults (server backtest, genetic optimization) unless the user specifies otherwise.
- **Backtest = submit script to server.** Server handles K-line data, script execution, and trade simulation. No local data download needed.
- **Use `QuantAPIClient` for all API calls.** It handles auth, async polling, progress display, and error retry.
- **"Optimize" = `run_optimization()`**, not manual parameter tweaking. See §4.

## Workflows

### 1. Create a strategy

User describes a trading idea → you generate a Python script → save to `{baseDir}/strategies/`.

```python
import sys
sys.path.insert(0, '{baseDir}/scripts')
from data_client import DataClient
from indicators import Indicators as ind

def generate_signals(mode, start_date, end_date):
    dc = DataClient()
    df = dc.get_perp_klines("BTCUSDT", "4h", start_date, end_date)
    ema20 = ind.ema(df["close"], 20)
    ema60 = ind.ema(df["close"], 60)
    signals = []
    for i in range(61, len(df)):
        if ema20[i] > ema60[i] and ema20[i-1] <= ema60[i-1]:
            signals.append({
                "timestamp": str(df.iloc[i]["datetime"]),  # ⚠️ must be datetime, NOT row index
                "symbol": "BTCUSDT", "action": "buy", "direction": "long",
                "confidence": 0.7, "reason": "EMA20 cross up",
                "price_at_signal": float(df["close"].iloc[i])
            })
    return {"strategy_name": "My Strategy", "signals": signals}
```

**Signal format:** `timestamp, symbol, action(buy/sell), direction(long/short), confidence, reason, price_at_signal`. Optional: `suggested_stop_loss, suggested_take_profit`.

**⚠️ timestamp must be `str(df.iloc[i]["datetime"])`** — never use row index `i` or `df.index[i]`.

### 2. Backtest (server-side, free, unlimited)

Submit script source code to server. Server fetches K-lines, runs script, simulates trades, returns metrics.

**Step 1 — Submit (first code block):**
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

Tell user **immediately** that the task is submitted.

**Step 2 — Poll result (second code block):**
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

If `running`, wait 10s and poll again in a third code block.

**Why two code blocks?** User sees "task submitted" immediately instead of waiting 15s in silence.

**Display rules:**
- Always show full `print_metrics(bt)` output. Never summarize as "收益为负".
- `print_trades(bt)` only when user explicitly asks for trade records.

### 3. Quick backtest (single block, for platforms with streaming output)

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

### 4. Parameter optimization (free, unlimited)

**🚨 When user says "optimize" / "improve" / "tune" — you MUST use this, not manual tweaking.**

| Trigger | Action |
|---------|--------|
| "优化"、"改进"、"调参"、"提高收益/Sharpe" | `run_optimization()` |
| "批量回测"、"对比参数"、"找最优" | `run_optimization()` |
| Manually change EMA20→EMA15 then re-backtest | ❌ **WRONG. This is guessing, not optimizing.** |

**Step 1 — Create PARAMS template** from current strategy:
```python
PARAMS = {'fast_ema': 20, 'slow_ema': 60, 'rsi_th': 55, 'sl_atr': 1.5, 'tp_atr': 3.0}

def generate_signals(mode='backtest', start_date=None, end_date=None):
    fast = PARAMS['fast_ema']
    slow = PARAMS['slow_ema']
    # ... use PARAMS values instead of hardcoded numbers ...
```

**Step 2 — Run optimization:**
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
        {"name": "rsi_th",   "type": "int", "low": 45, "high": 60, "step": 5},
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

**Optimization methods:**

| Method | Description | Best for |
|--------|-------------|----------|
| `genetic` ⭐ | Crossover + mutation + elitism | Default choice, large param space |
| `bayesian` ⭐ | TPE, fast convergence | Few evaluations needed |
| `grid` | Exhaustive search | ≤200 combinations |
| `random` | Random sampling | High-dimensional exploration |
| `annealing` | Simulated annealing | Escape local optima |
| `pso` | Particle swarm | Continuous params |

Default → `genetic`. User says "快速" → `bayesian`. User says "穷举" → `grid`.

### 5. Live monitoring (uses quota, 3 free slots)

```bash
pip3 install numpy pandas httpx loguru yfinance 2>/dev/null || pip install numpy pandas httpx loguru yfinance 2>/dev/null || python3 -m pip install numpy pandas httpx loguru yfinance 2>/dev/null
```

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from strategies.xxx_strategy import generate_signals
result = generate_signals(mode='live')
```

## API Reference

### DataClient

```python
dc = DataClient()
df = dc.get_perp_klines("BTCUSDT", "4h", start_date, end_date)   # perpetual futures
df = dc.get_spot_klines("BTCUSDT", "1h", start_date, end_date)   # spot
# Returns DataFrame: datetime, open, high, low, close, volume
```

Only use `get_perp_klines` and `get_spot_klines`. Do not invent method names.

### Indicators

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

Note: indicators return **numpy arrays**, not pandas Series. Use `arr[i]` not `.iloc[i]`.

### QuantAPIClient

| Method | Description |
|--------|-------------|
| `submit_backtest(...)` | Submit backtest job, returns `job_id` immediately |
| `check_backtest(job_id)` | Poll job status (running/completed/failed) |
| `wait_backtest(job_id)` | Poll until complete, print progress |
| `run_server_backtest(...)` | Submit + poll in one call (blocking) |
| `run_optimization(...)` | Submit param optimization, poll until complete |
| `print_metrics(result)` | Display backtest report card |
| `print_optimization(result)` | Display optimization Top 5 |
| `print_trades(result)` | Display trade records (only when user asks) |

### Quota

| Feature | Free | Uses quota |
|---------|------|-----------|
| Strategy generation | ✅ | No |
| Backtest (unlimited) | ✅ | No |
| Parameter optimization | ✅ | No |
| Live monitoring | 3 slots | Yes |

## Project Structure

```
dex-quant-skill/
├── SKILL.md              ← this file
├── scripts/
│   ├── api_client.py     ← server client (backtest, optimize)
│   ├── data_client.py    ← K-line data (server-side)
│   ├── indicators.py     ← technical indicators (server-side)
│   ├── machine_auth.py   ← auto auth
│   └── strategy_runner.py
├── strategies/           ← generated strategy scripts go here
└── schemas/
    └── signal_format.json
```

## Tips

1. **Backtest first, optimize second.** Get a working strategy before tuning parameters.
2. **Use `submit_backtest` + `check_backtest` for progress.** Two separate code blocks = user sees "submitted" immediately.
3. **Optimization > manual tuning.** 60 genetic evaluations in 90s beats hours of hand-tuning.
4. **Use `str(df.iloc[i]["datetime"])` for timestamps.** Row indices cause 0-trade backtests.
5. **Indicators return numpy arrays.** Use `arr[i]` not `.iloc[i]`.
6. **Don't install heavy deps for backtest.** Only `httpx` and `loguru` needed locally. Server has numpy/pandas.
7. **Check `print_metrics` output.** Never summarize results in your own words — show the full report card.
8. **Retry on failure.** If backtest returns error, retry once automatically before reporting to user.
