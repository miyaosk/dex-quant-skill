# 部署指南

> 策略脚本的两种运行方式：本地运行 vs 服务器运行。

---

## 方式一：本地运行

### 单次执行

```bash
python my_strategy.py live --once
```

适合手动检查、调试。

### 定时运行（推荐）

**macOS / Linux — 使用 crontab：**

```bash
# 每 4 小时执行一次
crontab -e
0 */4 * * * cd /path/to/strategy && python my_strategy.py live >> /path/to/logs/strategy.log 2>&1
```

**Windows — 使用任务计划程序：**

1. 打开"任务计划程序"
2. 创建基本任务
3. 设置触发器为"每隔 4 小时"
4. 操作设为运行 `python my_strategy.py live`

### 持续运行（守护进程）

```bash
# 使用 nohup 后台运行
nohup python my_strategy.py live --interval 4h > strategy.log 2>&1 &

# 查看运行状态
ps aux | grep my_strategy

# 停止运行
kill <pid>
```

### 资源占用参考

| 策略类型 | CPU | 内存 | 网络 |
|---------|-----|------|------|
| 纯技术指标 | < 5% | < 100MB | 极少（每周期一次 API 请求） |
| 技术 + 社媒 | 5-15% | 100-300MB | 中等（社媒 API 频繁调用） |
| 复杂混合策略 | 10-30% | 200-500MB | 较多（多数据源并行） |

---

## 方式二：服务器运行

通过服务器提供的代码执行 API 运行策略脚本。

### API 接口（待服务端实现）

**上传并启动策略：**

```
POST /api/v1/strategy/deploy
Content-Type: application/json

{
  "script_content": "<脚本内容>",
  "language": "python",
  "interval": "4h",
  "mode": "monitor",
  "params": {
    "symbols": ["BTCUSDT"],
    "leverage": 3
  }
}
```

**查看运行状态：**

```
GET /api/v1/strategy/{strategy_id}/status
```

**获取最新信号：**

```
GET /api/v1/strategy/{strategy_id}/signals
```

**停止策略：**

```
POST /api/v1/strategy/{strategy_id}/stop
```

### 服务器优势

- 7×24 小时运行，不怕断电断网
- 不占用本地 CPU / 内存
- 统一的日志和监控
- 支持多策略并行

### 服务器限制

- 脚本代码需要上传到服务器（注意隐私）
- 可能有执行时间和资源限制
- 需要网络连接才能查看状态

---

## 运行模式

| 模式 | 说明 | 自动下单 |
|------|------|---------|
| `monitor` | 只监控出信号，不自动下单 | ❌ |
| `live` | 出信号后经风控检查自动下单 | ✅ |

建议新策略先用 `monitor` 模式运行 1-2 周，确认信号质量后再切换到 `live`。
