"""
自定义信号驱动策略模板

用户用自然语言定义信号 → Agent 填充此模板 → 一键回测

示例用户指令:
  "当 RSI 低于 30 且资金费率为负时做多 BTC，5 倍杠杆，止损 3%，回测最近一年"
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import numpy as np
from loguru import logger

from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine
from scripts.signal_builder import (
    Indicators, Condition, Signal, SignalType, SignalStrategy,
)


# ═══════════════════════════════════════════
#  第 1 步：定义信号（Agent 根据用户自然语言填写）
# ═══════════════════════════════════════════

SYMBOL = "BTC-USDT-PERP"
BINANCE_SYMBOL = "BTCUSDT"
INTERVAL = "1d"
LOOKBACK_DAYS = 365

INITIAL_CAPITAL = 100_000
LEVERAGE = 5
MARGIN_MODE = "isolated"

strategy = SignalStrategy(
    name="RSI超卖+负费率做多BTC",
    symbol=SYMBOL,
    indicators_config={
        "rsi_period": 14,
        "sma_fast": 10,
        "sma_slow": 30,
        "volume_ma_period": 20,
    },
)

strategy.add_signal(Signal(
    name="RSI超卖+负费率→做多",
    signal_type=SignalType.ENTRY_LONG,
    condition=(
        Condition.below("rsi", 30)
        & Condition.below("funding_rate", 0)
    ),
    leverage=LEVERAGE,
    position_size=0.2,
    stop_loss_pct=0.03,
    take_profit_pct=0.10,
))

strategy.add_signal(Signal(
    name="RSI超买+正费率→做空",
    signal_type=SignalType.ENTRY_SHORT,
    condition=(
        Condition.above("rsi", 70)
        & Condition.above("funding_rate", 0.0005)
    ),
    leverage=LEVERAGE,
    position_size=0.2,
    stop_loss_pct=0.03,
    take_profit_pct=0.10,
))

strategy.add_signal(Signal(
    name="RSI回归→平多",
    signal_type=SignalType.EXIT_LONG,
    condition=Condition.above("rsi", 55),
))

strategy.add_signal(Signal(
    name="RSI回归→平空",
    signal_type=SignalType.EXIT_SHORT,
    condition=Condition.below("rsi", 45),
))


# ═══════════════════════════════════════════
#  第 2 步：获取数据
# ═══════════════════════════════════════════

def fetch_data():
    dc = DataClient()
    logger.info(f"拉取 {BINANCE_SYMBOL} {INTERVAL} K线数据...")
    klines = dc.get_perp_klines(BINANCE_SYMBOL, INTERVAL, limit=LOOKBACK_DAYS)

    logger.info(f"拉取 {BINANCE_SYMBOL} 资金费率数据...")
    funding_rates = dc.get_funding_rate(BINANCE_SYMBOL, limit=LOOKBACK_DAYS * 3)

    fr_map = {}
    for fr in funding_rates:
        date_key = fr["fundingTime"][:10]
        fr_map[date_key] = float(fr["fundingRate"])

    return klines, fr_map


# ═══════════════════════════════════════════
#  第 3 步：运行回测
# ═══════════════════════════════════════════

def run_backtest():
    klines, fr_map = fetch_data()

    closes = np.array([float(k["close"]) for k in klines])
    highs = np.array([float(k["high"]) for k in klines])
    lows = np.array([float(k["low"]) for k in klines])
    volumes = np.array([float(k["volume"]) for k in klines])

    logger.info(f"数据量: {len(closes)} 根 K 线")
    logger.info(f"\n{strategy.describe()}\n")

    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    engine.set_leverage(SYMBOL, LEVERAGE)
    engine.set_margin_mode(SYMBOL, MARGIN_MODE)

    warmup = 30
    prev_ctx = None
    has_long = False
    has_short = False

    for i in range(warmup, len(closes)):
        date_key = klines[i].get("openTime", "")
        if isinstance(date_key, (int, float)):
            from datetime import datetime, timezone
            date_key = datetime.fromtimestamp(date_key / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            date_key = str(date_key)[:10]

        fr = fr_map.get(date_key, 0.0)

        ctx = strategy.compute_context(
            closes[:i + 1],
            highs[:i + 1],
            lows[:i + 1],
            volumes[:i + 1],
            funding_rate=fr,
            prev_ctx=prev_ctx,
        )

        triggered = strategy.evaluate(ctx)

        for sig in triggered:
            price = closes[i]
            qty = sig.position_size

            if sig.signal_type == SignalType.ENTRY_LONG and not has_long:
                engine.open_long(SYMBOL, qty, price)
                has_long = True
                if sig.stop_loss_pct:
                    engine.set_stop_loss(SYMBOL, price * (1 - sig.stop_loss_pct))
                if sig.take_profit_pct:
                    engine.set_take_profit(SYMBOL, price * (1 + sig.take_profit_pct))
                logger.info(f"[{date_key}] 开多 | 价格={price:.2f} | RSI={ctx.get('rsi', 0):.1f} | FR={fr:.6f}")

            elif sig.signal_type == SignalType.ENTRY_SHORT and not has_short:
                engine.open_short(SYMBOL, qty, price)
                has_short = True
                if sig.stop_loss_pct:
                    engine.set_stop_loss(SYMBOL, price * (1 + sig.stop_loss_pct))
                if sig.take_profit_pct:
                    engine.set_take_profit(SYMBOL, price * (1 - sig.take_profit_pct))
                logger.info(f"[{date_key}] 开空 | 价格={price:.2f} | RSI={ctx.get('rsi', 0):.1f} | FR={fr:.6f}")

            elif sig.signal_type == SignalType.EXIT_LONG and has_long:
                engine.close_long(SYMBOL, price)
                has_long = False
                logger.info(f"[{date_key}] 平多 | 价格={price:.2f} | RSI={ctx.get('rsi', 0):.1f}")

            elif sig.signal_type == SignalType.EXIT_SHORT and has_short:
                engine.close_short(SYMBOL, price)
                has_short = False
                logger.info(f"[{date_key}] 平空 | 价格={price:.2f} | RSI={ctx.get('rsi', 0):.1f}")

        prev_ctx = ctx

    return engine


# ═══════════════════════════════════════════
#  第 4 步：输出回测报告
# ═══════════════════════════════════════════

def print_report(engine: BacktestEngine):
    metrics = engine.get_metrics()
    print("\n" + "=" * 60)
    print(f"  策略: {strategy.name}")
    print(f"  标的: {strategy.symbol}")
    print(f"  杠杆: {LEVERAGE}x | 保证金模式: {MARGIN_MODE}")
    print("=" * 60)
    print(f"  总收益率:       {metrics.get('total_return', 0):.2%}")
    print(f"  年化收益率:     {metrics.get('annual_return', 0):.2%}")
    print(f"  夏普比率:       {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"  最大回撤:       {metrics.get('max_drawdown', 0):.2%}")
    print(f"  胜率:           {metrics.get('win_rate', 0):.2%}")
    print(f"  盈亏比:         {metrics.get('profit_loss_ratio', 0):.2f}")
    print(f"  总交易次数:     {metrics.get('total_trades', 0)}")
    print(f"  强平次数:       {metrics.get('liquidation_count', 0)}")
    print(f"  累计手续费:     {metrics.get('total_commission', 0):.2f} USDT")
    print(f"  净资金费率:     {metrics.get('net_funding', 0):.2f} USDT")
    print("=" * 60)


if __name__ == "__main__":
    engine = run_backtest()
    print_report(engine)
