---
name: dex-quant-skill
description: >
  加密货币量化交易 AI Skill。用户用自然语言描述交易规则 → AI 生成策略脚本 → 服务器回测验证 → 实时监控。
  Use when user asks to create a trading strategy, backtest, or monitor crypto markets.
---

# DEX Quant Skill — 加密货币量化交易

## ⚠️ 行为准则（必须遵守）

1. **你是执行者**。你自己运行代码完成任务，不要给用户贴命令让他们手动跑。
2. **不要问用户选择**。不要问"你选哪种？"、"要我装依赖吗？"、"本地还是服务器？"。直接做。
3. **回测 = 把脚本源码上传到服务器**。服务器负责拉K线、跑信号、回测。本地不需要下载任何数据。
4. **依赖缺失时自动安装**：按顺序尝试 `pip3 install httpx loguru`、`pip install httpx loguru`、`python3 -m pip install httpx loguru`，直到成功为止。不要问用户。
5. **生成策略后如果用户说回测，立刻执行**，不要再确认。
6. **回测失败时自动重试一次**，不要问用户要不要重试。
7. **用户问"怎么优化"、"如何改进"、"怎么提高收益"时，优先使用参数优化功能**（`run_optimization`）自动搜索最优参数，而不是手动分析建议。先写一个带 PARAMS 的策略模板，然后用遗传算法或贝叶斯优化自动找最优组合。
8. **必须使用 `api_client.py` 中的 `QuantAPIClient`**。禁止自己写 `httpx.post()`/`requests.post()` 直接调 API。`QuantAPIClient` 已封装认证、异步轮询、进度显示、错误重试。

---

## 配额规则

| 功能 | 是否免费 | 是否占配额 |
|------|---------|-----------|
| 生成策略脚本 | 免费 | 不占 |
| 回测（无限次） | 免费 | 不占 |
| 定时监控任务 | 免费 3 个 | 占配额 |

回测可以随便跑，不占用任何配额。配额只限制「定时监控任务」的数量（免费 3 个）。

---

## 流程

```
用户描述想法 → 你生成策略脚本(.py) → 用户说回测 → 你读取脚本源码 + 调服务器API → 展示结果
```

本地不需要运行策略脚本、不需要下载K线数据。脚本源码直接上传给服务器执行。

---

## 1. 策略制作

用户说交易想法时，生成 Python 策略脚本，保存到 `{baseDir}/strategies/` 目录。

脚本要求：
- `import sys; sys.path.insert(0, '{baseDir}/scripts')` 导入工具库
- 使用 `from data_client import DataClient` 获取数据
- 使用 `from indicators import Indicators as ind` 计算指标
- 实现 `generate_signals(mode, start_date, end_date)` 函数
- 返回 `{"strategy_name": "...", "signals": [...]}`

**DataClient 核心方法**（必须用这些名字，不要自己编）：
```python
dc = DataClient()
df = dc.get_perp_klines("BTCUSDT", "4h", start_date, end_date)  # 永续合约K线
df = dc.get_spot_klines("BTCUSDT", "1h", start_date, end_date)  # 现货K线
# 返回 DataFrame: datetime, open, high, low, close, volume
```

**Indicators 常用方法**：
```python
ind.ema(series, period)    ind.sma(series, period)
ind.rsi(series, period)    ind.macd(series, fast, slow, signal)
ind.bollinger(series, period, std)  ind.atr(high, low, close, period)
ind.kdj(high, low, close, k, d, j) ind.crossover(a, b)
```

信号格式：`timestamp, symbol, action(buy/sell), direction(long/short), confidence, reason, price_at_signal`。可选：`suggested_stop_loss, suggested_take_profit`。

**⚠️ timestamp 必须是 K 线的 datetime 值**：用 `str(df.iloc[i]["datetime"])`，不要用行号 `i` 或 `df.index[i]`。

---

## 2. 回测（服务器端执行，免费无限次，不占配额）

**当用户要求回测时，立刻执行以下步骤（不要问任何问题）：**

### 步骤一：确保依赖已安装
```bash
pip3 install httpx loguru 2>/dev/null || pip install httpx loguru 2>/dev/null || python3 -m pip install httpx loguru 2>/dev/null
```
只需要 httpx 和 loguru。不需要 numpy/pandas/yfinance，数据在服务器端拉取。如果所有 pip 命令都失败，告诉用户手动安装这两个包。

### 步骤二：提交回测（⚠️ 必须分两个代码块！）

**第一个代码块 — 提交任务：**
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
提交后**立刻告诉用户**任务已提交正在执行。

**第二个代码块 — 等待 15 秒后查询结果：**
```python
import time
time.sleep(15)

import sys
sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

client = QuantAPIClient(timeout=300.0)
bt = client.check_backtest("{job_id}")
if bt["status"] == "completed":
    client.print_metrics(bt)
elif bt["status"] == "running":
    print("⏳ 还在执行中，请稍后再查询...")
else:
    print(f"❌ 回测失败: {bt.get('error', '未知')}")
```
如果 status 是 running，再等 10 秒执行第三个代码块再查一次。

**为什么分两个代码块？** 因为用户需要在提交后立刻看到"任务已提交"的反馈，而不是等整个回测跑完才看到所有输出。

关键：用 `submit_backtest()` + `check_backtest()` 而不是 `run_server_backtest()`。
服务器地址和认证已内置在 api_client.py 中，无需配置。

### ⚠️ 展示规则（必须遵守）

