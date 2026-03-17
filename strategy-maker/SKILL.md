---
name: strategy-maker
description: >
  将用户的自然语言交易想法转化为一个**可运行的策略脚本**（Python 或 TypeScript）。
  脚本接入数据源、评估条件规则、输出买/卖信号。
  Use when user asks to create, design, or modify a quantitative trading strategy.
---

# Strategy Maker — 策略制作

## 目标

将用户用自然语言描述的交易规则，生成一个**可直接运行的脚本文件**（`.py` 或 `.ts`）。

脚本是策略的唯一载体——它负责获取数据、计算指标/信号源、评估条件、输出买卖信号。
下游的回测 Skill 和监控执行 Skill 都以这个脚本为输入。

**核心公式：** `用户想法 → 条件规则 → 可运行脚本 → 买/卖信号`

---

## 触发条件

当用户表达以下意图时激活本 Skill：

- "帮我做一个 BTC 的趋势策略"
- "MACD 金叉就买，死叉就卖"
- "如果 Elon Musk 发了关于 Doge 的推特就买"
- "RSI 超过 70 就卖，低于 30 就买，再加上推特情绪过滤"
- "帮我写一个监控 SOL 大户钱包动向的策略"
- 任何涉及策略创建、修改、定义交易规则的请求

---

## 输入

| 输入项 | 是否必须 | 说明 |
|--------|---------|------|
| 用户想法描述 | **必须** | 自然语言的交易规则，可以是一句话也可以是详细的逻辑 |
| 目标币种 | **必须** | 要交易哪些币（BTCUSDT、ETHUSDT...） |
| 脚本语言偏好 | 可选 | Python（默认）或 TypeScript |
| 已有脚本 | 可选 | 用户希望在已有策略脚本基础上修改 |

---

## 输出

| 输出项 | 说明 |
|--------|------|
| **策略脚本** | 一个可直接运行的 `.py` 或 `.ts` 文件 |
| 策略说明 | 这个脚本做了什么、用了哪些条件、数据源 |
| 依赖说明 | 脚本需要安装哪些包 |
| 运行方式 | 如何执行这个脚本（命令行参数、环境变量等） |

---

## 条件规则体系

策略脚本的核心是**条件规则**——什么情况下买，什么情况下卖。
条件可以来自以下数据源的任意组合：

### 1. 技术指标条件

基于 K 线价格和成交量计算的经典指标：

| 指标 | 条件示例 | 信号 |
|------|---------|------|
| MACD | MACD 金叉（DIF 上穿 DEA） | 买 |
| MACD | MACD 死叉（DIF 下穿 DEA） | 卖 |
| RSI | RSI < 30（超卖） | 买 |
| RSI | RSI > 70（超买） | 卖 |
| 均线交叉 | SMA(10) 上穿 SMA(30) | 买 |
| 布林带 | 价格触及下轨 | 买 |
| ATR | 波动率放大 + 方向确认 | 买/卖 |
| 成交量 | 放量突破前高 | 买 |
| KDJ | K/D 金叉且 J < 20 | 买 |

支持的指标库：SMA, EMA, RSI, MACD, Bollinger Bands, ATR, KDJ, OBV, VWAP 等。
详见 `backtester/scripts/indicators.py`。

### 2. 社交媒体条件

监控社交平台的信号源：

| 来源 | 条件示例 | 信号 |
|------|---------|------|
| Twitter/X | 某 KOL 发了含 "$BTC" 的推文 | 买 |
| Twitter/X | "bearish" 情绪在 1h 内暴增 | 卖 |
| 新闻 | CoinDesk/CoinTelegraph 发布利好新闻 | 买 |
| 新闻 | 监管相关负面新闻 | 卖 |
| Reddit | 某 subreddit 提及量暴增 | 关注 |
| Telegram | 特定频道发出交易信号 | 买/卖 |

> 社媒条件脚本需要调用外部 API（Twitter API、新闻聚合 API 等），
> 模板中会预留接口，用户填入自己的 API Key。

