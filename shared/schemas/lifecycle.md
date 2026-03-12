# 策略生命周期状态机

> 本文档定义了策略从创建到退役的完整生命周期，共 **14 个状态** 及其转换规则。所有 Skill 必须严格遵守此状态机，不得跳过或绕过状态转换。

---

## 状态总览

| # | 状态 | 英文标识 | 所属阶段 | 说明 |
|---|------|---------|---------|------|
| 1 | 草稿 | `draft` | 设计 | 策略刚创建，StrategySpec 尚未完整 |
| 2 | 定义完成 | `spec_ready` | 设计 | StrategySpec 所有必填字段已填写，通过 schema 校验 |
| 3 | 回测就绪 | `backtest_ready` | 回测 | 回测引擎已接收 StrategySpec，BacktestConfig 已生成 |
| 4 | 回测运行中 | `backtest_running` | 回测 | 回测引擎正在执行历史数据回测 |
| 5 | 回测完成 | `backtest_done` | 回测 | 回测执行完毕，结果已保存 |
| 6 | 评审通过 | `review_passed` | 评审 | 评审 Skill 判定策略指标达标 |
| 7 | 评审驳回 | `review_rejected` | 评审 | 评审 Skill 判定策略指标不达标，需修改 |
| 8 | 运行就绪 | `runtime_ready` | 部署 | 策略信号生成器已部署到运行时环境 |
| 9 | 实时监控中 | `monitoring_live` | 监控 | 策略正在生成实时信号并被监控 |
| 10 | 执行已启用 | `execution_enabled` | 执行 | 执行模块已就绪，可接收信号 |
| 11 | 模拟交易中 | `paper_trading` | 执行 | 策略以模拟资金执行交易 |
| 12 | 实盘交易中 | `live_trading` | 执行 | 策略以真实资金执行交易 |
| 13 | 已暂停 | `paused` | 运维 | 策略因风控/人工干预暂停 |
| 14 | 已退役 | `retired` | 终态 | 策略永久停用 |

---

## 状态转换图

```
draft ──────────────► spec_ready
                          │
                          ▼
                    backtest_ready
                          │
                          ▼
                   backtest_running
                          │
                          ▼
                    backtest_done
                       │      │
                       ▼      ▼
              review_passed  review_rejected ──► draft (修改后重新提交)
                    │
                    ▼
              runtime_ready
                    │
                    ▼
             monitoring_live
                    │
                    ▼
           execution_enabled
                 │       │
                 ▼       ▼
          paper_trading  live_trading
                 │       │
                 ▼       ▼
               paused ◄──┘
                 │
                 ▼
              retired
```

---

## 状态转换规则

### 1. `draft` → `spec_ready`

- **前置条件**：StrategySpec 所有必填字段已填写（`name`、`universe`、`timeframe`、`entry_rules`、`exit_rules`、`position_sizing`、`risk_limits`）
- **触发者**：strategy-designer Skill
- **校验**：通过 `strategy_spec.json` schema 校验
- **失败处理**：返回缺失字段清单，保持 `draft`

### 2. `spec_ready` → `backtest_ready`

- **前置条件**：`lifecycle_state == "spec_ready"`，BacktestConfig 已生成
- **触发者**：backtester Skill
- **校验**：回测数据源可用，时间范围有效
- **失败处理**：返回数据不可用原因，保持 `spec_ready`

### 3. `backtest_ready` → `backtest_running`

- **前置条件**：`lifecycle_state == "backtest_ready"`，回测引擎资源就绪
- **触发者**：backtester Skill（自动）
- **校验**：无额外校验
- **失败处理**：回测引擎异常时回退至 `backtest_ready`

### 4. `backtest_running` → `backtest_done`

- **前置条件**：回测执行完毕（正常结束或超时）
- **触发者**：backtester Skill（自动）
- **校验**：回测结果完整性检查
- **失败处理**：记录错误日志，回退至 `backtest_ready`

### 5. `backtest_done` → `review_passed` / `review_rejected`

- **前置条件**：`lifecycle_state == "backtest_done"`，回测结果存在
- **触发者**：reviewer Skill
- **校验**：评审指标阈值判定（Sharpe、最大回撤、胜率等）
- **失败处理**：无——必须给出明确的通过或驳回结论

### 6. `review_rejected` → `draft`

- **前置条件**：用户确认修改策略
- **触发者**：strategy-designer Skill
- **校验**：保留原 `strategy_id`，版本号递增
- **说明**：驳回后回到草稿状态，用户可修改后重新走流程

