"""
信号定制引擎 — 用户自然语言 → 可组合信号 → 策略代码

设计理念：
  用户说 "当 RSI 超过 70 且资金费率大于 0.05% 时做空"
  → Agent 用本模块组装出信号对象
  → 信号对象喂入 BacktestEngine 驱动交易

三层结构：
  1. 指标计算层（Indicators）: MA/EMA/RSI/MACD/Bollinger 等
  2. 条件组合层（Conditions）: 大于/小于/交叉/AND/OR
  3. 信号输出层（Signal）: entry_long / entry_short / exit_long / exit_short
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


# ═══════════════════════════════════════════
#  第二层：条件组合
# ═══════════════════════════════════════════

class Condition:
    """
    可组合的条件单元。

    用法:
        rsi_high = Condition.above("rsi", 70)
        fr_high = Condition.above("funding_rate", 0.0005)
        short_signal = rsi_high & fr_high   # AND 组合
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
            lambda ctx: self.evaluate(ctx) and other.evaluate(ctx),
        )

    def __or__(self, other: Condition) -> Condition:
        return Condition(
            f"({self.name} OR {other.name})",
            lambda ctx: self.evaluate(ctx) or other.evaluate(ctx),
        )

    def __invert__(self) -> Condition:
        return Condition(
            f"NOT({self.name})",
            lambda ctx: not self.evaluate(ctx),
        )

    # ── 工厂方法：自然语言 → 条件 ──

    @staticmethod
    def above(field: str, threshold: float) -> Condition:
        """字段值 > 阈值。如: Condition.above("rsi", 70)"""
        return Condition(
            f"{field} > {threshold}",
            lambda ctx: ctx.get(field, 0) > threshold,
        )

    @staticmethod
    def below(field: str, threshold: float) -> Condition:
        """字段值 < 阈值。如: Condition.below("rsi", 30)"""
        return Condition(
            f"{field} < {threshold}",
            lambda ctx: ctx.get(field, 0) < threshold,
        )

    @staticmethod
    def cross_above(fast_field: str, slow_field: str) -> Condition:
        """快线上穿慢线。如: Condition.cross_above("fast_ma", "slow_ma")"""
        return Condition(
            f"{fast_field} cross above {slow_field}",
            lambda ctx: (
                ctx.get(fast_field, 0) > ctx.get(slow_field, 0) and
                ctx.get(f"prev_{fast_field}", 0) <= ctx.get(f"prev_{slow_field}", 0)
            ),
        )

    @staticmethod
    def cross_below(fast_field: str, slow_field: str) -> Condition:
        """快线下穿慢线。"""
        return Condition(
            f"{fast_field} cross below {slow_field}",
            lambda ctx: (
                ctx.get(fast_field, 0) < ctx.get(slow_field, 0) and
                ctx.get(f"prev_{fast_field}", 0) >= ctx.get(f"prev_{slow_field}", 0)
            ),
        )

    @staticmethod
    def between(field: str, low: float, high: float) -> Condition:
        """字段值在区间内。"""
        return Condition(
            f"{low} < {field} < {high}",
            lambda ctx: low < ctx.get(field, 0) < high,
        )

    @staticmethod
    def change_pct_above(field: str, pct: float) -> Condition:
        """字段变化百分比超过阈值。"""
        return Condition(
            f"{field} change > {pct}%",
            lambda ctx: (
                abs(ctx.get(field, 0) - ctx.get(f"prev_{field}", 0)) /
                max(abs(ctx.get(f"prev_{field}", 0)), 1e-10) > pct / 100
            ) if ctx.get(f"prev_{field}") is not None else False,
        )

    def __repr__(self):
        return f"Condition({self.name})"


# ═══════════════════════════════════════════
#  第三层：信号定义
# ═══════════════════════════════════════════

class SignalType(Enum):
    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"


