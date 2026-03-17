"""
信号运行时引擎

将通过评审的 StrategySpec 转化为实时信号监控服务。
负责指标计算、规则匹配、去重冷却、状态管理和信号生成。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# ─────────────────────────── 常量 ───────────────────────────

TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}

DEFAULT_DEDUP_MULTIPLIER = 3       # 去重窗口 = N × timeframe
DEFAULT_COOLDOWN_MULTIPLIER = 2    # 冷却期 = N × timeframe
DEFAULT_HEARTBEAT_INTERVAL = 10    # 每 10 个 bar 输出心跳
STATE_FILE_NAME = "signal_state.json"


# ─────────────────────────── 枚举 ───────────────────────────

class SignalState(str, Enum):
    """信号引擎的状态机状态"""
    IDLE = "idle"
    WATCHING = "watching"
    ENTRY_TRIGGERED = "entry_triggered"
    POSITION_OPEN = "position_open"
    EXIT_TRIGGERED = "exit_triggered"
    COOLDOWN = "cooldown"


class SignalType(str, Enum):
    """信号类型"""
    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"
    EXIT_ALL = "exit_all"
    ADJUST_POSITION = "adjust_position"


# ─────────────────────────── 数据类 ───────────────────────────

@dataclass
class SignalEvent:
    """
    信号事件——遵循 shared/schemas/data_objects.md 中的 SignalEvent 定义。
    """
    signal_id: str
    strategy_id: str
    timestamp: str
    symbol: str
    timeframe: str
    signal_type: str
    strength: float
    price_at_signal: float
    triggered_by: list[str]
    feature_snapshot: dict[str, Any]
    suggested_quantity: Optional[float] = None
    suggested_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    confidence: Optional[float] = None
    ttl_seconds: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConditionEvaluation:
    """单条规则条件的评估结果"""
    condition: str
    met: bool
    current_values: dict[str, Any]
    distance: str


@dataclass
class RuleEvaluation:
    """单条规则的完整评估"""
    rule_id: str
    rule_description: str
    overall_met: bool
    conditions: list[ConditionEvaluation]


@dataclass
class NoSignalExplanation:
    """"为什么没有信号"的完整解释"""
    timestamp: str
    symbol: str
    feature_snapshot: dict[str, Any]
    rule_evaluations: list[RuleEvaluation]
    summary: str


# ─────────────────────────── 核心引擎 ───────────────────────────

class SignalRuntime:
    """
    信号运行时引擎

    职责：
    1. 加载策略定义 (StrategySpec)
    2. 接收 bar 数据并计算指标
    3. 检查入场/出场规则
    4. 管理状态机 (idle → watching → entry_triggered → position_open → exit_triggered → cooldown)
    5. 去重和冷却控制
    6. 生成 SignalEvent
    7. 持久化/恢复状态
    """

    def __init__(self, state_dir: str = ".") -> None:
        # 策略配置
        self._spec: dict = {}
        self._strategy_id: str = ""
        self._timeframe: str = "1h"
        self._bar_seconds: int = 3600
        self._universe: list[str] = []

        # 每个标的的独立状态
        self._states: dict[str, SignalState] = {}
        self._last_signal_time: dict[str, datetime] = {}
        self._last_exit_time: dict[str, datetime] = {}
        self._recent_signals: list[SignalEvent] = []

        # 去重/冷却配置
        self._dedup_window_seconds: int = 0
        self._cooldown_seconds: int = 0

        # 运行统计
        self._bars_processed: int = 0
        self._signals_generated: int = 0
        self._signals_deduped: int = 0
        self._errors_count: int = 0
        self._start_time: Optional[datetime] = None

        # 持久化
        self._state_dir = Path(state_dir)

    # ───────────── 策略加载 ─────────────

    def load_strategy(self, spec: dict) -> None:
        """
        加载策略定义。
        校验评审状态，提取信号生成所需配置。
        """
        review_status = spec.get("review_status", "pending")
        if review_status not in ("passed", "conditional"):
            raise ValueError(
                f"策略未通过评审 (review_status={review_status})，"
                "无法构建信号服务。请先使用 backtest-reviewer 完成评审。"
            )

        self._spec = spec
        self._strategy_id = spec.get("strategy_id", "")
        self._timeframe = spec.get("timeframe", "1h")
        self._bar_seconds = TIMEFRAME_SECONDS.get(self._timeframe, 3600)
        self._universe = spec.get("universe", [])

        # 初始化每个标的的状态机
        for symbol in self._universe:
            self._states[symbol] = SignalState.IDLE

        # 去重窗口 = 3 × bar 周期
        self._dedup_window_seconds = DEFAULT_DEDUP_MULTIPLIER * self._bar_seconds
        # 冷却期 = 2 × bar 周期
        self._cooldown_seconds = DEFAULT_COOLDOWN_MULTIPLIER * self._bar_seconds

        logger.info(
            "策略加载完成 | strategy_id={} | universe={} | timeframe={} | "
            "dedup_window={}s | cooldown={}s",
            self._strategy_id, self._universe, self._timeframe,
            self._dedup_window_seconds, self._cooldown_seconds,
        )

    # ───────────── 启动/停止 ─────────────

    def start(self) -> None:
        """启动信号引擎，所有标的进入 watching 状态"""
        if not self._spec:
            raise RuntimeError("未加载策略，请先调用 load_strategy()")
        for symbol in self._universe:
            self._transition(symbol, SignalState.WATCHING)
        self._start_time = datetime.now(tz=timezone.utc)
        logger.info("信号引擎启动 | strategy_id={}", self._strategy_id)

    def stop(self) -> None:
        """停止信号引擎，所有标的回到 idle 状态"""
        for symbol in self._universe:
            self._transition(symbol, SignalState.IDLE)
        self.save_state()
        logger.info("信号引擎停止 | strategy_id={}", self._strategy_id)

    # ───────────── 核心：处理 bar 数据 ─────────────

    def on_bar(self, bar_data: dict) -> Optional[SignalEvent]:
        """
        处理一根新 K 线数据。

        参数:
            bar_data: K 线数据，必须包含:
                - symbol: 交易对
                - timestamp: bar 收盘时间 (ISO8601)
                - open, high, low, close, volume: OHLCV
                - indicators: dict，预计算的指标值（可选，如果未提供则由引擎计算）

        返回:
            SignalEvent（如果触发信号）或 None（未触发）
        """
        symbol = bar_data.get("symbol", "")
        timestamp_str = bar_data.get("timestamp", "")

        if symbol not in self._states:
            logger.warning("未知标的 {} 不在 universe 中，跳过", symbol)
            return None

        current_state = self._states[symbol]
        self._bars_processed += 1

        # 空闲状态不处理
        if current_state == SignalState.IDLE:
            return None

        # 获取指标值
        indicators = bar_data.get("indicators", {})
        close_price = bar_data.get("close", 0.0)

        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            timestamp = datetime.now(tz=timezone.utc)

        signal = None

        # 根据当前状态执行不同逻辑
        if current_state == SignalState.WATCHING:
            signal = self._check_entry(symbol, timestamp, close_price, indicators)

        elif current_state == SignalState.POSITION_OPEN:
            signal = self._check_exit(symbol, timestamp, close_price, indicators)

        elif current_state == SignalState.COOLDOWN:
            self._check_cooldown(symbol, timestamp)

        elif current_state == SignalState.ENTRY_TRIGGERED:
            # 等待执行反馈，检查信号是否超时
            self._check_signal_timeout(symbol, timestamp)

        elif current_state == SignalState.EXIT_TRIGGERED:
            pass  # 等待执行反馈

        # 定期心跳日志
        if self._bars_processed % DEFAULT_HEARTBEAT_INTERVAL == 0:
            self._emit_heartbeat()

        return signal

    # ───────────── 入场检查 ─────────────

    def _check_entry(
        self,
        symbol: str,
        timestamp: datetime,
        price: float,
        indicators: dict[str, Any],
    ) -> Optional[SignalEvent]:
        """检查入场规则，返回 SignalEvent 或 None"""
        entry_rules = self._spec.get("entry_rules", [])
        sorted_rules = sorted(entry_rules, key=lambda r: r.get("priority", 0))

        for rule in sorted_rules:
            rule_id = rule.get("id", "")
            condition = rule.get("condition", "")
            action = rule.get("action", "")

            # 评估规则条件（简化实现：使用 indicators 字典检查）
            met = self._evaluate_condition(condition, indicators, price)

            if met:
                # 去重检查
                signal_type = self._action_to_signal_type(action)
                if self._should_dedup(symbol, signal_type, timestamp):
                    self._signals_deduped += 1
                    logger.info(
                        "信号被去重跳过 | symbol={} | rule={} | signal_type={}",
                        symbol, rule_id, signal_type,
                    )
                    continue

                # 冷却期检查
                if self._is_in_cooldown(symbol, timestamp):
                    logger.info(
                        "处于冷却期，跳过 | symbol={} | rule={}",
                        symbol, rule_id,
                    )
                    continue

                # 生成信号
                signal = self._create_signal(
                    symbol=symbol,
                    timestamp=timestamp,
                    signal_type=signal_type,
                    price=price,
                    triggered_by=[rule_id],
                    indicators=indicators,
                )
                self._transition(symbol, SignalState.ENTRY_TRIGGERED)
                self._last_signal_time[symbol] = timestamp
                self._recent_signals.append(signal)
                self._signals_generated += 1

                logger.info(
                    "📊 入场信号触发 | symbol={} | type={} | price={} | rule={}",
                    symbol, signal_type, price, rule_id,
                )
                return signal

        # 未触发 → 记录无信号日志
        logger.debug(
            "本周期无入场信号 | symbol={} | timestamp={} | indicators={}",
            symbol, timestamp.isoformat(), json.dumps(indicators, default=str),
        )
        return None

    # ───────────── 出场检查 ─────────────

    def _check_exit(
        self,
        symbol: str,
        timestamp: datetime,
        price: float,
        indicators: dict[str, Any],
    ) -> Optional[SignalEvent]:
        """检查出场规则，返回 SignalEvent 或 None"""
        exit_rules = self._spec.get("exit_rules", [])
        sorted_rules = sorted(exit_rules, key=lambda r: r.get("priority", 0))

        for rule in sorted_rules:
            rule_id = rule.get("id", "")
            condition = rule.get("condition", "")
            action = rule.get("action", "")

            met = self._evaluate_condition(condition, indicators, price)

            if met:
                signal_type = self._action_to_signal_type(action)
                signal = self._create_signal(
                    symbol=symbol,
                    timestamp=timestamp,
                    signal_type=signal_type,
                    price=price,
                    triggered_by=[rule_id],
                    indicators=indicators,
                )
                self._transition(symbol, SignalState.EXIT_TRIGGERED)
                self._signals_generated += 1

                logger.info(
                    "📊 出场信号触发 | symbol={} | type={} | price={} | rule={}",
                    symbol, signal_type, price, rule_id,
                )
                return signal

        logger.debug(
            "本周期无出场信号 | symbol={} | timestamp={}",
            symbol, timestamp.isoformat(),
        )
        return None

    # ───────────── 冷却期检查 ─────────────

    def _check_cooldown(self, symbol: str, timestamp: datetime) -> None:
        """检查冷却期是否结束"""
        last_exit = self._last_exit_time.get(symbol)
        if last_exit is None:
            self._transition(symbol, SignalState.WATCHING)
            return

        elapsed = (timestamp - last_exit).total_seconds()
        if elapsed >= self._cooldown_seconds:
            self._transition(symbol, SignalState.WATCHING)
            logger.info(
                "冷却期结束，恢复监控 | symbol={} | cooldown={}s | elapsed={}s",
                symbol, self._cooldown_seconds, elapsed,
            )

    # ───────────── 信号超时检查 ─────────────

    def _check_signal_timeout(self, symbol: str, timestamp: datetime) -> None:
        """检查入场信号是否超时失效"""
        last_signal = self._last_signal_time.get(symbol)
        if last_signal is None:
            self._transition(symbol, SignalState.WATCHING)
            return

        elapsed = (timestamp - last_signal).total_seconds()
        if elapsed >= self._bar_seconds:
            self._transition(symbol, SignalState.WATCHING)
            logger.info("入场信号超时失效 | symbol={} | elapsed={}s", symbol, elapsed)

    # ───────────── 外部反馈接口 ─────────────

    def confirm_entry(self, symbol: str) -> None:
        """确认入场执行完成，状态机推进到 position_open"""
        if self._states.get(symbol) == SignalState.ENTRY_TRIGGERED:
            self._transition(symbol, SignalState.POSITION_OPEN)
            logger.info("入场确认 | symbol={} → position_open", symbol)

    def confirm_exit(self, symbol: str) -> None:
        """确认出场执行完成，状态机推进到 cooldown"""
        if self._states.get(symbol) == SignalState.EXIT_TRIGGERED:
            self._last_exit_time[symbol] = datetime.now(tz=timezone.utc)
            self._transition(symbol, SignalState.COOLDOWN)
            logger.info("出场确认 | symbol={} → cooldown", symbol)

    # ───────────── 状态查询 ─────────────

    def get_state(self) -> dict:
        """返回引擎当前的完整状态"""
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now(tz=timezone.utc) - self._start_time).total_seconds()
        return {
            "strategy_id": self._strategy_id,
            "universe": self._universe,
            "timeframe": self._timeframe,
            "states": {s: st.value for s, st in self._states.items()},
            "bars_processed": self._bars_processed,
            "signals_generated": self._signals_generated,
            "signals_deduped": self._signals_deduped,
            "errors_count": self._errors_count,
            "uptime_seconds": uptime,
            "dedup_window_seconds": self._dedup_window_seconds,
            "cooldown_seconds": self._cooldown_seconds,
        }

    def explain_no_signal(self, symbol: str, indicators: dict[str, Any], price: float) -> str:
        """
        解释指定标的为什么没有产生信号。
        返回人类可读的解释文本。
        """
        entry_rules = self._spec.get("entry_rules", [])
        lines = [f"📋 {symbol} 无信号原因分析", ""]

        for rule in entry_rules:
            rule_id = rule.get("id", "")
            description = rule.get("description", "")
            condition = rule.get("condition", "")
            met = self._evaluate_condition(condition, indicators, price)
            status = "✅ 已满足" if met else "❌ 未满足"
            lines.append(f"规则 {rule_id}: {description}")
            lines.append(f"  条件: {condition}")
            lines.append(f"  状态: {status}")
            lines.append("")

        state = self._states.get(symbol, SignalState.IDLE)
        if state == SignalState.COOLDOWN:
            lines.append("⏳ 当前处于冷却期，即使条件满足也不会触发信号")

        lines.append(f"📊 当前指标: {json.dumps(indicators, default=str, ensure_ascii=False)}")
        return "\n".join(lines)

    # ───────────── 状态持久化 ─────────────

    def save_state(self) -> None:
        """将当前状态持久化到磁盘"""
        state_path = self._state_dir / STATE_FILE_NAME
        state_data = {
            "strategy_id": self._strategy_id,
            "states": {s: st.value for s, st in self._states.items()},
            "last_signal_time": {
                s: t.isoformat() for s, t in self._last_signal_time.items()
            },
            "last_exit_time": {
                s: t.isoformat() for s, t in self._last_exit_time.items()
            },
            "recent_signals": [sig.to_dict() for sig in self._recent_signals[-20:]],
            "bars_processed": self._bars_processed,
            "signals_generated": self._signals_generated,
            "signals_deduped": self._signals_deduped,
            "saved_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        try:
            state_path.write_text(json.dumps(state_data, indent=2, default=str))
            logger.debug("状态已持久化 | path={}", state_path)
        except OSError as exc:
            self._errors_count += 1
            logger.error("状态持久化失败 | error={}", exc)

    def load_state(self) -> bool:
        """从磁盘恢复状态，成功返回 True"""
        state_path = self._state_dir / STATE_FILE_NAME
        if not state_path.exists():
            logger.info("无持久化状态文件，使用初始状态")
            return False

        try:
            state_data = json.loads(state_path.read_text())

            # 恢复状态机
            for symbol, state_val in state_data.get("states", {}).items():
                if symbol in self._states:
                    self._states[symbol] = SignalState(state_val)

            # 恢复时间戳
            for symbol, ts in state_data.get("last_signal_time", {}).items():
                self._last_signal_time[symbol] = datetime.fromisoformat(ts)
            for symbol, ts in state_data.get("last_exit_time", {}).items():
                self._last_exit_time[symbol] = datetime.fromisoformat(ts)

            self._bars_processed = state_data.get("bars_processed", 0)
            self._signals_generated = state_data.get("signals_generated", 0)
            self._signals_deduped = state_data.get("signals_deduped", 0)

            logger.info(
                "状态已恢复 | bars_processed={} | signals_generated={}",
                self._bars_processed, self._signals_generated,
            )
            return True

        except (json.JSONDecodeError, OSError, KeyError) as exc:
            self._errors_count += 1
            logger.error("状态恢复失败 | error={}", exc)
            return False

    # ───────────── 私有方法 ─────────────

    def _transition(self, symbol: str, new_state: SignalState) -> None:
        """执行状态转换并记录日志"""
        old_state = self._states.get(symbol, SignalState.IDLE)
        self._states[symbol] = new_state
        if old_state != new_state:
            logger.info(
                "状态转换 | symbol={} | {} → {}",
                symbol, old_state.value, new_state.value,
            )

    def _should_dedup(
        self,
        symbol: str,
        signal_type: str,
        timestamp: datetime,
    ) -> bool:
        """检查信号是否应被去重跳过"""
        for recent in reversed(self._recent_signals):
            if recent.symbol != symbol:
                continue
            if recent.signal_type != signal_type:
                continue
            try:
                recent_time = datetime.fromisoformat(
                    recent.timestamp.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                continue
            elapsed = (timestamp - recent_time).total_seconds()
            if elapsed < self._dedup_window_seconds:
                return True
        return False

    def _is_in_cooldown(self, symbol: str, timestamp: datetime) -> bool:
        """检查指定标的是否处于冷却期"""
        last_exit = self._last_exit_time.get(symbol)
        if last_exit is None:
            return False
        elapsed = (timestamp - last_exit).total_seconds()
        return elapsed < self._cooldown_seconds

    def _evaluate_condition(
        self,
        condition: str,
        indicators: dict[str, Any],
        price: float,
    ) -> bool:
        """
        评估规则条件。

        简化实现：检查 indicators 字典中是否有
        名为 "_{rule_condition}" 的预计算布尔值。
        生产环境应实现完整的条件表达式解析器。
        """
        # 如果 indicators 中直接包含该条件的评估结果
        condition_key = f"_rule_{condition}"
        if condition_key in indicators:
            return bool(indicators[condition_key])

        # 尝试简单的条件匹配
        # 生产环境中应替换为完整的表达式解析引擎
        if condition in indicators:
            return bool(indicators[condition])

        return False

    @staticmethod
    def _action_to_signal_type(action: str) -> str:
        """将规则 action 转换为 SignalType"""
        mapping = {
            "open_long": SignalType.ENTRY_LONG.value,
            "open_short": SignalType.ENTRY_SHORT.value,
            "close_long": SignalType.EXIT_LONG.value,
            "close_short": SignalType.EXIT_SHORT.value,
            "close_all": SignalType.EXIT_ALL.value,
        }
        return mapping.get(action, action)

    def _create_signal(
        self,
        symbol: str,
        timestamp: datetime,
        signal_type: str,
        price: float,
        triggered_by: list[str],
        indicators: dict[str, Any],
    ) -> SignalEvent:
        """创建 SignalEvent 实例"""
        # 从策略定义中获取止损/止盈
        risk_limits = self._spec.get("risk_limits", {})
        sl_pct = risk_limits.get("stop_loss")
        tp_pct = risk_limits.get("take_profit")

        sl_price = None
        tp_price = None
        if sl_pct and price:
            if "long" in signal_type:
                sl_price = round(price * (1 - sl_pct), 2)
            elif "short" in signal_type:
                sl_price = round(price * (1 + sl_pct), 2)
        if tp_pct and price:
            if "long" in signal_type:
                tp_price = round(price * (1 + tp_pct), 2)
            elif "short" in signal_type:
                tp_price = round(price * (1 - tp_pct), 2)

        # 过滤掉 indicators 中的内部键（以 _ 开头）
        public_indicators = {
            k: v for k, v in indicators.items() if not k.startswith("_")
        }

        return SignalEvent(
            signal_id=f"sig_{uuid.uuid4()}",
            strategy_id=self._strategy_id,
            timestamp=timestamp.isoformat(),
            symbol=symbol,
            timeframe=self._timeframe,
            signal_type=signal_type,
            strength=indicators.get("_signal_strength", 0.5),
            price_at_signal=price,
            triggered_by=triggered_by,
            feature_snapshot=public_indicators,
            suggested_price=price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            confidence=indicators.get("_confidence", None),
            ttl_seconds=self._bar_seconds,
            metadata={
                "engine_version": "v1.0",
                "bars_processed": self._bars_processed,
            },
        )

    def _emit_heartbeat(self) -> None:
        """输出心跳日志"""
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now(tz=timezone.utc) - self._start_time).total_seconds()

        logger.info(
            "💓 心跳 | strategy={} | bars={} | signals={} | deduped={} | "
            "errors={} | uptime={}s | states={}",
            self._strategy_id,
            self._bars_processed,
            self._signals_generated,
            self._signals_deduped,
            self._errors_count,
            int(uptime),
            {s: st.value for s, st in self._states.items()},
        )


# ─────────────────────────── 使用示例 ───────────────────────────

if __name__ == "__main__":
    logger.add("signal_runtime.log", rotation="10 MB", retention="7 days")

    # 示例：加载一个已通过评审的策略
    sample_spec = {
        "strategy_id": "strat_demo_001",
        "review_status": "passed",
        "timeframe": "1h",
        "universe": ["BTCUSDT"],
        "features": [
            {"name": "sma_20", "indicator": "SMA", "params": {"period": 20}},
            {"name": "sma_60", "indicator": "SMA", "params": {"period": 60}},
        ],
        "entry_rules": [
            {
                "id": "entry_long_1",
                "description": "SMA20 上穿 SMA60 做多",
                "condition": "sma20_cross_above_sma60",
                "action": "open_long",
                "priority": 0,
            }
        ],
        "exit_rules": [
            {
                "id": "exit_sl",
                "description": "止损 2%",
                "condition": "stop_loss_hit",
                "action": "close_all",
                "priority": 0,
            }
        ],
        "risk_limits": {
            "stop_loss": 0.02,
            "take_profit": 0.06,
        },
    }

    runtime = SignalRuntime(state_dir=".")
    runtime.load_strategy(sample_spec)
    runtime.start()

    # 模拟接收 bar 数据
    bar = {
        "symbol": "BTCUSDT",
        "timestamp": "2026-03-12T14:00:00Z",
        "open": 67000.0,
        "high": 67500.0,
        "low": 66800.0,
        "close": 67432.5,
        "volume": 15000.0,
        "indicators": {
            "sma_20": 65100.0,
            "sma_60": 63200.0,
            "sma20_cross_above_sma60": True,
            "_signal_strength": 0.82,
        },
    }

    signal = runtime.on_bar(bar)
    if signal:
        logger.info("生成信号: {}", json.dumps(signal.to_dict(), indent=2, default=str))

    # 查看引擎状态
    state = runtime.get_state()
    logger.info("引擎状态: {}", json.dumps(state, indent=2))

    # 保存状态
    runtime.save_state()
