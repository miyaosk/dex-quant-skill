"""
策略引擎 + 信号系统

核心理念（Eric 定义）：
  信号是策略产生的。策略基于技术指标判断市场状态，产出具体的交易信号。
  信号 = 具体的币种 + 入场时间 + 入场价格 + 方向 + 止盈止损。
  回测基于策略历史发出的信号去执行。

四层结构：
  1. 指标计算层（Indicators）: MA/EMA/RSI/MACD/Bollinger/ATR
  2. 策略规则层（StrategyRule + Condition）: Agent 写的判断逻辑
  3. 信号产出层（TradeSignal）: 策略运行后输出的具体交易指令
  4. 信号存储层（SignalLog）: 存储/导出/展示所有历史信号
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════
#  第一层：技术指标计算
# ═══════════════════════════════════════════

class Indicators:
    """常用技术指标，全部基于 numpy 向量化计算。"""

    @staticmethod
    def sma(series: np.ndarray, period: int) -> np.ndarray:
        """简单移动平均线"""
        result = np.full_like(series, np.nan, dtype=float)
        for i in range(period - 1, len(series)):
            result[i] = np.mean(series[i - period + 1:i + 1])
        return result

    @staticmethod
    def ema(series: np.ndarray, period: int) -> np.ndarray:
        """指数移动平均线"""
        result = np.full_like(series, np.nan, dtype=float)
        k = 2 / (period + 1)
        result[period - 1] = np.mean(series[:period])
        for i in range(period, len(series)):
            result[i] = series[i] * k + result[i - 1] * (1 - k)
        return result

    @staticmethod
    def rsi(series: np.ndarray, period: int = 14) -> np.ndarray:
        """相对强弱指数 (0-100)"""
        deltas = np.diff(series, prepend=series[0])
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = np.full_like(series, np.nan, dtype=float)
        avg_loss = np.full_like(series, np.nan, dtype=float)

        avg_gain[period] = np.mean(gains[1:period + 1])
        avg_loss[period] = np.mean(losses[1:period + 1])

        for i in range(period + 1, len(series)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

        rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100.0)
        rsi_values = 100 - (100 / (1 + rs))
        rsi_values[:period] = np.nan
        return rsi_values

    @staticmethod
    def macd(series: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """MACD 指标，返回 (macd_line, signal_line, histogram)"""
        fast_ema = Indicators.ema(series, fast)
        slow_ema = Indicators.ema(series, slow)
        macd_line = fast_ema - slow_ema
        signal_line = Indicators.ema(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(series: np.ndarray, period: int = 20, std_dev: float = 2.0
                        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """布林带，返回 (upper, middle, lower)"""
        middle = Indicators.sma(series, period)
        std = np.full_like(series, np.nan, dtype=float)
        for i in range(period - 1, len(series)):
            std[i] = np.std(series[i - period + 1:i + 1])
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        return upper, middle, lower

    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
            ) -> np.ndarray:
        """平均真实波幅"""
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - np.roll(close, 1)),
                np.abs(low - np.roll(close, 1))
            )
        )
        tr[0] = high[0] - low[0]
        return Indicators.sma(tr, period)

    @staticmethod
    def volume_ma(volume: np.ndarray, period: int = 20) -> np.ndarray:
        """成交量均线"""
        return Indicators.sma(volume, period)

    @staticmethod
    def kdj(high: np.ndarray, low: np.ndarray, close: np.ndarray,
            k_period: int = 9, d_period: int = 3) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """KDJ 随机指标，返回 (K, D, J)"""
        n = len(close)
        rsv = np.full(n, np.nan, dtype=float)
        for i in range(k_period - 1, n):
            hh = np.max(high[i - k_period + 1:i + 1])
            ll = np.min(low[i - k_period + 1:i + 1])
            rsv[i] = (close[i] - ll) / (hh - ll) * 100 if hh != ll else 50

        k_val = np.full(n, np.nan, dtype=float)
        d_val = np.full(n, np.nan, dtype=float)
        k_val[k_period - 1] = rsv[k_period - 1]
        d_val[k_period - 1] = k_val[k_period - 1]
        for i in range(k_period, n):
            k_val[i] = (d_period - 1) / d_period * k_val[i - 1] + 1 / d_period * rsv[i]
            d_val[i] = (d_period - 1) / d_period * d_val[i - 1] + 1 / d_period * k_val[i]
        j_val = 3 * k_val - 2 * d_val
        return k_val, d_val, j_val


# ═══════════════════════════════════════════
#  第二层：策略规则（条件 + 判断逻辑）
# ═══════════════════════════════════════════

class Condition:
    """
    可组合的条件单元。Agent 用这些积木搭建策略规则。

    用法:
        rsi_high = Condition.above("rsi", 70)
        fr_high = Condition.above("funding_rate", 0.0005)
        short_rule = rsi_high & fr_high   # AND 组合
    """

    def __init__(self, name: str, check_fn: Callable[[dict], bool]):
        self.name = name
        self._check = check_fn

    def evaluate(self, ctx: dict) -> bool:
        try:
            return self._check(ctx)
        except (KeyError, TypeError, IndexError):
            return False

    def __and__(self, other: Condition) -> Condition:
        return Condition(
            f"({self.name} AND {other.name})",
            lambda ctx, s=self, o=other: s.evaluate(ctx) and o.evaluate(ctx),
        )

    def __or__(self, other: Condition) -> Condition:
        return Condition(
            f"({self.name} OR {other.name})",
            lambda ctx, s=self, o=other: s.evaluate(ctx) or o.evaluate(ctx),
        )

    def __invert__(self) -> Condition:
        return Condition(
            f"NOT({self.name})",
            lambda ctx, s=self: not s.evaluate(ctx),
        )

    @staticmethod
    def above(field: str, threshold: float) -> Condition:
        return Condition(f"{field} > {threshold}",
                         lambda ctx, f=field, t=threshold: ctx.get(f, 0) > t)

    @staticmethod
    def below(field: str, threshold: float) -> Condition:
        return Condition(f"{field} < {threshold}",
                         lambda ctx, f=field, t=threshold: ctx.get(f, 0) < t)

    @staticmethod
    def cross_above(fast_field: str, slow_field: str) -> Condition:
        return Condition(
            f"{fast_field} cross above {slow_field}",
            lambda ctx, ff=fast_field, sf=slow_field: (
                ctx.get(ff, 0) > ctx.get(sf, 0) and
                ctx.get(f"prev_{ff}", 0) <= ctx.get(f"prev_{sf}", 0)
            ),
        )

    @staticmethod
    def cross_below(fast_field: str, slow_field: str) -> Condition:
        return Condition(
            f"{fast_field} cross below {slow_field}",
            lambda ctx, ff=fast_field, sf=slow_field: (
                ctx.get(ff, 0) < ctx.get(sf, 0) and
                ctx.get(f"prev_{ff}", 0) >= ctx.get(f"prev_{sf}", 0)
            ),
        )

    @staticmethod
    def between(field: str, low: float, high: float) -> Condition:
        return Condition(f"{low} < {field} < {high}",
                         lambda ctx, f=field, lo=low, hi=high: lo < ctx.get(f, 0) < hi)

    @staticmethod
    def change_pct_above(field: str, pct: float) -> Condition:
        def _check(ctx, f=field, p=pct):
            curr = ctx.get(f, 0)
            prev = ctx.get(f"prev_{f}")
            if prev is None or prev == 0:
                return False
            return abs(curr - prev) / abs(prev) > p / 100
        return Condition(f"{field} change > {pct}%", _check)

    def __repr__(self):
        return f"Condition({self.name})"


class RuleAction(Enum):
    """策略规则触发后要执行的动作"""
    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


@dataclass
class StrategyRule:
    """
    一条策略规则：当 condition 满足时，执行 action。

    Agent 根据用户描述，组装多条 StrategyRule 构成完整策略。
    策略运行时，满足条件的 Rule 产出 TradeSignal。
    """
    name: str
    action: RuleAction
    condition: Condition
    leverage: int = 1
    position_size: float = 0.1
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None

    def check(self, ctx: dict) -> bool:
        return self.condition.evaluate(ctx)

    def describe(self) -> str:
        parts = [
            f"规则: {self.name}",
            f"动作: {self.action.value}",
            f"条件: {self.condition.name}",
        ]
        if self.action in (RuleAction.OPEN_LONG, RuleAction.OPEN_SHORT):
            parts.append(f"杠杆: {self.leverage}x")
            parts.append(f"仓位: {self.position_size:.0%}")
            if self.stop_loss_pct:
                parts.append(f"止损: {self.stop_loss_pct:.1%}")
            if self.take_profit_pct:
                parts.append(f"止盈: {self.take_profit_pct:.1%}")
        return " | ".join(parts)


# ═══════════════════════════════════════════
#  第三层：交易信号（策略的输出产物）
# ═══════════════════════════════════════════

@dataclass
class TradeSignal:
    """
    策略产出的具体交易信号。

    这就是 Eric 说的 "信号是具体的币种、入场时间、入场价格、止盈止损"。
    每当策略规则被触发，就产出一个 TradeSignal，记录在 SignalLog 中。
    """
    signal_id: str
    datetime: str
    symbol: str
    side: str               # "long" / "short"
    action: str              # "open" / "close"
    price: float
    quantity: float
    leverage: int = 1
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""         # "RSI=28.5<30 AND funding_rate=-0.001<0"
    pnl: Optional[float] = None  # 平仓时的已实现盈亏

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "datetime": self.datetime,
            "symbol": self.symbol,
            "side": self.side,
            "action": self.action,
            "price": self.price,
            "quantity": self.quantity,
            "leverage": self.leverage,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "reason": self.reason,
            "pnl": self.pnl,
        }

    def format_row(self) -> str:
        """格式化为表格行（终端展示）"""
        sl = f"{self.stop_loss:.2f}" if self.stop_loss else "-"
        tp = f"{self.take_profit:.2f}" if self.take_profit else "-"
        pnl_str = f"{self.pnl:+.2f}" if self.pnl is not None else "-"
        return (f"{self.datetime} | {self.symbol:16s} | {self.side:5s} {self.action:5s} | "
                f"${self.price:<10.2f} | SL:{sl:>10s} TP:{tp:>10s} | PnL:{pnl_str:>10s} | {self.reason}")


# ═══════════════════════════════════════════
#  第四层：信号存储
# ═══════════════════════════════════════════

class SignalLog:
    """
    存储策略产出的所有信号，支持查询/导出/展示。
    """

    def __init__(self):
        self.signals: list[TradeSignal] = []

    def add(self, signal: TradeSignal):
        self.signals.append(signal)

    def __len__(self):
        return len(self.signals)

    def to_dataframe(self) -> pd.DataFrame:
        if not self.signals:
            return pd.DataFrame()
        return pd.DataFrame([s.to_dict() for s in self.signals])

    def to_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self.signals], f, ensure_ascii=False, indent=2)

    def to_csv(self, path: str):
        self.to_dataframe().to_csv(path, index=False, encoding="utf-8")

    def get_open_signals(self) -> list[TradeSignal]:
        return [s for s in self.signals if s.action == "open"]

    def get_close_signals(self) -> list[TradeSignal]:
        return [s for s in self.signals if s.action == "close"]

    def summary(self) -> str:
        if not self.signals:
            return "暂无信号"
        opens = self.get_open_signals()
        closes = self.get_close_signals()
        longs = [s for s in opens if s.side == "long"]
        shorts = [s for s in opens if s.side == "short"]
        total_pnl = sum(s.pnl for s in closes if s.pnl is not None)
        wins = sum(1 for s in closes if s.pnl is not None and s.pnl > 0)
        losses = sum(1 for s in closes if s.pnl is not None and s.pnl <= 0)
        win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0

        lines = [
            f"═══ 信号统计 ═══",
            f"  总信号数: {len(self.signals)}",
            f"  开仓: {len(opens)} (做多:{len(longs)} 做空:{len(shorts)})",
            f"  平仓: {len(closes)}",
            f"  总盈亏: {total_pnl:+.2f} USDT",
            f"  胜率: {win_rate:.1%} ({wins}胜 {losses}负)",
        ]
        return "\n".join(lines)

    def print_table(self):
        """终端打印信号表格"""
        header = (f"{'时间':19s} | {'币种':16s} | {'方向':11s} | "
                  f"{'价格':12s} | {'止损':>10s} {'止盈':>10s} | {'盈亏':>10s} | 触发原因")
        print("=" * len(header))
        print(header)
        print("-" * len(header))
        for s in self.signals:
            print(s.format_row())
        print("=" * len(header))


# ═══════════════════════════════════════════
#  策略组装器（Agent 写策略的核心）
# ═══════════════════════════════════════════

@dataclass
class Strategy:
    """
    完整的量化策略。Agent 根据用户自然语言描述来组装。

    流程：
      1. 用户说 "我要一个 MACD 策略"
      2. Agent 追问：入场条件？盈亏比？杠杆？仓位？
      3. Agent 用 StrategyRule + Condition 组装策略
      4. 策略在历史数据上运行 → 产出 TradeSignal 列表
      5. TradeSignal 喂入 BacktestEngine → 回测结果
      6. 用户看结果，调参数 → 重跑（或用 GeneticOptimizer 自动寻优）
    """
    name: str
    symbol: str
    rules: list[StrategyRule] = field(default_factory=list)
    indicators_config: dict = field(default_factory=dict)
    signal_log: SignalLog = field(default_factory=SignalLog)

    def add_rule(self, rule: StrategyRule):
        self.rules.append(rule)
        return self

    def compute_context(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        volumes: np.ndarray,
        funding_rate: float = 0.0,
        open_interest: float = 0.0,
        prev_ctx: Optional[dict] = None,
    ) -> dict:
        """根据历史数据 + 指标配置，计算当前 bar 的所有指标上下文。"""
        idx = len(closes) - 1
        ctx: dict = {
            "close": closes[idx],
            "high": highs[idx],
            "low": lows[idx],
            "volume": volumes[idx],
            "funding_rate": funding_rate,
            "open_interest": open_interest,
        }

        cfg = self.indicators_config

        if "sma_fast" in cfg:
            ctx["fast_ma"] = Indicators.sma(closes, cfg["sma_fast"])[idx]
        if "sma_slow" in cfg:
            ctx["slow_ma"] = Indicators.sma(closes, cfg["sma_slow"])[idx]
        if "ema_fast" in cfg:
            ctx["fast_ema"] = Indicators.ema(closes, cfg["ema_fast"])[idx]
        if "ema_slow" in cfg:
            ctx["slow_ema"] = Indicators.ema(closes, cfg["ema_slow"])[idx]
        if "rsi_period" in cfg:
            ctx["rsi"] = Indicators.rsi(closes, cfg["rsi_period"])[idx]
        if "macd" in cfg:
            m = cfg["macd"]
            macd_line, signal_line, hist = Indicators.macd(
                closes, m.get("fast", 12), m.get("slow", 26), m.get("signal", 9))
            ctx["macd"] = macd_line[idx]
            ctx["macd_signal"] = signal_line[idx]
            ctx["macd_histogram"] = hist[idx]
        if "bollinger" in cfg:
            b = cfg["bollinger"]
            upper, middle, lower = Indicators.bollinger_bands(
                closes, b.get("period", 20), b.get("std", 2.0))
            ctx["bb_upper"] = upper[idx]
            ctx["bb_middle"] = middle[idx]
            ctx["bb_lower"] = lower[idx]
        if "atr_period" in cfg:
            ctx["atr"] = Indicators.atr(highs, lows, closes, cfg["atr_period"])[idx]
        if "volume_ma_period" in cfg:
            vma = Indicators.volume_ma(volumes, cfg["volume_ma_period"])[idx]
            ctx["volume_ma"] = vma
            ctx["volume_ratio"] = volumes[idx] / vma if vma and vma > 0 else 1.0
        if "kdj" in cfg:
            kp = cfg["kdj"].get("k_period", 9)
            dp = cfg["kdj"].get("d_period", 3)
            k, d, j = Indicators.kdj(highs, lows, closes, kp, dp)
            ctx["kdj_k"] = k[idx]
            ctx["kdj_d"] = d[idx]
            ctx["kdj_j"] = j[idx]

        if prev_ctx:
            for key in ["fast_ma", "slow_ma", "fast_ema", "slow_ema",
                        "rsi", "macd", "macd_signal", "macd_histogram",
                        "close", "funding_rate", "open_interest",
                        "kdj_k", "kdj_d", "kdj_j"]:
                if key in prev_ctx:
                    ctx[f"prev_{key}"] = prev_ctx[key]

        return ctx

    def evaluate(self, ctx: dict, bar_datetime: str, current_price: float,
                 has_long: bool = False, has_short: bool = False) -> list[TradeSignal]:
        """
        评估所有规则，产出触发的 TradeSignal 列表。

        这是核心方法 — 策略规则满足时，产出具体信号。
        """
        triggered: list[TradeSignal] = []
        for rule in self.rules:
            if not rule.check(ctx):
                continue

            if rule.action == RuleAction.OPEN_LONG and has_long:
                continue
            if rule.action == RuleAction.OPEN_SHORT and has_short:
                continue
            if rule.action == RuleAction.CLOSE_LONG and not has_long:
                continue
            if rule.action == RuleAction.CLOSE_SHORT and not has_short:
                continue

            side = "long" if rule.action in (RuleAction.OPEN_LONG, RuleAction.CLOSE_LONG) else "short"
            action = "open" if rule.action in (RuleAction.OPEN_LONG, RuleAction.OPEN_SHORT) else "close"

            sl, tp = None, None
            if action == "open":
                if rule.stop_loss_pct:
                    sl = (current_price * (1 - rule.stop_loss_pct) if side == "long"
                          else current_price * (1 + rule.stop_loss_pct))
                if rule.take_profit_pct:
                    tp = (current_price * (1 + rule.take_profit_pct) if side == "long"
                          else current_price * (1 - rule.take_profit_pct))

            signal = TradeSignal(
                signal_id=uuid.uuid4().hex[:12],
                datetime=bar_datetime,
                symbol=self.symbol,
                side=side,
                action=action,
                price=current_price,
                quantity=rule.position_size,
                leverage=rule.leverage,
                stop_loss=sl,
                take_profit=tp,
                reason=rule.condition.name,
            )
            triggered.append(signal)
            self.signal_log.add(signal)

        return triggered

    def describe(self) -> str:
        lines = [
            f"═══ 策略: {self.name} ═══",
            f"标的: {self.symbol}",
            f"指标: {self.indicators_config}",
            f"规则数: {len(self.rules)}",
            "",
        ]
        for i, rule in enumerate(self.rules, 1):
            lines.append(f"  [{i}] {rule.describe()}")
        return "\n".join(lines)


# ═══════════════════════════════════════════
#  快捷策略构建函数（Agent 直接调用）
# ═══════════════════════════════════════════

def build_macd_strategy(
    symbol: str = "BTC-USDT-PERP",
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    leverage: int = 5,
    position_size: float = 0.2,
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.15,
) -> Strategy:
    """
    MACD 策略：MACD 柱状图由负转正做多，由正转负做空。
    用户说: "帮我做一个 MACD 策略"
    """
    strategy = Strategy(
        name=f"MACD策略 ({fast}/{slow}/{signal})",
        symbol=symbol,
        indicators_config={"macd": {"fast": fast, "slow": slow, "signal": signal}},
    )
    strategy.add_rule(StrategyRule(
        "MACD金叉做多", RuleAction.OPEN_LONG,
        Condition.cross_above("macd", "macd_signal"),
        leverage, position_size, stop_loss_pct, take_profit_pct,
    ))
    strategy.add_rule(StrategyRule(
        "MACD死叉做空", RuleAction.OPEN_SHORT,
        Condition.cross_below("macd", "macd_signal"),
        leverage, position_size, stop_loss_pct, take_profit_pct,
    ))
    strategy.add_rule(StrategyRule(
        "MACD死叉平多", RuleAction.CLOSE_LONG,
        Condition.cross_below("macd", "macd_signal"),
    ))
    strategy.add_rule(StrategyRule(
        "MACD金叉平空", RuleAction.CLOSE_SHORT,
        Condition.cross_above("macd", "macd_signal"),
    ))
    return strategy


def build_ma_cross_strategy(
    symbol: str = "BTC-USDT-PERP",
    fast_period: int = 10,
    slow_period: int = 30,
    leverage: int = 5,
    position_size: float = 0.2,
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.15,
) -> Strategy:
    """均线交叉策略。用户说: "双均线金叉做多死叉做空" """
    strategy = Strategy(
        name=f"均线交叉策略 (MA{fast_period}/{slow_period})",
        symbol=symbol,
        indicators_config={"sma_fast": fast_period, "sma_slow": slow_period},
    )
    strategy.add_rule(StrategyRule(
        "金叉做多", RuleAction.OPEN_LONG,
        Condition.cross_above("fast_ma", "slow_ma"),
        leverage, position_size, stop_loss_pct, take_profit_pct))
    strategy.add_rule(StrategyRule(
        "死叉做空", RuleAction.OPEN_SHORT,
        Condition.cross_below("fast_ma", "slow_ma"),
        leverage, position_size, stop_loss_pct, take_profit_pct))
    strategy.add_rule(StrategyRule(
        "死叉平多", RuleAction.CLOSE_LONG,
        Condition.cross_below("fast_ma", "slow_ma")))
    strategy.add_rule(StrategyRule(
        "金叉平空", RuleAction.CLOSE_SHORT,
        Condition.cross_above("fast_ma", "slow_ma")))
    return strategy


def build_rsi_strategy(
    symbol: str = "BTC-USDT-PERP",
    period: int = 14,
    overbought: float = 70,
    oversold: float = 30,
    leverage: int = 3,
    position_size: float = 0.2,
    stop_loss_pct: float = 0.05,
) -> Strategy:
    """RSI 超买超卖策略。用户说: "RSI 低于 30 做多，高于 70 做空" """
    strategy = Strategy(
        name=f"RSI策略 ({period}, OB:{overbought} OS:{oversold})",
        symbol=symbol,
        indicators_config={"rsi_period": period},
    )
    strategy.add_rule(StrategyRule(
        f"RSI<{oversold}做多", RuleAction.OPEN_LONG,
        Condition.below("rsi", oversold),
        leverage, position_size, stop_loss_pct))
    strategy.add_rule(StrategyRule(
        f"RSI>{overbought}做空", RuleAction.OPEN_SHORT,
        Condition.above("rsi", overbought),
        leverage, position_size, stop_loss_pct))
    strategy.add_rule(StrategyRule(
        "RSI回归平多", RuleAction.CLOSE_LONG,
        Condition.above("rsi", (oversold + 50) / 2)))
    strategy.add_rule(StrategyRule(
        "RSI回归平空", RuleAction.CLOSE_SHORT,
        Condition.below("rsi", (overbought + 50) / 2)))
    return strategy


def build_funding_rate_strategy(
    symbol: str = "BTC-USDT-PERP",
    open_threshold: float = 0.0005,
    close_threshold: float = 0.00015,
    leverage: int = 1,
    position_size: float = 0.5,
) -> Strategy:
    """资金费率套利策略。用户说: "费率高做空收费率" """
    strategy = Strategy(
        name=f"资金费率套利 (>{open_threshold:.4%})",
        symbol=symbol,
    )
    strategy.add_rule(StrategyRule(
        "正费率做空", RuleAction.OPEN_SHORT,
        Condition.above("funding_rate", open_threshold),
        leverage, position_size))
    strategy.add_rule(StrategyRule(
        "负费率做多", RuleAction.OPEN_LONG,
        Condition.below("funding_rate", -open_threshold),
        leverage, position_size))
    strategy.add_rule(StrategyRule(
        "费率回归平空", RuleAction.CLOSE_SHORT,
        Condition.between("funding_rate", -close_threshold, close_threshold)))
    strategy.add_rule(StrategyRule(
        "费率回归平多", RuleAction.CLOSE_LONG,
        Condition.between("funding_rate", -close_threshold, close_threshold)))
    return strategy


def build_bollinger_strategy(
    symbol: str = "BTC-USDT-PERP",
    period: int = 20,
    std_dev: float = 2.0,
    leverage: int = 3,
    position_size: float = 0.2,
    stop_loss_pct: float = 0.03,
) -> Strategy:
    """布林带策略。用户说: "跌破布林带下轨做多，突破上轨做空" """
    strategy = Strategy(
        name=f"布林带策略 (BB{period}, {std_dev}σ)",
        symbol=symbol,
        indicators_config={"bollinger": {"period": period, "std": std_dev}},
    )
    strategy.add_rule(StrategyRule(
        "跌破下轨做多", RuleAction.OPEN_LONG,
        Condition("close < bb_lower",
                  lambda ctx: ctx.get("close", 0) < ctx.get("bb_lower", float("inf"))),
        leverage, position_size, stop_loss_pct))
    strategy.add_rule(StrategyRule(
        "突破上轨做空", RuleAction.OPEN_SHORT,
        Condition("close > bb_upper",
                  lambda ctx: ctx.get("close", 0) > ctx.get("bb_upper", 0)),
        leverage, position_size, stop_loss_pct))
    strategy.add_rule(StrategyRule(
        "回归中轨平多", RuleAction.CLOSE_LONG,
        Condition("close > bb_middle",
                  lambda ctx: ctx.get("close", 0) > ctx.get("bb_middle", 0))))
    strategy.add_rule(StrategyRule(
        "回归中轨平空", RuleAction.CLOSE_SHORT,
        Condition("close < bb_middle",
                  lambda ctx: ctx.get("close", 0) < ctx.get("bb_middle", float("inf")))))
    return strategy
