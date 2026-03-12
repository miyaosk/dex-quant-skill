# AI Quant Agent Platform — Skills

**基于 Skills 的 AI 量化 Agent 平台** — 5 个职责明确的 Skill + 统一策略定义，覆盖从策略构思到实盘执行的完整链路。

> 用户负责表达意图，AI 负责理解和编排，确定性系统负责回测、监控、风控和执行。

---

## 核心理念

这不是一个"大而全的量化 AI"，而是：
- **一个统一聊天入口** — 用户全程用自然语言
- **五个职责明确的 Skills** — 每个只管一段稳定职责
- **一个统一策略定义（StrategySpec）** — 所有 Skill 围绕同一份结构化对象工作
- **研究与实盘分离** — 策略研究和执行层完全隔离
- **AI 做认知，程序做执行** — AI 理解需求、编排流程、解释结果；确定性系统拉数据、跑回测、算信号、做风控、下单

---

## 五个 Skills

```
用户自然语言
     │
     ▼
┌─ 1. strategy-designer ──────────────────────┐
│  自然语言 → 结构化策略定义 (StrategySpec)      │
│  · 提取标的/周期/入场出场规则/仓位/风控        │
│  · 标注缺失字段和未确认假设                    │
│  · 不写代码，只输出策略 spec                   │
└──────────────────┬───────────────────────────┘
                   │ StrategySpec
                   ▼
┌─ 2. backtest-coder ─────────────────────────┐
│  策略定义 → 可回测代码 + 参数配置              │
│  · 保证实现与 spec 严格一致                    │
│  · 数据接口 / 回测引擎 / 遗传寻优              │
│  · 不判断策略好不好（那是 reviewer 的事）       │
└──────────────────┬───────────────────────────┘
                   │ 回测结果
                   ▼
┌─ 3. backtest-reviewer ──────────────────────┐
│  回测结果 → 评审报告 + 准入决策                │
│  · 收益来源 / 成本后表现 / 参数敏感性          │
│  · 过拟合检测 / 样本内外一致性                  │
│  · 输出: approved / paper_trade_first / rejected│
│  · 像严厉的 PM，专门防止伪 alpha               │
└──────────────────┬───────────────────────────┘
                   │ 通过评审的 StrategySpec
                   ▼
┌─ 4. signal-runtime-builder ─────────────────┐
│  策略定义 → 实时/准实时信号监控服务             │
│  · 信号计算 / 状态机 / 去重冷却                │
│  · 能回答"为什么没触发"                        │
│  · 不自行修改策略定义                          │
└──────────────────┬───────────────────────────┘
                   │ SignalEvent
                   ▼
┌─ 5. execution-guard ────────────────────────┐
│  信号 → 风控检查 → 可执行订单                  │
│  · 仓位上限 / 日亏损阈值 / 重复下单防护        │
│  · 冷却期 / 交易所健康 / Kill Switch           │
│  · "有信号" ≠ "允许成交"                       │
└──────────────────────────────────────────────┘
```

---

## 统一策略定义（StrategySpec）

**这是整个系统最核心的对象。** 所有 Skill 都读取或产出它。

```json
{
  "strategy_id": "strat_001",
  "version": "v1.0",
  "name": "btc_4h_breakout_vol_filter",
  "market": "crypto",
  "venue": ["binance_futures"],
  "universe": ["BTCUSDT"],
  "timeframe": "4h",
  "direction": "long_only",
  "features": [
    {"name": "breakout_high", "params": {"lookback": 20}},
    {"name": "volume_ma", "params": {"window": 20}}
  ],
  "entry_rules": ["close > highest(high, 20)", "volume > sma(volume, 20) * 1.5"],
  "exit_rules": ["stop_loss = entry - 2 * atr(14)", "trailing_stop = 2 * atr(14)"],
  "position_sizing": {"mode": "risk_based", "risk_per_trade": 0.005},
  "risk_limits": {"max_position_pct": 0.2, "max_daily_loss": 0.02},
  "review_status": "pending",
  "lifecycle_state": "draft"
}
```

---

## 策略生命周期

```
draft → spec_ready → backtest_ready → backtest_running → backtest_done
                                                              │
                                        ┌─────────────────────┤
                                        ▼                     ▼
                                 review_passed          review_rejected
                                        │
                                        ▼
                                 runtime_ready → monitoring_live → execution_enabled
                                                                         │
                                                    ┌────────────────────┤
                                                    ▼                    ▼
                                             paper_trading          live_trading
                                                    │                    │
                                                    └───────┬────────────┘
                                                            ▼
                                                    paused ←→ retired
```

**硬性约束：**
- 未评审通过 → 不得进入 `runtime_ready`
- 未开启执行权限 → 不得进入 `live_trading`
- 风控重大异常 → 任何时候可打回 `paused`

---

## 用户交互流程

### 研究模式

