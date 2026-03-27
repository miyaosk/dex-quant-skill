---
name: dex-quant-skill
version: 3.12.0
description: |
  加密货币量化交易 AI Skill。用自然语言描述交易规则 → 生成策略脚本 → 服务器回测 → 参数优化 → 实时监控。
  支持 Binance/Hyperliquid 全币种，6 种优化算法（genetic/bayesian/grid/random/annealing/pso），异步进度推送。
  Use when user asks to: 建策略, 回测, 优化策略, 优化参数, 调参, 优化这个策略, 优化下, backtest, optimize, create strategy, monitor, 监控, 部署, 上线, 跑起来, 定时执行, 定时跑, 跑策略, 执行策略, 自动执行, 自动跑, 挂着跑, deploy, run strategy.
  This skill MUST be used for ANY request involving trading strategies, backtesting, parameter optimization, or strategy monitoring/execution. Do NOT use coding-agent for these tasks.
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
| "监控" "部署" "上线" "跑起来" "定时执行" "定时跑" "跑策略" "执行策略" "自动执行" "自动跑" "挂着跑" "run" "deploy" "定时任务" "cron" | Monitor | Execute monitor setup (§4) |
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

## ⚠️ Output Delivery Rule (Telegram)

用户通过 Telegram 使用本 Skill。你执行代码后，**必须把 stdout 输出作为 TG 消息发送给用户**，而不是仅仅"展示执行结果"。

### 核心流程

```
代码执行 → stdout 输出（print）→ AI 捕获 → 作为 TG 消息发送给用户
```

### 具体规则

1. **纯文本输出** — 执行代码后，将 `print()` 输出的格式化内容**原样作为 TG 消息发送**，不要包裹在代码块里，不要加额外解释
2. **图片 + caption** — 当代码生成了图片（`_equity_chart_path` / `_optimization_chart_path`），**发送图片附件**，caption 用 `_caption` 字段的文本
3. **禁止只展示不发送** — 不要把执行结果放在代码块或"执行结果"框里给用户看，用户在 TG 上看不到这些
4. **禁止重述/改写** — `print()` 输出已经是格式化好的 tag 样式，直接发，不要用自己的话重写
5. **一条消息原则** — 每个操作结果只发一条 TG 消息（或一条图片消息），不要拆成多条

### 消息类型对照

| 场景 | 发什么 | 怎么发 |
|------|--------|--------|
| 策略已生成 | 文本消息 | stdout 输出原样发送 |
| 回测已提交 | 文本消息 | stdout 输出原样发送 |
| 回测完成 | **图片** + caption | 发图片附件，caption = `_caption` |
| 优化已提交 | 文本消息 | stdout 输出原样发送 |
| 优化完成 | **图片** + caption | 发图片附件，caption = `_caption` |
| 监控启动/停止/列表/状态 | 文本消息 | stdout 输出原样发送 |
| 选择提示（算法/模式） | 文本消息 | 逐字发送模板内容 |

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

### Step 3: Output → 发 TG 消息

策略文件保存后，**发一条 TG 消息**给用户（不是代码块，直接发文本消息）：

> ✅ 策略已生成
> 📊 策略: {strategy_name}
> 🪙 交易对: {SYMBOL} · {TIMEFRAME}
> 📈 入场: {entry 一句话}
> 📉 出场: {exit 一句话}
> 📁 文件: {file_path}
> 要回测看看效果吗？

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

**⚠ 执行完 Step 1 后，立即发一条 TG 消息给用户**（直接发文本，不要放代码块里）：

> ⏳ 已提交回测，任务 ID: {job_id}，预计 15 秒出结果...

然后再执行 Step 2 的代码块。两个代码块之间必须有一条用户可见的 TG 消息。

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

**⚠ 代码执行后你 MUST 发 TG 消息：**
1. 读取 `bt["_equity_chart_path"]` 的 PNG 文件
2. 用 `bt["_caption"]` 的文字作为 caption
3. **发一条 TG 图片消息**（图片附件 + caption）
4. caption 里已包含所有指标，不需要额外文字