@dataclass
class Signal:
    """
    一个完整的交易信号。

    用法:
        Signal(
            name="RSI超卖反弹",
            signal_type=SignalType.ENTRY_LONG,
            condition=Condition.below("rsi", 30) & Condition.above("volume_ratio", 1.5),
            leverage=5,
            stop_loss_pct=0.03,
            take_profit_pct=0.10,
        )
    """
    name: str
    signal_type: SignalType
    condition: Condition
    leverage: int = 1
    position_size: float = 0.1
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None

    def check(self, ctx: dict) -> bool:
        return self.condition.evaluate(ctx)

    def describe(self) -> str:
        parts = [
            f"信号: {self.name}",
            f"类型: {self.signal_type.value}",
            f"条件: {self.condition.name}",
            f"杠杆: {self.leverage}x",
            f"仓位: {self.position_size}",
        ]
        if self.stop_loss_pct:
            parts.append(f"止损: {self.stop_loss_pct:.1%}")
        if self.take_profit_pct:
            parts.append(f"止盈: {self.take_profit_pct:.1%}")
        return " | ".join(parts)


# ═══════════════════════════════════════════
#  信号策略组装器
# ═══════════════════════════════════════════

@dataclass
class SignalStrategy:
    """
    将多个信号组装成完整策略。

    用法:
        strategy = SignalStrategy(name="BTC 动量策略", symbol="BTC-USDT-PERP")
        strategy.add_signal(entry_long_signal)
        strategy.add_signal(entry_short_signal)
        strategy.add_signal(exit_long_signal)
        strategy.add_signal(exit_short_signal)

        # 逐 bar 运行
        for bar in klines:
            ctx = strategy.compute_context(bar, history)
            actions = strategy.evaluate(ctx)
    """
    name: str
    symbol: str
    signals: list[Signal] = field(default_factory=list)
    indicators_config: dict = field(default_factory=dict)

    def add_signal(self, signal: Signal):
        self.signals.append(signal)
        return self

    def compute_context(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        volumes: np.ndarray,
        funding_rate: float = 0.0,
        open_interest: float = 0.0,
        prev_ctx: dict = None,
    ) -> dict:
        """
        根据历史数据计算所有指标，生成上下文。

        Agent 可自由扩展此方法添加更多指标。
        """
        idx = len(closes) - 1
        ctx = {
            "close": closes[idx],
            "high": highs[idx],
            "low": lows[idx],
            "volume": volumes[idx],
            "funding_rate": funding_rate,
            "open_interest": open_interest,
        }

        cfg = self.indicators_config

        if "sma_fast" in cfg:
            sma = Indicators.sma(closes, cfg["sma_fast"])
            ctx["fast_ma"] = sma[idx]
        if "sma_slow" in cfg:
            sma = Indicators.sma(closes, cfg["sma_slow"])
            ctx["slow_ma"] = sma[idx]
        if "ema_fast" in cfg:
            ema = Indicators.ema(closes, cfg["ema_fast"])
            ctx["fast_ema"] = ema[idx]
        if "ema_slow" in cfg:
            ema = Indicators.ema(closes, cfg["ema_slow"])
            ctx["slow_ema"] = ema[idx]
        if "rsi_period" in cfg:
            rsi = Indicators.rsi(closes, cfg["rsi_period"])
            ctx["rsi"] = rsi[idx]
        if "macd" in cfg:
            m = cfg["macd"]
            macd_line, signal_line, hist = Indicators.macd(
                closes, m.get("fast", 12), m.get("slow", 26), m.get("signal", 9)
            )
            ctx["macd"] = macd_line[idx]
            ctx["macd_signal"] = signal_line[idx]
            ctx["macd_histogram"] = hist[idx]
        if "bollinger" in cfg:
            b = cfg["bollinger"]
            upper, middle, lower = Indicators.bollinger_bands(
                closes, b.get("period", 20), b.get("std", 2.0)
            )
            ctx["bb_upper"] = upper[idx]
            ctx["bb_middle"] = middle[idx]
            ctx["bb_lower"] = lower[idx]
        if "atr_period" in cfg:
            atr = Indicators.atr(highs, lows, closes, cfg["atr_period"])
            ctx["atr"] = atr[idx]
        if "volume_ma_period" in cfg:
            vma = Indicators.volume_ma(volumes, cfg["volume_ma_period"])
            ctx["volume_ma"] = vma[idx]
            ctx["volume_ratio"] = volumes[idx] / vma[idx] if vma[idx] and vma[idx] > 0 else 1.0

        if prev_ctx:
            for key in ["fast_ma", "slow_ma", "fast_ema", "slow_ema",
                        "rsi", "macd", "macd_signal", "close",
                        "funding_rate", "open_interest"]:
                if key in prev_ctx:
                    ctx[f"prev_{key}"] = prev_ctx[key]

        return ctx

    def evaluate(self, ctx: dict) -> list[Signal]:
        """评估所有信号，返回当前触发的信号列表。"""
        triggered = []
        for signal in self.signals:
            if signal.check(ctx):
                triggered.append(signal)
        return triggered

    def describe(self) -> str:
        """打印策略的完整描述（自然语言可读）。"""
        lines = [
            f"═══ 策略: {self.name} ═══",
            f"标的: {self.symbol}",
            f"指标配置: {self.indicators_config}",
            f"信号数量: {len(self.signals)}",
            "",
        ]
        for i, sig in enumerate(self.signals, 1):
            lines.append(f"  [{i}] {sig.describe()}")
        return "\n".join(lines)


