---
name: dex-quant-skill
description: >
  加密货币量化交易 AI Skill 技能包。
  用户用自然语言描述交易规则 → AI 生成可运行的策略脚本 → 回测验证 → 实时监控执行。
  支持技术指标、社交媒体、链上数据等多种信号源。
---

# DEX Quant Skill — 加密货币量化交易技能包

## 一句话说明

用户用自然语言说 **"MACD 金叉就买 BTC"** 或 **"Elon Musk 发推提到 Doge 就买"**，
AI 自动生成可运行的策略脚本，支持回测验证和实时交易。

---

## 3 个 Skill

```
 ┌─────────────────┐     ┌─────────────┐     ┌──────────────────┐
 │  策略制作         │     │  回测        │     │  监控执行          │
 │  strategy-maker  │────▶│  backtester  │────▶│  monitor-executor │
 │                  │     │              │     │                   │
 │  用户说想法       │     │  跑历史数据   │     │  跑脚本+出信号     │
 │  → AI 生成脚本   │     │  → 看能不能赚 │     │  → 风控检查        │
 │  (.py / .ts)    │     │  → 给评价     │     │  → 执行/拦截       │
 └─────────────────┘     └─────────────┘     └──────────────────┘
```

| Skill | 职责 | 输入 | 输出 |
|-------|------|------|------|
| **strategy-maker** | 把自然语言变成可运行脚本 | 用户想法 | `.py` / `.ts` 策略脚本 |
| **backtester** | 调 Server 回测验证策略 | 策略脚本 → 信号 → Server | 绩效报告 + 上线建议 |
| **monitor-executor** | 实时运行脚本 + 执行交易 | 策略脚本 + 运行模式 | 买/卖信号 + 交易记录 |

---

## 策略 = 脚本

在这个系统里，**策略就是一个可运行的脚本**。脚本负责：

1. **获取数据**（K 线、推特、新闻、链上数据...）
2. **评估条件**（MACD 金叉？RSI 超卖？KOL 发推了？）
3. **输出信号**（某个币该买还是该卖）

脚本可以用 **Python** 或 **TypeScript** 编写。

### 信号输出格式

所有策略脚本输出统一的 JSON 格式：

```json
{
  "strategy_name": "BTC MACD 趋势跟踪",
  "signals": [
    {
      "symbol": "BTCUSDT",
      "action": "buy",
      "confidence": 0.85,
      "reason": "MACD 金叉 + 成交量放大",
      "source_type": "technical"
    }
  ]
}
```

详细格式定义见 `shared/schemas/signal_format.json`。

---

## 条件规则类型

策略可以使用以下任意类型的条件，也可以组合使用：

| 类型 | 示例 | 数据来源 |
|------|------|---------|
| **技术指标** | MACD 金叉、RSI 超卖、均线交叉 | K 线 OHLCV |
| **社媒信号** | KOL 发推、新闻情绪、Reddit 热度 | Twitter API / 新闻 API |
| **链上数据** | 资金费率过高、鲸鱼转账、Gas 异常 | Binance API / 区块链浏览器 |
| **大盘联动** | BTC 涨了山寨跟、纳指暴跌币圈跌 | 交易所 / yfinance |
| **时间条件** | 每 4h 检查一次、每天 UTC 8 点 | 定时触发 |

---

## 执行模式

策略脚本可以在两种环境下运行：

| 模式 | 说明 | 适合场景 |
|------|------|---------|
| **本地运行** | 脚本在用户自己的电脑上跑 | 开发调试、隐私敏感、免费使用 |
| **服务器运行** | 脚本上传到服务器通过 API 执行 | 7×24 运行、不占本地资源 |

---

## 快速开始

### 场景 1：从零创建技术指标策略

```
用户: "帮我做一个 BTC 的策略，MACD 金叉就买，死叉就卖，加上成交量确认"
AI:   → 使用 strategy-maker 生成 btc_macd_strategy.py
      → 建议用 backtester 跑 2024 年回测验证
      → 通过后用 monitor-executor 部署实时监控
```

### 场景 2：社媒 + 技术的混合策略

```
用户: "帮我监控推特，如果有大 V 喊单 SOL 并且 RSI 低于 40 就买"
AI:   → 使用 strategy-maker 生成混合策略脚本
      → 技术指标部分可回测，社媒部分标注为"实时验证"
      → 部署后同时监控推特和价格
```

### 场景 3：回测已有策略

```
用户: "把我这个策略跑一下 2024 年全年的 ETH 数据"
AI:   → 本地运行脚本产出信号
      → 调 dex-quant-server API 发送信号
      → Server 拉 K 线（带缓存）+ 回测引擎模拟
      → 返回绩效报告 + 结论（通过/先模拟/驳回）
```

---

## 项目结构

```
dex-skill/
├── SKILL.md                          ← 你在这里
├── strategy-maker/                   ← Skill 1: 策略制作
│   ├── SKILL.md
│   ├── assets/templates/
│   │   ├── technical_strategy.py     ← 技术指标策略模板
│   │   ├── social_strategy.py        ← 社媒策略模板
│   │   └── mixed_strategy.py         ← 混合策略模板
│   └── references/
│       ├── conditions-guide.md       ← 条件规则指南
│       └── examples.md               ← 示例策略
├── backtester/                       ← Skill 2: 回测（调 dex-quant-server）
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── api_client.py             ← Server API 客户端（核心）
│   │   ├── data_client.py            ← 本地数据获取（策略脚本生成信号用）
│   │   ├── backtest_engine.py        ← 本地回测引擎（备用）
│   │   ├── indicators.py             ← 技术指标库（12 种指标）
│   │   └── optimizer.py              ← 参数优化器
│   ├── assets/
│   │   └── review_template.json      ← 评审模板
│   └── references/
│       ├── data-sources.md
│       ├── engine-spec.md
│       ├── cost-models.md
│       ├── metrics-guide.md
│       └── review-checklist.md
├── monitor-executor/                 ← Skill 3: 监控执行
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── risk_checker.py           ← 11 项风控检查 + Kill Switch
│   │   └── signal_runtime.py         ← 信号运行时引擎
│   └── references/
│       ├── risk-rules.md
│       ├── deployment-guide.md
│       ├── runtime-spec.md
│       └── state-machine.md
└── shared/
    └── schemas/
        ├── signal_format.json        ← 信号标准输出格式
        ├── strategy_spec.json        ← 策略元数据（保留）
        ├── data_objects.md
        └── lifecycle.md
```

---

## 安装

```bash
# 克隆到本地
git clone <repo-url> dex-skill

# 安装 Python 依赖
pip install -r requirements.txt

# 安装到 Cursor/Codex
bash install.sh
```

## 依赖

```
httpx>=0.27
numpy>=1.24
pandas>=2.0
loguru>=0.7
yfinance>=0.2
```