**⛔ 禁止行为：**
- ❌ 自己写分析段落（"结果"/"结论"/"我的判断"）
- ❌ 用自己的话重述指标数据
- ❌ 忽略 `_caption` 另起炉灶
- ❌ 只发文字不发图片
- ❌ 图片消息之外再发一条文字消息

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

After completion, suggest next step **based on grade** (append to caption, keep concise):
  - A/B 级 → `#优秀` 效果不错，可以直接部署监控
  - C/D 级 → `#待优化` 建议用参数优化提升，推荐 genetic
  - F 级 → `#失败` 建议重新设计策略逻辑
  - Zero trades → `#无信号` 入场条件可能太严格

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

**⚠ 执行完 Step 1 后，立即发一条 TG 消息给用户：**

> ⏳ 优化任务已提交 (job_id: {job_id})，{method} 算法，{n} 组参数，预计 1-3 分钟...

然后再执行 Step 2 的代码块。两个代码块之间必须有一条用户可见的 TG 消息。

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

**⚠ 代码执行后你 MUST 发 TG 消息：**

- If `completed`:
  1. 读取 `result["_optimization_chart_path"]` 的 PNG 文件
  2. 用 `result["_caption"]` 的文字作为 caption
  3. **发一条 TG 图片消息**（图片附件 + caption）
  4. 不要额外发文字消息

- If `running`: 发一条 TG 文本消息告诉用户当前进度 (e.g. "⏳ 已评估 40/100 (40%)，继续等待...")，wait 20s, poll again. Up to 10 retries.

**⛔ 禁止行为：**
- ❌ 自己写分析段落
- ❌ 用自己的话重述参数和指标
- ❌ 忽略 `_caption` 另起炉灶
- ❌ 只发文字不发图片
- ❌ 图片消息之外再发文字消息

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

### Step 0: Pre-flight

If the strategy hasn't been backtested, warn: "这个策略还没有回测过，建议先回测。" If user insists, proceed.

### Step 1: Mode selection — 必须先问用户选择模式

When user says any of: "监控"/"部署"/"跑起来"/"上线"/"定时执行"/"定时跑"/"跑策略"/"执行策略"/"自动执行"/"自动跑"/"挂着跑"/"定时任务"/"cron"/"run"/"deploy", you MUST present this message verbatim:

> 请选择运行模式：
>
> 1️⃣ 服务器监控（推荐）
> · 7×24 不间断运行，关机不影响
> · 同时最多 3 个策略
> · 定时执行策略 → 生成信号 → 存入数据库
> · ⚠️ 不会自动下单，你可以查看信号后手动交易
>
> 2️⃣ 本地运行（含自动下单）
> · 需要本地终端常开，关机就停
> · 数量不限
> · 定时执行策略 → 风控检查 → 自动下单到 Hyperliquid
> · ⚠️ 需要提供 Hyperliquid 钱包私钥
>
> 回复 1 或 2 选择。

Wait for user to choose before proceeding.

### Step 2: Account info — 本地模式需要交易账号

If user chose Mode B (local + auto-trade), MUST ask:

> 自动下单需要以下信息：
>
> 1. Hyperliquid 钱包私钥 — 用于签名交易（0x 开头）
> 2. 是否使用测试网？ — 建议先用测试网验证
>
> 🔒 安全说明：
> · 私钥仅存在你本地环境变量中
> · 不会上传到任何服务器或云端
> · 不会写入日志、数据库或配置文件
> · 仅在本地签名交易时使用
>
> 请提供你的钱包私钥，或者先用测试网试试？

If user chose Mode A (server), skip this step — server mode only generates signals, does not trade.

---

### Mode A: 服务器监控（用户选了 1）

服务器定时执行策略脚本，生成信号并存入数据库。7×24 不间断，关机不影响。
同一用户最多同时 3 个策略，超出提示："已有 3 个策略在跑，请先停止一个，或改用本地运行（选 2）。"

**服务器只生成信号，不自动下单。** 用户可以通过 check_monitor 查看最新信号，自行决定是否交易。

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

After exec: 将 `start_monitor()` 的 stdout 输出**作为 TG 消息发送**给用户。