# ═══════════════════════════════════════════
#  快捷构建函数（Agent 直接调用）
# ═══════════════════════════════════════════

def build_ma_cross_signals(
    fast_period: int = 10,
    slow_period: int = 30,
    leverage: int = 5,
    position_size: float = 0.1,
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.15,
) -> tuple[dict, list[Signal]]:
    """
    快捷构建：均线交叉信号组。

    自然语言: "快速均线上穿慢速均线时做多，下穿时做空"
    """
    config = {"sma_fast": fast_period, "sma_slow": slow_period}
    signals = [
        Signal("均线金叉做多", SignalType.ENTRY_LONG,
               Condition.cross_above("fast_ma", "slow_ma"),
               leverage, position_size, stop_loss_pct, take_profit_pct),
        Signal("均线死叉做空", SignalType.ENTRY_SHORT,
               Condition.cross_below("fast_ma", "slow_ma"),
               leverage, position_size, stop_loss_pct, take_profit_pct),
        Signal("均线死叉平多", SignalType.EXIT_LONG,
               Condition.cross_below("fast_ma", "slow_ma")),
        Signal("均线金叉平空", SignalType.EXIT_SHORT,
               Condition.cross_above("fast_ma", "slow_ma")),
    ]
    return config, signals


def build_rsi_signals(
    period: int = 14,
    overbought: float = 70,
    oversold: float = 30,
    leverage: int = 3,
    position_size: float = 0.1,
    stop_loss_pct: float = 0.05,
) -> tuple[dict, list[Signal]]:
    """
    快捷构建：RSI 超买超卖信号组。

    自然语言: "RSI 低于 30 做多，高于 70 做空"
    """
    config = {"rsi_period": period}
    signals = [
        Signal(f"RSI超卖(<{oversold})做多", SignalType.ENTRY_LONG,
               Condition.below("rsi", oversold),
               leverage, position_size, stop_loss_pct),
        Signal(f"RSI超买(>{overbought})做空", SignalType.ENTRY_SHORT,
               Condition.above("rsi", overbought),
               leverage, position_size, stop_loss_pct),
        Signal(f"RSI回归(>{50})平多", SignalType.EXIT_LONG,
               Condition.above("rsi", (oversold + 50) / 2)),
        Signal(f"RSI回归(<{50})平空", SignalType.EXIT_SHORT,
               Condition.below("rsi", (overbought + 50) / 2)),
    ]
    return config, signals


