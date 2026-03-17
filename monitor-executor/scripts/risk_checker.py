"""
风控检查器

对交易信号执行全面的风控检查，决定是否允许执行。
包含 10 项独立检查：仓位上限、日内亏损、重复下单、冷却期、
交易所可用性、保证金充足、杠杆限制、黑名单时段、相关性暴露、Kill Switch。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger

# ─────────────────────────── 数据类 ───────────────────────────


@dataclass
class RiskConfig:
    """风控配置参数"""

    # 仓位限制
    max_position_pct: float = 0.2
    max_total_position_pct: float = 0.6
    max_concurrent_positions: int = 3

    # 日内亏损
    max_daily_loss: float = 0.02
    daily_loss_warning_ratio: float = 0.8

    # 冷却期
    cooldown_seconds: int = 7200

    # 杠杆
    max_leverage: int = 20
    leverage_warning_threshold: int = 10

    # 保证金
    safety_margin_pct: float = 0.1
    min_available_usd: float = 100.0

    # 去重
    dedup_window_seconds: int = 3600

    # 黑名单时段 — 格式: [{"name": "...", "start": "ISO8601", "end": "ISO8601"}, ...]
    blackout_periods: list[dict] = field(default_factory=list)
    weekend_low_liquidity_hours: list[int] = field(
        default_factory=lambda: [2, 3, 4, 5]
    )

    # 相关性
    max_correlated_positions: int = 2

    # Kill Switch
    max_drawdown: float = 0.1
    max_consecutive_losses: int = 5


@dataclass
class AccountState:
    """账户状态快照"""
    total_balance: float = 0.0
    available_balance: float = 0.0
    margin_used: float = 0.0
    unrealized_pnl: float = 0.0
    today_realized_pnl: float = 0.0
    peak_balance: float = 0.0
    consecutive_losses: int = 0


@dataclass
class PositionInfo:
    """单个持仓信息"""
    symbol: str = ""
    direction: str = ""           # "long" / "short"
    quantity: float = 0.0
    entry_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    leverage: int = 1


@dataclass
class SignalInfo:
    """信号的关键信息（从 SignalEvent 提取）"""
    signal_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    signal_type: str = ""         # "entry_long" / "entry_short" / "exit_*"
    price_at_signal: float = 0.0
    suggested_quantity: float = 0.0
    leverage: int = 1
    timestamp: str = ""
    ttl_seconds: int = 3600


@dataclass
class SingleCheckResult:
    """单项风控检查结果"""
    check_name: str
    passed: bool
    current_value: Any = None
    limit_value: Any = None
    message: str = ""


@dataclass
class RiskCheckResult:
    """全部风控检查的综合结果"""
    allowed: bool
    checks: dict[str, SingleCheckResult] = field(default_factory=dict)
    rejection_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["checks"] = {k: asdict(v) for k, v in self.checks.items()}
        return result


# ─────────────────────────── 相关性分组 ───────────────────────────

CORRELATION_GROUPS: dict[str, list[str]] = {
    "btc_ecosystem": ["BTCUSDT", "BCHUSDT", "LTCUSDT"],
    "eth_ecosystem": ["ETHUSDT", "MATICUSDT", "ARBUSDT", "OPUSDT"],
    "defi": ["UNIUSDT", "AAVEUSDT", "COMPUSDT", "MKRUSDT"],
    "meme": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT"],
    "l1": ["SOLUSDT", "AVAXUSDT", "DOTUSDT", "ADAUSDT", "NEARUSDT"],
}


def _find_correlation_group(symbol: str) -> Optional[str]:
    """查找标的所属的相关性分组"""
    for group_name, symbols in CORRELATION_GROUPS.items():
        if symbol in symbols:
            return group_name
    return None


def _signal_direction(signal: SignalInfo) -> str:
    """从信号类型推断方向"""
    if "long" in signal.signal_type:
        return "long"
    if "short" in signal.signal_type:
        return "short"
    return "unknown"


# ─────────────────────────── 核心检查器 ───────────────────────────


class RiskChecker:
    """
    风控检查器

    职责：
    1. 接收交易信号、账户状态、持仓状态和风控配置
    2. 执行 10 项独立风控检查
    3. 返回综合检查结果
    4. 管理 Kill Switch 状态
    """

    def __init__(self, config: Optional[RiskConfig] = None) -> None:
        self._config = config or RiskConfig()
        self._kill_switch_active = False
        self._kill_switch_reason = ""
        self._kill_switch_time: Optional[datetime] = None
        self._recent_order_ids: list[str] = []  # 最近的订单 signal_id 记录
        self._recent_orders: list[dict] = []     # 最近的订单详情
        self._last_trade_time: dict[str, datetime] = {}  # 每个标的的上次交易时间

    # ───────────── 综合检查入口 ─────────────

    def check_all(
        self,
        signal: SignalInfo,
        account: AccountState,
        positions: list[PositionInfo],
    ) -> RiskCheckResult:
        """
        执行全部风控检查。

        按优先级顺序执行，任一关键检查失败即标记为不允许执行。
        """
        result = RiskCheckResult(allowed=True)

        # 按优先级执行检查（任一失败即标记 allowed=False，但继续执行后续检查以收集完整信息）
        checks = [
            ("kill_switch", self._check_kill_switch, (account,)),
            ("signal_validity", self._check_signal_validity, (signal,)),
            ("duplicate", self._check_duplicate, (signal,)),
            ("venue_health", self._check_venue_health, (signal,)),
            ("blackout", self._check_blackout, ()),
            ("daily_loss", self._check_daily_loss, (account,)),
            ("cooldown", self._check_cooldown, (signal,)),
            ("margin", self._check_margin, (signal, account)),
            ("position_limit", self._check_position_limit, (signal, account, positions)),
            ("leverage", self._check_leverage, (signal,)),
            ("correlation", self._check_correlation, (signal, positions)),
        ]

        for check_name, check_fn, args in checks:
            try:
                check_result = check_fn(*args)
                result.checks[check_name] = check_result
                if not check_result.passed:
                    result.allowed = False
                    result.rejection_reasons.append(
                        f"[{check_name}] {check_result.message}"
                    )
                    logger.warning(
                        "❌ 风控检查失败 | check={} | message={}",
                        check_name, check_result.message,
                    )
            except Exception as exc:
                result.allowed = False
                error_check = SingleCheckResult(
                    check_name=check_name,
                    passed=False,
                    message=f"检查异常: {exc}",
                )
                result.checks[check_name] = error_check
                result.rejection_reasons.append(
                    f"[{check_name}] 检查异常: {exc}"
                )
                logger.error("风控检查异常 | check={} | error={}", check_name, exc)

        # 日志摘要
        passed_count = sum(1 for c in result.checks.values() if c.passed)
        total_count = len(result.checks)
        if result.allowed:
            logger.info(
                "✅ 风控检查全部通过 | signal={} | {}/{}",
                signal.signal_id, passed_count, total_count,
            )
        else:
            logger.warning(
                "❌ 风控检查未通过 | signal={} | passed={}/{} | reasons={}",
                signal.signal_id, passed_count, total_count,
                result.rejection_reasons,
            )

        return result

    # ───────────── 各项检查实现 ─────────────

    def _check_kill_switch(self, account: AccountState) -> SingleCheckResult:
        """Kill Switch / 熔断检查"""
        # 手动激活的 kill switch
        if self._kill_switch_active:
            return SingleCheckResult(
                check_name="kill_switch",
                passed=False,
                message=(
                    f"Kill switch 已激活 | 原因: {self._kill_switch_reason} | "
                    f"时间: {self._kill_switch_time}"
                ),
            )

        # 自动检测：账户回撤
        if account.peak_balance > 0:
            drawdown = (account.peak_balance - account.total_balance) / account.peak_balance
            if drawdown > self._config.max_drawdown:
                self.activate_kill_switch(
                    f"账户回撤 {drawdown:.2%} 超过阈值 {self._config.max_drawdown:.2%}"
                )
                return SingleCheckResult(
                    check_name="kill_switch",
                    passed=False,
                    current_value=drawdown,
                    limit_value=self._config.max_drawdown,
                    message=f"自动触发: 账户回撤 {drawdown:.2%}",
                )

        # 自动检测：连续亏损
        if account.consecutive_losses >= self._config.max_consecutive_losses:
            self.activate_kill_switch(
                f"连续亏损 {account.consecutive_losses} 笔"
            )
            return SingleCheckResult(
                check_name="kill_switch",
                passed=False,
                current_value=account.consecutive_losses,
                limit_value=self._config.max_consecutive_losses,
                message=f"自动触发: 连续亏损 {account.consecutive_losses} 笔",
            )

        return SingleCheckResult(
            check_name="kill_switch",
            passed=True,
            message="Kill switch 未激活",
        )

    def _check_signal_validity(self, signal: SignalInfo) -> SingleCheckResult:
        """信号有效性检查"""
        if not signal.signal_id:
            return SingleCheckResult(
                check_name="signal_validity",
                passed=False,
                message="信号 ID 为空",
            )

        # 检查信号是否过期
        try:
            sig_time = datetime.fromisoformat(
                signal.timestamp.replace("Z", "+00:00")
            )
            now = datetime.now(tz=timezone.utc)
            elapsed = (now - sig_time).total_seconds()
            if elapsed > signal.ttl_seconds:
                return SingleCheckResult(
                    check_name="signal_validity",
                    passed=False,
                    current_value=elapsed,
                    limit_value=signal.ttl_seconds,
                    message=f"信号已过期（已过 {elapsed:.0f}s，TTL {signal.ttl_seconds}s）",
                )
        except (ValueError, AttributeError):
            pass  # 无法解析时间戳时不阻断

        return SingleCheckResult(
            check_name="signal_validity",
            passed=True,
            message="信号有效",
        )

    def _check_duplicate(self, signal: SignalInfo) -> SingleCheckResult:
        """重复下单防护"""
        if signal.signal_id in self._recent_order_ids:
            return SingleCheckResult(
                check_name="duplicate",
                passed=False,
                message=f"信号 {signal.signal_id} 已被执行过",
            )

        # 同标的同方向去重
        direction = _signal_direction(signal)
        now = datetime.now(tz=timezone.utc)
        for order in self._recent_orders:
            if (
                order.get("symbol") == signal.symbol
                and order.get("direction") == direction
            ):
                order_time_str = order.get("timestamp", "")
                try:
                    order_time = datetime.fromisoformat(
                        order_time_str.replace("Z", "+00:00")
                    )
                    elapsed = (now - order_time).total_seconds()
                    if elapsed < self._config.dedup_window_seconds:
                        return SingleCheckResult(
                            check_name="duplicate",
                            passed=False,
                            current_value=elapsed,
                            limit_value=self._config.dedup_window_seconds,
                            message=(
                                f"{signal.symbol} {direction} 方向在 "
                                f"{self._config.dedup_window_seconds}s 内已有订单"
                            ),
                        )
                except (ValueError, AttributeError):
                    continue

        return SingleCheckResult(
            check_name="duplicate",
            passed=True,
            message="无重复订单",
        )

    def _check_venue_health(self, signal: SignalInfo) -> SingleCheckResult:
        """
        交易所可用性检查（简化实现）。
        生产环境应接入真实的交易所健康检查 API。
        """
        # 简化：默认认为交易所可用
        return SingleCheckResult(
            check_name="venue_health",
            passed=True,
            message=f"交易所可用 | symbol={signal.symbol}",
        )

    def _check_blackout(self) -> SingleCheckResult:
        """黑名单时段过滤"""
        now = datetime.now(tz=timezone.utc)

        # 检查自定义黑名单
        for period in self._config.blackout_periods:
            try:
                start = datetime.fromisoformat(
                    period["start"].replace("Z", "+00:00")
                )
                end = datetime.fromisoformat(
                    period["end"].replace("Z", "+00:00")
                )
                if start <= now <= end:
                    return SingleCheckResult(
                        check_name="blackout",
                        passed=False,
                        message=f"当前处于黑名单时段: {period.get('name', '未命名')}",
                    )
            except (KeyError, ValueError):
                continue

        # 检查周末低流动性时段
        if now.weekday() >= 5:
            if now.hour in self._config.weekend_low_liquidity_hours:
                return SingleCheckResult(
                    check_name="blackout",
                    passed=True,
                    message=f"⚠️ 周末低流动性时段 (UTC {now.hour}:00)，滑点可能增大",
                )

        return SingleCheckResult(
            check_name="blackout",
            passed=True,
            message="正常交易时段",
        )

    def _check_daily_loss(self, account: AccountState) -> SingleCheckResult:
        """日内亏损阈值检查"""
        if account.total_balance <= 0:
            return SingleCheckResult(
                check_name="daily_loss",
                passed=False,
                message="账户余额为零或负值",
            )

        # 计算当日总亏损（已实现 + 未实现亏损）
        total_daily_pnl = account.today_realized_pnl + min(account.unrealized_pnl, 0)
        daily_loss_pct = abs(min(total_daily_pnl, 0)) / account.total_balance

        if daily_loss_pct >= self._config.max_daily_loss:
            return SingleCheckResult(
                check_name="daily_loss",
                passed=False,
                current_value=daily_loss_pct,
                limit_value=self._config.max_daily_loss,
                message=(
                    f"当日亏损 {daily_loss_pct:.2%} 已达上限 "
                    f"{self._config.max_daily_loss:.2%}，今日停止交易"
                ),
            )

        if daily_loss_pct >= self._config.max_daily_loss * self._config.daily_loss_warning_ratio:
            return SingleCheckResult(
                check_name="daily_loss",
                passed=True,
                current_value=daily_loss_pct,
                limit_value=self._config.max_daily_loss,
                message=(
                    f"⚠️ 当日亏损 {daily_loss_pct:.2%} 接近上限 "
                    f"{self._config.max_daily_loss:.2%}"
                ),
            )

        return SingleCheckResult(
            check_name="daily_loss",
            passed=True,
            current_value=daily_loss_pct,
            limit_value=self._config.max_daily_loss,
            message=f"当日亏损 {daily_loss_pct:.2%}，上限 {self._config.max_daily_loss:.2%}",
        )

    def _check_cooldown(self, signal: SignalInfo) -> SingleCheckResult:
        """冷却期检查"""
        last_trade = self._last_trade_time.get(signal.symbol)
        if last_trade is None:
            return SingleCheckResult(
                check_name="cooldown",
                passed=True,
                message=f"{signal.symbol} 无历史交易，无冷却期",
            )

        now = datetime.now(tz=timezone.utc)
        elapsed = (now - last_trade).total_seconds()

        if elapsed < self._config.cooldown_seconds:
            remaining = self._config.cooldown_seconds - elapsed
            return SingleCheckResult(
                check_name="cooldown",
                passed=False,
                current_value=elapsed,
                limit_value=self._config.cooldown_seconds,
                message=(
                    f"冷却期中 | 距上次交易 {elapsed:.0f}s，"
                    f"需等待 {remaining:.0f}s"
                ),
            )

        return SingleCheckResult(
            check_name="cooldown",
            passed=True,
            current_value=elapsed,
            limit_value=self._config.cooldown_seconds,
            message=f"冷却期已过 | 已过 {elapsed:.0f}s",
        )

    def _check_margin(
        self,
        signal: SignalInfo,
        account: AccountState,
    ) -> SingleCheckResult:
        """保证金充足性检查"""
        order_value = signal.price_at_signal * signal.suggested_quantity
        leverage = max(signal.leverage, 1)
        required_margin = order_value / leverage
        safety_buffer = account.total_balance * self._config.safety_margin_pct
        available = account.available_balance - safety_buffer

        if available < required_margin:
            return SingleCheckResult(
                check_name="margin",
                passed=False,
                current_value=available,
                limit_value=required_margin,
                message=(
                    f"可用保证金不足 | 需要 ${required_margin:.2f}，"
                    f"可用 ${available:.2f}（含安全余量 ${safety_buffer:.2f}）"
                ),
            )

        if available < self._config.min_available_usd:
            return SingleCheckResult(
                check_name="margin",
                passed=False,
                current_value=available,
                limit_value=self._config.min_available_usd,
                message=f"可用余额 ${available:.2f} 低于最低要求 ${self._config.min_available_usd:.2f}",
            )

        return SingleCheckResult(
            check_name="margin",
            passed=True,
            current_value=available,
            limit_value=required_margin,
            message=f"保证金充足 | 可用 ${available:.2f}，需要 ${required_margin:.2f}",
        )

    def _check_position_limit(
        self,
        signal: SignalInfo,
        account: AccountState,
        positions: list[PositionInfo],
    ) -> SingleCheckResult:
        """仓位上限检查"""
        if account.total_balance <= 0:
            return SingleCheckResult(
                check_name="position_limit",
                passed=False,
                message="账户余额为零",
            )

        # 新订单市值
        new_order_value = signal.price_at_signal * signal.suggested_quantity

        # 单仓位占比
        single_pct = new_order_value / account.total_balance
        if single_pct > self._config.max_position_pct:
            return SingleCheckResult(
                check_name="position_limit",
                passed=False,
                current_value=single_pct,
                limit_value=self._config.max_position_pct,
                message=(
                    f"单仓位占比 {single_pct:.1%} 超过上限 "
                    f"{self._config.max_position_pct:.1%}"
                ),
            )

        # 总仓位占比
        total_value = sum(p.market_value for p in positions) + new_order_value
        total_pct = total_value / account.total_balance
        if total_pct > self._config.max_total_position_pct:
            return SingleCheckResult(
                check_name="position_limit",
                passed=False,
                current_value=total_pct,
                limit_value=self._config.max_total_position_pct,
                message=(
                    f"总仓位占比 {total_pct:.1%} 超过上限 "
                    f"{self._config.max_total_position_pct:.1%}"
                ),
            )

        # 持仓数量
        if len(positions) >= self._config.max_concurrent_positions:
            return SingleCheckResult(
                check_name="position_limit",
                passed=False,
                current_value=len(positions),
                limit_value=self._config.max_concurrent_positions,
                message=(
                    f"持仓数量 {len(positions)} 已达上限 "
                    f"{self._config.max_concurrent_positions}"
                ),
            )

        return SingleCheckResult(
            check_name="position_limit",
            passed=True,
            current_value=single_pct,
            limit_value=self._config.max_position_pct,
            message=f"仓位占比 {single_pct:.1%}，上限 {self._config.max_position_pct:.1%}",
        )

    def _check_leverage(self, signal: SignalInfo) -> SingleCheckResult:
        """杠杆限制检查"""
        if signal.leverage > self._config.max_leverage:
            return SingleCheckResult(
                check_name="leverage",
                passed=False,
                current_value=signal.leverage,
                limit_value=self._config.max_leverage,
                message=(
                    f"杠杆 {signal.leverage}x 超过上限 "
                    f"{self._config.max_leverage}x"
                ),
            )

        if signal.leverage > self._config.leverage_warning_threshold:
            return SingleCheckResult(
                check_name="leverage",
                passed=True,
                current_value=signal.leverage,
                limit_value=self._config.max_leverage,
                message=f"⚠️ 杠杆 {signal.leverage}x 偏高，请注意爆仓风险",
            )

        return SingleCheckResult(
            check_name="leverage",
            passed=True,
            current_value=signal.leverage,
            limit_value=self._config.max_leverage,
            message=f"杠杆 {signal.leverage}x，上限 {self._config.max_leverage}x",
        )

    def _check_correlation(
        self,
        signal: SignalInfo,
        positions: list[PositionInfo],
    ) -> SingleCheckResult:
        """相关性暴露检查"""
        new_group = _find_correlation_group(signal.symbol)
        if new_group is None:
            return SingleCheckResult(
                check_name="correlation",
                passed=True,
                message=f"{signal.symbol} 不在已知相关性分组中，跳过检查",
            )

        direction = _signal_direction(signal)
        same_direction_count = 0
        for pos in positions:
            pos_group = _find_correlation_group(pos.symbol)
            if pos_group == new_group and pos.direction == direction:
                same_direction_count += 1

        if same_direction_count >= self._config.max_correlated_positions:
            return SingleCheckResult(
                check_name="correlation",
                passed=False,
                current_value=same_direction_count,
                limit_value=self._config.max_correlated_positions,
                message=(
                    f"相关性组 '{new_group}' 已有 {same_direction_count} 个 "
                    f"{direction} 仓位，上限 {self._config.max_correlated_positions}"
                ),
            )

        return SingleCheckResult(
            check_name="correlation",
            passed=True,
            current_value=same_direction_count,
            limit_value=self._config.max_correlated_positions,
            message=f"相关性暴露正常 | 组 '{new_group}' {direction} 仓位 {same_direction_count}",
        )

    # ───────────── Kill Switch 管理 ─────────────

    def activate_kill_switch(self, reason: str = "手动激活") -> None:
        """激活 Kill Switch，拒绝所有新订单"""
        self._kill_switch_active = True
        self._kill_switch_reason = reason
        self._kill_switch_time = datetime.now(tz=timezone.utc)
        logger.critical(
            "🚨 KILL SWITCH 激活 | 原因: {} | 时间: {}",
            reason, self._kill_switch_time.isoformat(),
        )

    def deactivate_kill_switch(self) -> None:
        """关闭 Kill Switch，恢复正常交易"""
        if self._kill_switch_active:
            logger.info(
                "✅ Kill Switch 已关闭 | 之前原因: {} | 持续时间: {}",
                self._kill_switch_reason,
                (datetime.now(tz=timezone.utc) - self._kill_switch_time)
                if self._kill_switch_time
                else "未知",
            )
        self._kill_switch_active = False
        self._kill_switch_reason = ""
        self._kill_switch_time = None

    def is_kill_switch_active(self) -> bool:
        """查询 Kill Switch 是否处于激活状态"""
        return self._kill_switch_active

    def get_kill_switch_info(self) -> dict:
        """获取 Kill Switch 的详细信息"""
        return {
            "active": self._kill_switch_active,
            "reason": self._kill_switch_reason,
            "activated_at": (
                self._kill_switch_time.isoformat()
                if self._kill_switch_time
                else None
            ),
        }

    # ───────────── 订单记录管理 ─────────────

    def record_execution(self, signal: SignalInfo) -> None:
        """记录已执行的订单，用于去重和冷却期检查"""
        self._recent_order_ids.append(signal.signal_id)
        self._recent_orders.append({
            "signal_id": signal.signal_id,
            "symbol": signal.symbol,
            "direction": _signal_direction(signal),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
        self._last_trade_time[signal.symbol] = datetime.now(tz=timezone.utc)

        # 保留最近 100 条记录
        if len(self._recent_order_ids) > 100:
            self._recent_order_ids = self._recent_order_ids[-100:]
        if len(self._recent_orders) > 100:
            self._recent_orders = self._recent_orders[-100:]

        logger.info(
            "订单已记录 | signal_id={} | symbol={} | direction={}",
            signal.signal_id, signal.symbol, _signal_direction(signal),
        )


# ─────────────────────────── 使用示例 ───────────────────────────

if __name__ == "__main__":
    logger.add("risk_checker.log", rotation="10 MB", retention="7 days")

    # 创建风控配置
    config = RiskConfig(
        max_position_pct=0.2,
        max_daily_loss=0.02,
        cooldown_seconds=7200,
        max_leverage=10,
    )

    # 创建检查器
    checker = RiskChecker(config)

    # 模拟信号
    signal = SignalInfo(
        signal_id="sig_test_001",
        strategy_id="strat_demo_001",
        symbol="BTCUSDT",
        signal_type="entry_long",
        price_at_signal=67432.5,
        suggested_quantity=0.015,
        leverage=3,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        ttl_seconds=3600,
    )

    # 模拟账户状态
    account = AccountState(
        total_balance=10000.0,
        available_balance=9000.0,
        margin_used=1000.0,
        unrealized_pnl=-50.0,
        today_realized_pnl=-30.0,
        peak_balance=10500.0,
        consecutive_losses=1,
    )

    # 模拟持仓
    positions = [
        PositionInfo(
            symbol="ETHUSDT",
            direction="long",
            quantity=0.5,
            entry_price=3200.0,
            market_value=1600.0,
            unrealized_pnl=-50.0,
            leverage=2,
        )
    ]

    # 执行风控检查
    result = checker.check_all(signal, account, positions)

    # 输出结果
    logger.info("风控检查结果: {}", json.dumps(result.to_dict(), indent=2, default=str))

    if result.allowed:
        logger.info("✅ 允许执行")
        checker.record_execution(signal)
    else:
        logger.warning("❌ 拒绝执行 | 原因: {}", result.rejection_reasons)

    # Kill Switch 操作示例
    logger.info("Kill Switch 状态: {}", checker.get_kill_switch_info())
    checker.activate_kill_switch("测试激活")
    logger.info("Kill Switch 状态: {}", checker.get_kill_switch_info())
    checker.deactivate_kill_switch()
    logger.info("Kill Switch 状态: {}", checker.get_kill_switch_info())