```
用户: "我想做一个 ETH 4h 趋势策略，减少震荡假突破"
  AI: [strategy-designer] 整理成策略定义 → 用户确认

用户: "生成回测代码，跑 2022-2025"
  AI: [backtest-coder] 生成代码 → 执行回测

用户: "表现怎么样？能上线吗？"
  AI: [backtest-reviewer] 评审 → 准入报告
```

### 监控模式

```
用户: "先部署监控，不自动下单"
  AI: [signal-runtime-builder] 部署信号服务

用户: "现在有信号吗？"
  AI: "breakout 条件满足，但成交量过滤未满足，所以未触发"
```

### 执行模式

```
  AI: "ETH 4h 已触发开多信号。风控检查通过。建议仓位 15%。是否执行？"
用户: "执行，但只开 10%"
  AI: [execution-guard] 风控通过 → 提交订单
```

---

## 项目结构

```
dex-quant-skill/
├── README.md
├── requirements.txt
├── .gitignore
│
├── shared/schemas/
│   ├── strategy_spec.json         # StrategySpec 统一模板
│   ├── data_objects.md            # 5 个核心数据对象定义
│   └── lifecycle.md               # 策略生命周期状态机
│
├── strategy-designer/
│   ├── SKILL.md                   # Skill 1: 自然语言 → 策略定义
│   ├── references/
│   │   ├── spec-schema.md         # StrategySpec 字段详解
│   │   └── examples.md            # 5 个策略示例
│   └── assets/
│       └── strategy_template.json # 空白模板
│
├── backtest-coder/
│   ├── SKILL.md                   # Skill 2: 策略定义 → 回测代码
│   ├── references/
│   │   ├── data-sources.md        # 数据源 API 文档
│   │   ├── engine-spec.md         # 回测引擎规格
│   │   └── cost-models.md         # 成本模型
│   ├── scripts/
│   │   ├── data_client.py         # 多源数据客户端
│   │   ├── backtest_engine.py     # 回测引擎
│   │   ├── indicators.py          # 技术指标库
│   │   └── optimizer.py           # 遗传寻优 + 网格搜索
│   └── assets/templates/
│       └── perpetual_strategy.py  # 永续合约策略模板
│
├── backtest-reviewer/
│   ├── SKILL.md                   # Skill 3: 回测评审 + 准入判断
│   ├── references/
│   │   ├── review-checklist.md    # 10 维评审清单
│   │   └── metrics-guide.md       # 指标解读指南
│   └── assets/
│       └── review_template.json   # ReviewReport 模板
│
├── signal-runtime-builder/
│   ├── SKILL.md                   # Skill 4: 策略 → 实时信号监控
│   ├── references/
│   │   ├── runtime-spec.md        # 运行时规格
│   │   └── state-machine.md       # 信号状态机
│   └── scripts/
│       └── signal_runtime.py      # 信号运行时实现
│
└── execution-guard/
    ├── SKILL.md                   # Skill 5: 信号 → 风控 + 执行
    ├── references/
    │   ├── risk-rules.md          # 10 项风控规则
    │   └── order-spec.md          # 订单规格
    └── scripts/
        └── risk_checker.py        # 风控检查器
```

---

## 为什么拆成 5 个 Skill

| 问题 | 解决方式 |
|------|---------|
| 上下文太杂 | 每个 Skill 只管一段职责，不会又理解策略又写代码又盯盘又管风控 |
| 出错难定位 | 策略逻辑错？实现错？数据错？还是执行层拦住了？每层独立可追溯 |
| 复用差 | 换交易所、换回测框架、换通知系统，只改一个 Skill |
| 安全性 | 研究和执行完全隔离，Agent 不会在"创意模式"下触发真单 |
| 坏策略上线 | backtest-reviewer 独立评审，专门防止伪 alpha |

---

## 开发节奏建议

| 阶段 | 内容 | 目标 |
|------|------|------|
| Phase 0 | 定义 StrategySpec + 状态机 + 风控矩阵 | 统一语言 |
| Phase 1 | strategy-designer + backtest-coder | 从聊天到回测 |
| Phase 2 | backtest-reviewer + review gate | 评审闭环 |
| Phase 3 | signal-runtime-builder + 告警 | 实时监控 |
| Phase 4 | execution-guard + 人工确认 + kill switch | 可控执行 |

---

## 技术栈

| 组件 | 技术 |
|------|------|
| HTTP 客户端 | httpx |
| 数据处理 | pandas + numpy |
| 美股/商品 | yfinance |
| 日志 | loguru |
| Python 版本 | 3.10+ |

---

## 数据源

| 数据源 | 覆盖 | API Key | 历史 |
|--------|------|---------|------|
| Binance Futures | 永续合约 K线/资金费率/持仓量/合约信息 | 不需要 | 无限 |
| Binance Spot | 现货 K线 | 不需要 | 无限 |
| CoinGecko | 代币价格 | 不需要 | 365 天 |
| Yahoo Finance | 美股/大宗商品/贵金属 | 不需要 | 10-30 年 |
| DeFi Llama | TVL/手续费 | 不需要 | 全历史 |

---

## License

MIT