def build_funding_rate_signals(
    open_threshold: float = 0.0005,
    close_threshold: float = 0.00015,
    leverage: int = 1,
    position_size: float = 0.5,
) -> tuple[dict, list[Signal]]:
    """
    快捷构建：资金费率套利信号组。

    自然语言: "资金费率大于 0.05% 时做空收费率，回归后平仓"
    """
    config = {}
    signals = [
        Signal(f"正费率(>{open_threshold:.4%})做空", SignalType.ENTRY_SHORT,
               Condition.above("funding_rate", open_threshold),
               leverage, position_size),
        Signal(f"负费率(<{-open_threshold:.4%})做多", SignalType.ENTRY_LONG,
               Condition.below("funding_rate", -open_threshold),
               leverage, position_size),
        Signal(f"费率回归平空", SignalType.EXIT_SHORT,
               Condition.between("funding_rate", -close_threshold, close_threshold)),
        Signal(f"费率回归平多", SignalType.EXIT_LONG,
               Condition.between("funding_rate", -close_threshold, close_threshold)),
    ]
    return config, signals


def build_bollinger_signals(
    period: int = 20,
    std_dev: float = 2.0,
    leverage: int = 3,
    position_size: float = 0.1,
    stop_loss_pct: float = 0.03,
) -> tuple[dict, list[Signal]]:
    """
    快捷构建：布林带突破信号组。

    自然语言: "价格突破布林带下轨做多，突破上轨做空"
    """
    config = {"bollinger": {"period": period, "std": std_dev}}
    signals = [
        Signal("跌破下轨做多", SignalType.ENTRY_LONG,
               Condition.below("close", 0) | Condition(
                   "close < bb_lower",
                   lambda ctx: ctx.get("close", 0) < ctx.get("bb_lower", float("inf"))
               ),
               leverage, position_size, stop_loss_pct),
        Signal("突破上轨做空", SignalType.ENTRY_SHORT,
               Condition(
                   "close > bb_upper",
                   lambda ctx: ctx.get("close", 0) > ctx.get("bb_upper", 0)
               ),
               leverage, position_size, stop_loss_pct),
        Signal("回归中轨平多", SignalType.EXIT_LONG,
               Condition(
                   "close > bb_middle",
                   lambda ctx: ctx.get("close", 0) > ctx.get("bb_middle", 0)
               )),
        Signal("回归中轨平空", SignalType.EXIT_SHORT,
               Condition(
                   "close < bb_middle",
                   lambda ctx: ctx.get("close", 0) < ctx.get("bb_middle", float("inf"))
               )),
    ]
    return config, signals


def build_multi_factor_signals(
    rsi_period: int = 14,
    ma_fast: int = 10,
    ma_slow: int = 30,
    rsi_threshold_long: float = 40,
    rsi_threshold_short: float = 60,
    funding_threshold: float = 0.0003,
    leverage: int = 5,
    position_size: float = 0.1,
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.15,
) -> tuple[dict, list[Signal]]:
    """
    快捷构建：多因子组合信号。

    自然语言: "均线金叉 + RSI 没超买 + 资金费率不太高 → 做多"
    """
    config = {
        "rsi_period": rsi_period,
        "sma_fast": ma_fast,
        "sma_slow": ma_slow,
    }
    signals = [
        Signal(
            "多因子做多(金叉+RSI低+费率低)",
            SignalType.ENTRY_LONG,
            Condition.cross_above("fast_ma", "slow_ma")
            & Condition.below("rsi", rsi_threshold_short)
            & Condition.below("funding_rate", funding_threshold),
            leverage, position_size, stop_loss_pct, take_profit_pct,
        ),
        Signal(
            "多因子做空(死叉+RSI高+费率高)",
            SignalType.ENTRY_SHORT,
            Condition.cross_below("fast_ma", "slow_ma")
            & Condition.above("rsi", rsi_threshold_long)
            & Condition.above("funding_rate", -funding_threshold),
            leverage, position_size, stop_loss_pct, take_profit_pct,
        ),
        Signal("死叉平多", SignalType.EXIT_LONG,
               Condition.cross_below("fast_ma", "slow_ma")),
        Signal("金叉平空", SignalType.EXIT_SHORT,
               Condition.cross_above("fast_ma", "slow_ma")),
    ]
    return config, signals
