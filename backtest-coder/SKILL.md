---
name: backtest-coder
description: >
  Convert a StrategySpec into runnable backtest implementation. Generates strategy code, parameter config,
  data mapping, backtest runner, and performance output. Use when user asks to generate backtest code,
  run backtests, implement a strategy, or test strategy performance.
  将策略定义转成可回测的代码实现，包含策略代码、参数配置、数据接口、回测脚本。
---

# Backtest Coder — 策略规格 → 可运行回测代码

## 目标

将 StrategySpec（策略规格定义）转化为**可复现的回测实现**，输出可直接运行的策略代码、参数配置、回测脚本和绩效报告。

---

## 必需输入

| 输入 | 说明 | 来源 |
|------|------|------|
| **StrategySpec** | 策略逻辑定义（信号规则、开平仓条件、风控参数） | 用户提供或上游 skill 生成 |
| **BacktestConfig** | 回测配置（初始资金、杠杆、手续费、滑点、保证金模式） | 用户指定或使用默认值 |
| **数据字段映射** | 数据源字段到策略变量的映射关系 | 参考 [references/data-sources.md](references/data-sources.md) |
| **框架模板** | 策略代码模板 | [assets/templates/perpetual_strategy.py](assets/templates/perpetual_strategy.py) |

---

## 输出产物

| 产物 | 说明 |
|------|------|
| **策略代码** | 完整的策略实现（信号计算、开平仓逻辑、风控） |
| **参数配置** | JSON 格式的外部化参数（可独立修改，无需改代码） |
| **运行脚本** | 一键执行回测的 runner 脚本 |
| **绩效输出格式** | 标准化的绩效指标 + 交易日志 + 净值曲线 |
| **运行日志** | 回测过程的详细日志（loguru 格式） |

---

## 工作流程

### 步骤 1：解析 StrategySpec

- 提取策略名称、交易标的、时间框架
- 提取信号规则（指标 + 条件）
- 提取风控参数（止损/止盈/最大持仓）
- 确认数据需求（K线周期、是否需要资金费率等）

### 步骤 2：配置数据源

- 根据交易标的选择数据接口（参考 [references/data-sources.md](references/data-sources.md)）
- 构建数据拉取代码（使用 `scripts/data_client.py`）
- 映射数据字段到策略变量

### 步骤 3：构建指标计算

- 使用 `scripts/indicators.py` 中的向量化指标
- 所有指标参数外部化到配置文件
- 确保计算结果与 spec 定义一致

### 步骤 4：实现交易逻辑

- 编写信号判断代码（严格按 spec 实现）
- 实现开仓/平仓逻辑（使用 `scripts/backtest_engine.py`）
- 接入止损/止盈/资金费率结算

### 步骤 5：配置回测引擎

- 设置 BacktestConfig（杠杆、保证金模式、手续费、滑点）
- 手续费和滑点必须显式配置（参考 [references/cost-models.md](references/cost-models.md)）
- 启用/禁用资金费率结算和强平检查

### 步骤 6：执行回测

- 逐 bar 运行策略
- 记录所有交易和净值变化
- 输出绩效指标

### 步骤 7：输出结果

- 调用 `engine.get_result()` 获取完整结果
- 格式化输出绩效摘要（`BacktestEngine.format_summary()`）
- 导出交易日志和净值曲线

---

## 禁止事项

| 禁止 | 理由 |
|------|------|
| **修改策略逻辑** | Coder 只负责实现，不改变 spec 定义的交易规则 |
| **引入新 alpha** | 不添加 spec 中未定义的信号或因子 |
| **判断策略是否值得上线** | 策略评审是 reviewer 的职责 |
| **硬编码参数** | 所有参数必须外部化到配置文件 |
| **忽略成本** | 手续费、滑点、资金费率必须显式建模 |

---

## 最终检查清单

- [ ] 实现与 StrategySpec 严格一致（逐条对照信号规则）
- [ ] 所有参数已外部化到 JSON 配置
- [ ] 手续费模型已显式配置（参考 [references/cost-models.md](references/cost-models.md)）
- [ ] 滑点模型已显式配置
- [ ] 资金费率结算已启用（永续合约策略）
- [ ] 强平检查已启用
- [ ] 止损/止盈逻辑已实现（如 spec 要求）
- [ ] 代码可独立运行（`python strategy.py` 即可执行）
- [ ] 输出包含完整绩效指标和交易日志

---

## 脚本参考

| 脚本 | 功能 | 何时使用 |
|------|------|----------|
| [scripts/data_client.py](scripts/data_client.py) | 多源数据客户端 | 拉取 K 线、资金费率、持仓量等数据 |
| [scripts/backtest_engine.py](scripts/backtest_engine.py) | 永续合约回测引擎 | 执行策略回测（保证金/强平/资金费率） |
| [scripts/indicators.py](scripts/indicators.py) | 技术指标库 | 计算 SMA/EMA/RSI/MACD/布林带等 |
| [scripts/optimizer.py](scripts/optimizer.py) | 参数优化器 | 遗传算法 + 网格搜索优化策略参数 |

---

## 支持的数据源

| 数据源 | 数据类型 | 历史深度 | 是否需要 Key |
|--------|----------|----------|-------------|
| **Binance Futures** | K线、资金费率、持仓量 | 无限制（K线/费率），30天（OI/多空比） | 否 |
| **Binance Spot** | 现货 K 线 | 无限制 | 否 |
| **CoinGecko** | 代币价格 | 365 天（免费版） | 否 |
| **Yahoo Finance** | 美股、大宗商品、贵金属 | 10-30 年 | 否 |
| **DeFi Llama** | TVL、手续费 | 协议上线至今 | 否 |

详细 API 规格见 [references/data-sources.md](references/data-sources.md)

---

## 回测引擎能力

| 能力 | 说明 |
|------|------|
| **保证金模式** | 逐仓（isolated）+ 全仓（cross） |
| **杠杆** | 1x - 125x |
| **资金费率结算** | 每 8h，使用真实历史数据 |
| **强制平仓** | 保证金率 ≤ 维持保证金率时触发 |
| **止损/止盈** | bar 内 high/low 判断触发 |
| **滑点** | 固定 bps 模型 |
| **手续费** | Maker 0.02% / Taker 0.05% |

保证金和强平计算公式见 [references/engine-spec.md](references/engine-spec.md)

---

## 参数优化

| 方法 | 适用场景 | 说明 |
|------|----------|------|
| **遗传算法优化** | 参数空间大（>1000 种组合） | 锦标赛选择 + 均匀交叉 + 变异 + 精英保留 + 早停 |
| **网格搜索** | 参数空间小（≤1000 种组合） | 穷举所有组合 |

详见 [scripts/optimizer.py](scripts/optimizer.py)

---

## 参考文档

| 文档 | 内容 | 何时阅读 |
|------|------|----------|
| [references/data-sources.md](references/data-sources.md) | 各 API 端点、参数、限流、数据限制 | 配置数据源时 |
| [references/engine-spec.md](references/engine-spec.md) | 保证金/杠杆/资金费率/强平计算公式 | 配置引擎或调试结果时 |
| [references/cost-models.md](references/cost-models.md) | 手续费/滑点/资金费率成本模型 | 配置成本参数时 |

---

## 策略模板

| 模板 | 适用场景 |
|------|----------|
| [assets/templates/perpetual_strategy.py](assets/templates/perpetual_strategy.py) | 永续合约策略完整流程模板 |