### 3. 链上数据条件

来自交易所、DEX 和链上浏览器的数据（全部有免费 API）：

| 数据 | 条件示例 | 信号 | 数据源 | Key |
|------|---------|------|--------|-----|
| 资金费率 | funding rate > 0.1%（多头过热） | 卖 | Binance API | 无需 |
| 持仓量 | OI 突然增加 20% | 关注 | Binance API | 无需 |
| DEX 交易量 | 某 pair 交易量暴增 | 买 | DEX Screener API | 无需 |
| DEX 流动性 | 流动性突然抽走 | 卖 | DEX Screener API | 无需 |
| 鲸鱼大额转账 | 大户转入交易所 | 卖 | Whale Alert API | 免费 Key |
| 钱包持仓/交易 | 某地址大量买入 | 买 | Etherscan / DeBank | 免费 Key |
| Gas 费 | Gas 异常飙升（链上拥堵） | 关注 | Owlracle / Etherscan | 免费 Key |
| DeFi TVL | 协议 TVL 持续增长 | 买 | DeFi Llama API | 无需 |

> **无需 Key** = 直接调用，无需注册
> **免费 Key** = 免费注册后获取 Key，有免费调用额度

### 4. 大盘/跨资产条件

跨市场联动信号：

| 数据 | 条件示例 | 信号 |
|------|---------|------|
| BTC 走势 | BTC 日线收阳 → 山寨币跟涨 | 买山寨 |
| 美股 | 纳指暴跌 → 币圈联动下跌 | 卖 |
| 黄金 | 金价创新高 → 避险情绪上升 | 卖 |
| DeFi TVL | 协议 TVL 持续增长 | 买 |

### 5. 时间条件

| 条件 | 示例 |
|------|------|
| 固定时间触发 | 每天 UTC 8:00 检查一次 |
| 周期间隔 | 每 4 小时执行一次 |
| 事件驱动 | 新 K 线收盘时执行 |

### 条件组合

多个条件可以用 AND / OR 组合：

```
买入条件 = (MACD金叉 AND 成交量放大) OR (RSI<25 AND 推特情绪转正)
卖出条件 = (MACD死叉) OR (RSI>80) OR (鲸鱼大量转入交易所)
```

---

## 脚本规范

所有生成的策略脚本必须遵循统一的输出格式，以便回测和监控执行 Skill 能够对接。

### 标准信号输出格式

脚本运行后必须输出 JSON 格式的信号列表：

```json
{
  "strategy_name": "BTC MACD 趋势跟踪",
  "strategy_version": "v1.0",
  "generated_at": "2026-03-12T12:00:00Z",
  "signals": [
    {
      "symbol": "BTCUSDT",
      "action": "buy",
      "confidence": 0.85,
      "reason": "MACD 金叉 + 成交量大于 20 日均量 1.5 倍",
      "price_at_signal": 68500.0,
      "suggested_stop_loss": 66000.0,
      "suggested_take_profit": 74000.0,
      "source_type": "technical",
      "metadata": {
        "macd_dif": 150.5,
        "macd_dea": 120.3,
        "volume_ratio": 1.8,
        "rsi": 58
      }
    }
  ]
}
```

### 信号字段说明

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `symbol` | string | ✅ | 交易对（如 BTCUSDT） |
| `action` | string | ✅ | `buy` / `sell` / `close` / `hold` |
| `confidence` | float | ✅ | 信心度 0-1 |
| `reason` | string | ✅ | 人类可读的触发原因 |
| `price_at_signal` | float | 建议 | 信号触发时的价格 |
| `suggested_stop_loss` | float | 可选 | 建议止损价 |
| `suggested_take_profit` | float | 可选 | 建议止盈价 |
| `source_type` | string | ✅ | `technical` / `social` / `onchain` / `mixed` |
| `metadata` | object | 可选 | 触发条件的具体数值 |

### 脚本入口约定

**Python 脚本：**