### 7. `review_passed` → `runtime_ready`

- **前置条件**：`lifecycle_state == "review_passed"` 且 `review_status == "passed"`
- **触发者**：runtime-monitor Skill
- **校验**：信号生成器代码已生成、数据源连接正常
- **❌ 硬性约束**：**未评审通过不得进入 `runtime_ready`**

### 8. `runtime_ready` → `monitoring_live`

- **前置条件**：`lifecycle_state == "runtime_ready"`，信号生成器成功启动
- **触发者**：runtime-monitor Skill
- **校验**：至少收到 1 根完整 K 线数据、信号生成器无异常
- **失败处理**：启动失败回退至 `runtime_ready`

### 9. `monitoring_live` → `execution_enabled`

- **前置条件**：`lifecycle_state == "monitoring_live"`，用户显式确认开启执行权限
- **触发者**：executor Skill
- **校验**：用户授权确认、资金账户可用
- **❌ 硬性约束**：**用户未显式确认不得自动开启执行权限**

### 10. `execution_enabled` → `paper_trading`

- **前置条件**：`lifecycle_state == "execution_enabled"`
- **触发者**：executor Skill
- **校验**：模拟账户余额初始化完成
- **说明**：模拟交易是实盘交易前的必经阶段

### 11. `execution_enabled` → `live_trading`

- **前置条件**：`lifecycle_state == "execution_enabled"` 且已完成至少 1 轮 `paper_trading`
- **触发者**：executor Skill（需用户二次确认）
- **校验**：真实资金账户余额充足、API 权限就绪
- **❌ 硬性约束**：**未开启执行权限不得进入 `live_trading`**
- **❌ 硬性约束**：**未完成模拟交易不建议直接进入 `live_trading`**（可由用户强制跳过）

### 12. `paper_trading` / `live_trading` → `paused`

- **前置条件**：任意执行中状态
- **触发者**：风控触发（自动） / 用户手动暂停 / runtime-monitor Skill 检测异常
- **校验**：记录暂停原因与时间戳
- **说明**：暂停不清除持仓信息，可恢复

### 13. `paused` → `paper_trading` / `live_trading` / `monitoring_live`

- **前置条件**：暂停原因已解除，用户确认恢复
- **触发者**：用户显式操作
- **校验**：根据暂停前状态恢复到对应状态

### 14. 任意状态 → `retired`

- **前置条件**：用户显式确认退役
- **触发者**：用户操作
- **校验**：所有未平仓位已关闭
- **说明**：终态，不可恢复。退役后策略数据保留但不再运行

---

## 硬性约束汇总

| 约束编号 | 规则 | 说明 |
|---------|------|------|
| C-01 | 未评审通过不得进入 `runtime_ready` | 评审是信号生成的前置条件 |
| C-02 | 未开启执行权限不得进入 `live_trading` | 执行权限需用户显式授权 |
| C-03 | 未完成模拟交易不建议进入 `live_trading` | 可由用户强制跳过，但需警告 |
| C-04 | `paused` 状态恢复需用户确认 | 防止自动恢复导致意外损失 |
| C-05 | `retired` 为终态，不可逆转 | 退役前需关闭所有持仓 |
| C-06 | 状态转换不可跳跃 | 必须按顺序逐级推进 |
| C-07 | 每次状态变更需记录审计日志 | 包括变更时间、触发者、原因 |

---

## 各 Skill 状态权限矩阵

| Skill | 可读取状态 | 可写入/推进状态 |
|-------|----------|---------------|
| strategy-designer | `draft`, `review_rejected` | `draft` → `spec_ready`, `review_rejected` → `draft` |
| backtester | `spec_ready`, `backtest_ready`, `backtest_running`, `backtest_done` | `spec_ready` → `backtest_ready` → `backtest_running` → `backtest_done` |
| reviewer | `backtest_done` | `backtest_done` → `review_passed` / `review_rejected` |
| runtime-monitor | `review_passed`, `runtime_ready`, `monitoring_live`, `paused` | `review_passed` → `runtime_ready` → `monitoring_live`, `paused` ↔ `monitoring_live` |
| executor | `monitoring_live`, `execution_enabled`, `paper_trading`, `live_trading`, `paused` | `monitoring_live` → `execution_enabled` → `paper_trading` / `live_trading`, `*` → `paused`, `paused` → 恢复 |