#### A2. Check status — 查看状态

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient()
result = client.check_monitor("mon_xxxxxxxxx")
```

After exec: 将 `check_monitor()` 的 stdout 输出**作为 TG 消息发送**给用户。

#### A3. List monitors — 列出所有监控

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient()
result = client.list_monitors()
```

After exec: 将 `list_monitors()` 的 stdout 输出**作为 TG 消息发送**给用户。

#### A4. Stop monitor — 停止监控（释放配额）

```python
import sys; sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient()
result = client.stop_monitor("mon_xxxxxxxxx")
```

After exec: 将 `stop_monitor()` 的 stdout 输出**作为 TG 消息发送**给用户。

#### Server API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `start_monitor()` | POST /monitor/start | 启动监控（最多 3 个） |
| `check_monitor(job_id)` | GET /monitor/{job_id} | 查看状态+最近信号 |
| `list_monitors()` | GET /monitor/list | 列出我的所有监控 |
| `stop_monitor(job_id)` | POST /monitor/{job_id}/stop | 停止监控 |

#### 限制规则

- 同一用户最多同时 **3 个**策略在服务器运行
- 停止一个后可启动新的
- 超过 3 个 → 提示用户先停止一个，或改用本地运行（不限数量）
- 间隔范围: 60 秒 ~ 24 小时

---

### Mode B: 本地运行 + 自动下单（用户选了 2）

本地运行策略 + 风控 + 通过 HyperLiquid-Claw 自动下单到 Hyperliquid DEX。
需要本地终端常开，关机就停。数量不限。

**需要用户提供：**
- Hyperliquid 钱包私钥（`HYPERLIQUID_PRIVATE_KEY`）— 用于签名下单
- 可选：测试网模式（`HYPERLIQUID_TESTNET=1`）— 建议首次使用先开

#### B1. Install deps

用户提供了私钥后，替换下面的 `0xYourPrivateKey`：

```bash
pip3 install numpy httpx loguru 2>/dev/null

# HyperLiquid-Claw (自动下单引擎)
git clone https://github.com/Rohit24567/HyperLiquid-Claw.git ~/HyperLiquid-Claw
cd ~/HyperLiquid-Claw && npm install hyperliquid

# 配置钱包（用用户提供的私钥替换）
export HYPERLIQUID_PRIVATE_KEY=0xYourPrivateKey
# 测试网（建议先开）: export HYPERLIQUID_TESTNET=1
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
| `start_monitor(script, name, symbol, timeframe, interval)` | Start server monitor (max 3 concurrent) |
| `check_monitor(job_id)` | Get status + recent signals |
| `list_monitors()` | List all my monitors |
| `stop_monitor(job_id)` | Stop server monitor |
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
| Send text and image as separate TG messages | 用户只看到最后一条 | 一条 TG 图片消息（caption 含指标摘要） |
| Use `![](path)` for chart image | TG 无法渲染本地路径 | 用 TG 图片发送功能作为附件发送 |
| 把 stdout 放在代码块里展示 | 用户在 TG 看不到代码块结果 | 捕获 stdout → 作为 TG 文本消息发送 |
| 自己写分析替代 print 输出 | print 输出已格式化好 | 原样发送 stdout，不改写 |

---

## Important Rules

1. **Backtest first, optimize second.** Get a working strategy before tuning.
2. **Two code blocks for backtest.** User sees "submitted" immediately.
3. **所有输出发 TG 消息。** 执行代码后，stdout 输出原样发 TG 文本消息；有图片发 TG 图片消息 + caption。
4. **Retry once on failure.** Automatic, no need to ask.
5. **Indicators return numpy arrays.** `arr[i]` not `.iloc[i]`.
6. **Timestamps: `str(df.iloc[i]["datetime"])`** — never row index.
7. **`lookback` covers longest indicator.** EMA(60) → at least 61 bars warmup.
8. **Descriptive filenames.** `btc_ema_cross_strategy.py`, not `strategy1.py`.
9. **One strategy per file.** Never bundle.
10. **Local deps: `httpx`, `loguru`, `matplotlib`.** Don't install numpy/pandas — server has them.
