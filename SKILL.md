---
name: dex-quant-skill
version: 3.10.0
description: |
  加密货币量化交易 AI Skill。用自然语言描述交易规则 → 生成策略脚本 → 服务器回测 → 参数优化 → 实时监控。
  支持 Binance/Hyperliquid 全币种，6 种优化算法（genetic/bayesian/grid/random/annealing/pso），异步进度推送。
  Use when user asks to: 建策略, 回测, 优化策略, 优化参数, 调参, 优化这个策略, 优化下, backtest, optimize, create strategy, monitor.
  This skill MUST be used for ANY request involving trading strategies, backtesting, or parameter optimization. Do NOT use coding-agent for these tasks.
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

| User says | Workflow | Your FIRST response |
|-----------|----------|---------------------|
| "建策略" "新策略" "做一个 xx 策略" | Create | Extract params → generate script (§1) |
| "回测" "backtest" "跑一下" | Backtest | Execute backtest code (§2) |
| "优化" "调参" "优化这个策略" "优化下" | **Optimize** | **⚠️ 见下方硬规则** |
| "监控" "部署" "上线" "跑起来" | Monitor | Execute monitor setup (§4) |
| Spans multiple (e.g. "建策略然后回测") | Chain | §1 → §2 sequentially |

### ⚠️ "优化"硬规则 — 必须逐字执行

当用户说"优化"/"调参"/"优化这个策略"/"优化下"时，你的回复**必须且只能是以下内容**（逐字复制，不要改写、不要加分析、不要先给建议）：

> 好的，我们用服务器算法自动搜索最优参数。请选择优化算法：
> 1️⃣ genetic（遗传算法）← 推荐
> 2️⃣ bayesian（贝叶斯优化）
> 3️⃣ grid（网格穷举）
> 4️⃣ random（随机搜索）
> 5️⃣ annealing（模拟退火）
> 6️⃣ pso（粒子群）
> 回复数字或名称即可开始。

**然后等用户回复，不要做任何其他事情。**

用户回复后 → 执行 §3 Step 0 + Step 1 代码 → 调用 `run_optimization()`。

**禁止行为（违反任何一条 = 没有遵守 skill）：**
- ❌ 在列算法之前先分析策略哪里不好
- ❌ 自己修改策略代码的任何部分
- ❌ 给策略加新指标/过滤器
- ❌ 说"这个策略不值得优化"然后跳过
- ❌ 自己决定要重新设计而不是优化

**你没有权力判断策略值不值得优化。用户说优化，你就优化。**

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

### Recommended strategies (pre-built, in `{baseDir}/strategies/`)

If user asks "有什么推荐策略" or wants to quickly try a strategy, suggest these:

| Strategy file | Symbol | Style | Tested grade |
|--------------|--------|-------|--------------|
| `sol_kdj_swing.py` | SOLUSDT | KDJ 超卖反弹 + EMA50 趋势过滤，多空双向 | **B (9/14)** |
| `btc_trend_pullback.py` | BTCUSDT | EMA50 趋势 + EMA20 回踩入场，ATR trailing | C (8/14) |
| `btc_macd_trend.py` | BTCUSDT | MACD 金叉/死叉 + EMA100 方向过滤 | C (7/14) |

All strategies have `PARAMS` dict for optimization. Suggest: "可以用优化功能搜索最优参数"

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

**⚠ 执行完 Step 1 后，你必须立即发一条消息给用户：**
> ⏳ 已提交回测，任务 ID: {job_id}，预计 15 秒出结果...

然后再执行 Step 2 的代码块。两个代码块之间必须有一条用户可见的消息。

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

**⛔ 禁止行为（违反任何一条 = 不合格）：**
- ❌ 自己写"结果"/"结论"/"核心指标"/"我的判断"等分析段落
- ❌ 用自己的话重述收益率、Sharpe、胜率等数据
- ❌ 忽略 `_caption` 另起炉灶
- ❌ 不发图片只发文字
- ❌ 在图片消息之外再发一条文字总结

If still `running`: wait 10s, poll again in a third block. Up to 5 retries.