```python
# 策略脚本必须实现 generate_signals() 函数
def generate_signals(mode="live", start_date=None, end_date=None):
    """
    mode: "live" 实时模式 / "backtest" 回测模式
    start_date/end_date: 回测模式下的时间范围
    返回: 标准信号 JSON
    """
    ...

if __name__ == "__main__":
    import json, sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"
    result = generate_signals(mode=mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))
```

**TypeScript 脚本：**

```typescript
// 策略脚本必须导出 generateSignals 函数
export async function generateSignals(
  mode: "live" | "backtest" = "live",
  startDate?: string,
  endDate?: string
): Promise<SignalOutput> {
  // ...
}
```

---

## 工作流程

### 第 1 步：理解用户想法

从用户的自然语言中提取：

- **目标币种**：要交易哪些币
- **买入条件**：什么情况下买
- **卖出条件**：什么情况下卖
- **数据源**：需要技术指标？社媒数据？链上数据？
- **时间周期**：多久检查一次（1分钟/1小时/4小时/1天）
- **风险偏好**：止损止盈设置

### 第 2 步：追问缺失信息

> **必须追问的（不可用默认值代替）：**
> - 目标币种为空时
> - 买入条件为空时
> - 卖出条件为空时

> **可以用默认值的：**
> - 脚本语言（默认 Python）
> - 时间周期（默认 4h）
> - 止损止盈（可以不设）

### 第 3 步：选择模板

根据条件类型选择合适的脚本模板：

| 条件类型 | 模板 | 说明 |
|---------|------|------|
| 纯技术指标 | `templates/technical_strategy.py` | 最常用，只需 K 线数据 |
| 纯社媒信号 | `templates/social_strategy.py` | 需要 Twitter/新闻 API |
| 混合条件 | `templates/mixed_strategy.py` | 技术 + 社媒 + 链上 |

### 第 4 步：填充逻辑，生成脚本

基于模板，将用户的条件规则翻译成代码：

1. 设置数据获取逻辑（K 线、社媒 API、链上数据等）
2. 实现条件判断（指标阈值、关键词匹配、事件检测等）
3. 实现信号生成（buy/sell/hold）
4. 填入标准输出格式
5. 添加必要的错误处理和日志

### 第 5 步：输出并说明

向用户输出：

1. **完整的脚本文件** — 保存到 `strategies/` 目录，**必须明确告知用户脚本保存路径**
2. **策略说明**：用了哪些条件、逻辑是什么
3. **依赖安装**：`pip install xxx` 或 `npm install xxx`
4. **运行命令**：`python strategies/my_strategy.py backtest 2024-01-01 2024-12-31`（运行后用户选择本地回测或服务器回测）
5. **下一步建议**：拿去回测（backtester Skill）或直接部署监控（monitor-executor Skill）

---

## 禁止事项

| 禁止行为 | 原因 |
|---------|------|
| ❌ 生成不可运行的伪代码 | 脚本必须能直接执行 |
| ❌ 硬编码 API Key | API Key 必须通过环境变量或配置文件传入 |
| ❌ 执行回测 | 回测是 backtester Skill 的职责 |
| ❌ 部署监控/下单 | 执行是 monitor-executor Skill 的职责 |
| ❌ 在脚本中直接调用交易所下单 API | 脚本只负责输出信号，不负责执行 |
| ❌ 忽略错误处理 | 网络请求、数据缺失等异常必须优雅处理 |

---

## 参考资源

- **脚本模板（技术指标）**：`strategy-maker/assets/templates/technical_strategy.py`
- **脚本模板（社媒）**：`strategy-maker/assets/templates/social_strategy.py`
- **脚本模板（混合）**：`strategy-maker/assets/templates/mixed_strategy.py`
- **条件规则指南**：`strategy-maker/references/conditions-guide.md`
- **示例策略**：`strategy-maker/references/examples.md`
- **信号格式定义**：`shared/schemas/signal_format.json`
- **技术指标库**：`backtester/scripts/indicators.py`
- **数据获取**：`backtester/scripts/data_client.py`