回测完成后，你**必须**把 `print_metrics(bt)` 的完整输出展示给用户。只需调这一个函数，它已包含所有指标和结论。

**禁止**只说一句"总收益为负"这种总结。用户需要看到完整的指标数值。

如果用户随后要求查看"交易记录"，用 `client.print_trades(bt)` 展示（bt 是之前保存的回测结果变量）。不要主动调用，仅用户要求时才调。

---

## 3. 参数优化 / 批量回测（免费不占配额）

当用户说以下任何一种时，**都用 `run_optimization`**：
- "优化参数"、"找最优参数"
- "批量回测"、"批量生成策略"
- "随机生成N个策略然后回测"
- "对比不同参数"、"跑一批"
- "用遗传算法优化"
- "怎么优化这个策略"、"如何改进"、"怎么提高收益/胜率/Sharpe"
- "这个策略怎么调"、"帮我调参"

核心思路：生成一个**带 PARAMS 的策略脚本模板**，把差异点做成参数。服务器自动遍历所有参数组合并排名。

**不要**循环调用 `run_server_backtest` 50 次。**只调一次 `run_optimization`**。

### 搜索方法（method 参数）

| method | 说明 | 适用场景 |
|--------|------|---------|
| `"grid"` | 网格穷举 | 参数少、组合数 ≤ 200 |
| `"genetic"` | 遗传算法（交叉+变异+精英保留+早停）⭐ | 大空间首选，智能搜索 |
| `"bayesian"` | 贝叶斯优化 (TPE)⭐ | 回测耗时长，少量评估快速收敛 |
| `"random"` | 随机采样 | 高维空间快速探索 |
| `"annealing"` | 模拟退火 | 参数空间多峰，跳出局部最优 |
| `"pso"` | 粒子群优化 | 连续参数为主，群体协作 |

**推荐策略**：
- 默认或用户无偏好 → `"genetic"`（通用性最好）
- 用户强调"快速"、"少跑几次就出结果" → `"bayesian"`
- 参数少且用户想穷举 → `"grid"`
- 用户明确说"遗传算法/贝叶斯/模拟退火/粒子群/随机" → 对应 method

### 步骤一：生成带 PARAMS 的策略脚本

脚本中用 `PARAMS['xxx']` 替代硬编码参数值：

```python
PARAMS = {'fast_ema': 20, 'slow_ema': 60, 'rsi_threshold': 50, 'sl_pct': 0.02, 'tp_pct': 0.06}

def generate_signals(mode='backtest', start_date=None, end_date=None):
    fast = PARAMS['fast_ema']
    slow = PARAMS['slow_ema']
    rsi_th = PARAMS['rsi_threshold']
    # ... 使用这些参数计算指标和生成信号 ...
```

### 步骤二：调用优化 API

```python
import sys
sys.path.insert(0, '{baseDir}/scripts')
from api_client import QuantAPIClient

with open('{baseDir}/strategies/xxx_strategy.py', 'r') as f:
    script_content = f.read()

client = QuantAPIClient(timeout=600.0)
result = client.run_optimization(
    script_content=script_content,
    params=[
        {"name": "fast_ema", "type": "int", "low": 5, "high": 30, "step": 5},
        {"name": "slow_ema", "type": "int", "low": 40, "high": 80, "step": 10},
        {"name": "rsi_threshold", "type": "int", "low": 40, "high": 60, "step": 5},
        {"name": "sl_pct", "type": "float", "low": 0.01, "high": 0.05, "step": 0.01},
        {"name": "tp_pct", "type": "float", "low": 0.03, "high": 0.10, "step": 0.01},
    ],
    strategy_name="BTC EMA RSI 优化",
    symbol="BTCUSDT",
    timeframe="4h",
    start_date="2025-01-01",
    end_date="2025-12-31",
    leverage=3,
    fitness_metric="sharpe_ratio",
    max_combinations=200,
    method="genetic",  # grid / genetic / bayesian / random / annealing / pso
)

client.print_optimization(result)
```

服务器会自动替换 PARAMS、逐一回测所有参数组合，返回按 fitness 降序排名的 Top 结果。

### 注意
- `method="grid"`: 控制参数组合数在 200 以内（step 不要太小）
- 其他方法: 无需严格控制组合数，算法自动收敛，`max_combinations` 控制最大评估次数
- fitness_metric 支持：sharpe_ratio、total_return_pct、sortino_ratio、win_rate
- 结果展示必须用 `print_optimization()`，展示完整排名表

---

## 4. 定时监控（占配额，免费 3 个）

用户要求监控时，运行策略脚本的 live 模式（这时候才需要本地运行和占配额）：

```bash
pip3 install numpy pandas httpx loguru yfinance 2>/dev/null || pip install numpy pandas httpx loguru yfinance 2>/dev/null || python3 -m pip install numpy pandas httpx loguru yfinance 2>/dev/null
```

```python
import sys
sys.path.insert(0, '{baseDir}/scripts')
from strategies.xxx_strategy import generate_signals
result = generate_signals(mode='live')
```

---

## 项目结构

```
dex-quant-skill/
├── SKILL.md              ← 你正在读的文件
├── scripts/
│   ├── api_client.py     ← 回测服务器客户端（run_server_backtest）
│   ├── data_client.py    ← K线数据获取（服务器端使用）
│   ├── indicators.py     ← 技术指标库（服务器端使用）
│   ├── machine_auth.py   ← 自动认证
│   └── strategy_runner.py
├── strategies/           ← 生成的策略脚本放这里
└── schemas/
    └── signal_format.json
```