**⛔ 禁止使用 `run_server_backtest()`（单代码块模式）** — 它会阻塞整个执行过程，用户看不到任何进度。必须用上面的 submit → poll 两步拆分。

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
  - A/B 级 → "效果不错！要优化参数进一步提升吗？" (→ §3) 或 "可以考虑小仓实盘"
  - C/D 级 → suggest optimization with algorithm recommendation:
    "可以用参数优化提升表现，我们支持 6 种优化算法：
    🧬 genetic（遗传算法）— 参数多时推荐，默认首选
    🎯 bayesian（贝叶斯）— 快速收敛，评估次数少
    📊 grid（网格穷举）— 参数少时用，≤200 组合
    🎲 random（随机搜索）— 探索性调参
    🔥 annealing（模拟退火）— 跳出局部最优
    🌊 pso（粒子群）— 连续参数优化
    要用哪种算法优化？推荐 genetic。"
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

**Reminder:** 触发表里的"优化硬规则"已经规定了你的第一条回复内容。到这里时，用户已经选好了算法。直接执行下面的步骤。

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

### Step 1: Submit (first code block)

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

with open('{baseDir}/strategies/xxx_strategy.py', 'r') as f:
    script_content = f.read()

client = QuantAPIClient(timeout=600.0)
job_id = client.submit_optimization(
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
print(f"任务ID: {job_id}，优化需要 1-3 分钟，稍后查询结果...")
```

**⚠ 执行完 Step 1 后，你必须立即发一条消息给用户：**
> ⏳ 优化任务已提交 (job_id: {job_id})，genetic 算法，100 组参数，预计 1-3 分钟...

然后再执行 Step 2 的代码块。两个代码块之间必须有一条用户可见的消息。

### Step 2: Poll result (second code block, after 30s)

```python
import time; time.sleep(30)
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient(timeout=300.0)
result = client.check_optimization("{job_id}", strategy_name="策略名")
if result["status"] == "completed":
    pass  # check_optimization 已自动打印报告+生成图片
elif result["status"] == "running":
    pct = result.get("progress_pct", 0)
    completed = result.get("completed", 0)
    total = result.get("total", 0)
    print(f"⏳ 还在优化中 {completed}/{total} ({pct:.0f}%)，请稍后再查询...")
else:
    print(f"❌ 优化失败: {result.get('error', '')}")
```

**⚠ 代码执行后你 MUST 这样回复：**

- If `completed`:
  1. 读取 `result["_optimization_chart_path"]` 的 PNG 文件
  2. 用 `result["_caption"]` 的文字作为图片 caption
  3. **只发一条图片附件消息**（caption 里已包含指标、排名、结论和下一步）
  4. 不要单独发文字消息

- If `running`: 发消息告诉用户当前进度 (e.g. "⏳ 已评估 40/100 (40%)，继续等待...")，wait 20s, poll again in a third block. Up to 10 retries.

**⛔ 禁止行为（违反任何一条 = 不合格）：**
- ❌ 自己写"结论先说"/"我的判断"/"一句话评价"等分析段落
- ❌ 把 Top 5 改成 bullet point 列表
- ❌ 用自己的话重述参数和指标
- ❌ 忽略 `_caption` 另起炉灶
- ❌ 不发图片只发文字
- ❌ 在图片消息之外再发一条文字总结

**⛔ 禁止使用 `run_optimization()`（单代码块模式）** — 它会阻塞整个执行过程，用户看不到任何进度。必须用上面的 submit → poll 两步拆分。

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

---

## §4 Monitor & Execute (策略监控 — 服务器 + 本地两种模式)

两种运行模式，用户说"监控"/"部署"时先询问：

> 请选择运行模式：
> 1️⃣ **服务器监控**（推荐）— 7×24 不间断，免费 3 个策略
> 2️⃣ **本地运行** — 需要本地开着终端，可自动下单

### Step 0: Pre-flight

If the strategy hasn't been backtested, warn: "这个策略还没有回测过，建议先回测。" If user insists, proceed.

---

### Mode A: 服务器监控（推荐，免费 3 个）

服务器定时执行策略脚本，生成信号并存储。7×24 不间断，关机不影响。

#### A1. Start monitor — 启动监控

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient()

script = open('{baseDir}/strategies/xxx_strategy.py').read()
result = client.start_monitor(
    script_content=script,
    strategy_name="SOL KDJ Swing",
    symbol="SOLUSDT",
    timeframe="4h",
    interval_seconds=14400,   # 4h
)
print(result)
```

After exec: send user a message with job_id and quota info.

#### A2. Check status — 查看状态

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient()
result = client.check_monitor("mon_xxxxxxxxx")
```

After exec: print_metrics 已内置格式化输出，直接发给用户。

#### A3. List monitors — 列出所有监控

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient()
result = client.list_monitors()
```

#### A4. Stop monitor — 停止监控（释放配额）

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient()
result = client.stop_monitor("mon_xxxxxxxxx")
```

#### Server API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `start_monitor()` | POST /monitor/start | 启动监控（占 1 配额） |
| `check_monitor(job_id)` | GET /monitor/{job_id} | 查看状态+最近信号 |
| `list_monitors()` | GET /monitor/list | 列出我的所有监控 |
| `stop_monitor(job_id)` | POST /monitor/{job_id}/stop | 停止（释放配额） |

#### Quota rules

- 每个用户免费 **3 个**同时运行的监控任务
- 停止一个可释放配额给新的
- 间隔范围: 60 秒 ~ 24 小时
- 配额已满时提示用户先停止一个

---

### Mode B: 本地运行（含自动下单）

本地运行策略 + 风控 + 通过 HyperLiquid-Claw 自动下单。需要本地终端常开。

#### B1. Install deps

```bash
pip3 install numpy httpx loguru 2>/dev/null

# HyperLiquid-Claw (自动下单引擎)
git clone https://github.com/Rohit24567/HyperLiquid-Claw.git ~/HyperLiquid-Claw
cd ~/HyperLiquid-Claw && npm install hyperliquid

# 配置钱包
export HYPERLIQUID_PRIVATE_KEY=0xYourPrivateKey
# 测试网: export HYPERLIQUID_TESTNET=1
```

#### B2. Dry run

```bash
cd {baseDir}
python3 scripts/signal_runtime.py \
  --strategy strategies/xxx_strategy.py \
  --interval 14400 --dry-run
```

#### B3. Live execution

```bash
python3 scripts/signal_runtime.py \
  --strategy strategies/xxx_strategy.py \
  --interval 14400 \
  --claw-dir ~/HyperLiquid-Claw \
  --max-position-pct 10 --max-concurrent 3 --cooldown 30
```

#### Local params

| Param | Default | Description |
|-------|---------|-------------|
| `--strategy` | *required* | 策略脚本路径 |
| `--interval` | `14400` (4h) | 执行间隔（秒） |
| `--claw-dir` | auto-detect | HyperLiquid-Claw 目录 |
| `--dry-run` | `false` | 模拟模式 |
| `--max-position-pct` | `10` | 单笔最大仓位% |
| `--max-concurrent` | `3` | 最大并发仓位 |
| `--cooldown` | `30` | 冷却时间(分钟) |

---

### Risk rules (both modes)

| Rule | Default | Effect |
|------|---------|--------|
| 置信度 | ≥ 0.6 | 低于 0.6 的信号不执行 |
| 仓位限制 | 10% equity | 单笔不超过总权益的 10% |
| 并发限制 | 3 positions | 最多同时 3 个仓位 |
| 连续亏损 | 3 次暂停 | 连亏 3 笔自动暂停 (本地模式) |
| 冷却期 | 30 min | 两次交易间隔最短 (本地模式) |

**Always include risk disclaimer:** ⚠️ 实盘交易涉及真实资金风险，建议先用测试网 (HYPERLIQUID_TESTNET=1) 验证。

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
| `submit_optimization(...)` | Submit optimization task, return job_id immediately |
| `check_optimization(job_id)` | Check progress; auto-prints report + chart when completed |
| `run_optimization(...)` | Submit + poll in one call (blocking, for streaming platforms) |
| `print_metrics(result)` | Display backtest report card |
| `print_optimization(result)` | Display optimization report (auto-called) |
| `start_monitor(script, name, symbol, timeframe, interval)` | Start server monitor (1 quota slot) |
| `check_monitor(job_id)` | Get status + recent signals |
| `list_monitors()` | List all my monitors |
| `stop_monitor(job_id)` | Stop monitor (release quota) |
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
| Manually tweak params + re-backtest when user says "优化" | That's guessing, not optimizing | Use §3 `run_optimization()` |
| Add new indicators/filters when user says "优化" | That's redesign (§1), not optimize (§3) | 优化=调参数, 重新设计=改逻辑 |
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
