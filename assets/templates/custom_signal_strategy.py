"""
策略驱动信号模板

核心流程：
  用户描述意图 → Agent 写策略（本文件）→ 策略跑数据产出信号 → 信号驱动回测 → 输出结果

信号 = 策略产出的具体交易指令（币种 + 时间 + 价格 + 方向 + 止盈止损）

示例用户指令:
  "帮我做一个 MACD 策略做 BTC，5 倍杠杆，止损 5%，跑去年的数据"
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import numpy as np
from loguru import logger

from scripts.data_client import DataClient
from scripts.backtest_engine import BacktestEngine
from scripts.signal_builder import (
    Strategy, StrategyRule, RuleAction, Condition, TradeSignal,
    build_macd_strategy,
)


# ═══════════════════════════════════════════
#  第 1 步：Agent 根据用户描述构建策略
# ═══════════════════════════════════════════

SYMBOL = "BTC-USDT-PERP"
BINANCE_SYMBOL = "BTCUSDT"
INTERVAL = "1d"
LOOKBACK_DAYS = 365

INITIAL_CAPITAL = 100_000
LEVERAGE = 5
MARGIN_MODE = "isolated"

# Agent 一行调用预设策略 ...
strategy = build_macd_strategy(
    symbol=SYMBOL,
    fast=12, slow=26, signal=9,
    leverage=LEVERAGE,
    position_size=0.2,
    stop_loss_pct=0.05,
    take_profit_pct=0.15,
)

# ... 或自由组合规则
# strategy = Strategy(
#     name="自定义多因子策略",
#     symbol=SYMBOL,
#     indicators_config={
#         "macd": {"fast": 12, "slow": 26, "signal": 9},
#         "rsi_period": 14,
#     },
# )
# strategy.add_rule(StrategyRule(
#     "MACD金叉+RSI未超买→做多", RuleAction.OPEN_LONG,
#     Condition.cross_above("macd", "macd_signal") & Condition.below("rsi", 65),
#     leverage=5, position_size=0.2, stop_loss_pct=0.05, take_profit_pct=0.15,
# ))


# ═══════════════════════════════════════════
#  第 2 步：拉取数据
# ═══════════════════════════════════════════

def fetch_data():
    dc = DataClient()
    logger.info(f"拉取 {BINANCE_SYMBOL} {INTERVAL} K线...")
    klines = dc.get_perp_klines(BINANCE_SYMBOL, INTERVAL, limit=LOOKBACK_DAYS)

    logger.info(f"拉取 {BINANCE_SYMBOL} 资金费率...")
    funding_rates = dc.get_funding_rate(BINANCE_SYMBOL, limit=LOOKBACK_DAYS * 3)

    fr_map = {}
    for fr in funding_rates:
        date_key = fr["fundingTime"][:10]
        fr_map[date_key] = float(fr["fundingRate"])

    return klines, fr_map


# ═══════════════════════════════════════════
#  第 3 步：策略运行 → 产出信号 → 驱动回测
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
        # 解析 bar 时间
        bar_time = klines[i].get("openTime", "")
        if isinstance(bar_time, (int, float)):
            from datetime import datetime, timezone
            bar_datetime = datetime.fromtimestamp(bar_time / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        else:
            bar_datetime = str(bar_time)[:16]

        fr = fr_map.get(bar_datetime[:10], 0.0)

        ctx = strategy.compute_context(
            closes[:i + 1], highs[:i + 1], lows[:i + 1], volumes[:i + 1],
            funding_rate=fr, prev_ctx=prev_ctx,
        )

        # 策略评估 → 产出信号
        signals = strategy.evaluate(
            ctx, bar_datetime, closes[i],
            has_long=has_long, has_short=has_short,
        )

        # 信号驱动回测引擎执行
        for sig in signals:
            if sig.action == "open" and sig.side == "long":
                engine.open_long(SYMBOL, sig.quantity, sig.price)
                has_long = True
                if sig.stop_loss:
                    engine.set_stop_loss(SYMBOL, sig.stop_loss)
                if sig.take_profit:
                    engine.set_take_profit(SYMBOL, sig.take_profit)
                logger.info(f"[{sig.datetime}] 📈 开多 ${sig.price:.2f} | SL:{sig.stop_loss or '-'} TP:{sig.take_profit or '-'} | {sig.reason}")

            elif sig.action == "open" and sig.side == "short":
                engine.open_short(SYMBOL, sig.quantity, sig.price)
                has_short = True
                if sig.stop_loss:
                    engine.set_stop_loss(SYMBOL, sig.stop_loss)
                if sig.take_profit:
                    engine.set_take_profit(SYMBOL, sig.take_profit)
                logger.info(f"[{sig.datetime}] 📉 开空 ${sig.price:.2f} | SL:{sig.stop_loss or '-'} TP:{sig.take_profit or '-'} | {sig.reason}")

            elif sig.action == "close" and sig.side == "long":
                engine.close_long(SYMBOL, sig.price)
                has_long = False
                logger.info(f"[{sig.datetime}] 平多 ${sig.price:.2f} | {sig.reason}")

            elif sig.action == "close" and sig.side == "short":
                engine.close_short(SYMBOL, sig.price)
                has_short = False
                logger.info(f"[{sig.datetime}] 平空 ${sig.price:.2f} | {sig.reason}")

        prev_ctx = ctx

    return engine


# ═══════════════════════════════════════════
#  第 4 步：输出回测报告 + 信号列表
# ═══════════════════════════════════════════

def print_report(engine: BacktestEngine):
    metrics = engine.get_metrics()
    print("\n" + "=" * 70)
    print(f"  策略: {strategy.name}")
    print(f"  标的: {strategy.symbol}")
    print(f"  杠杆: {LEVERAGE}x | 保证金模式: {MARGIN_MODE}")
    print("=" * 70)
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
    print("=" * 70)

    # 打印策略产出的信号表
    print(f"\n{strategy.signal_log.summary()}")
    print("\n信号列表:")
    strategy.signal_log.print_table()

    # 可选：导出信号到文件
    # strategy.signal_log.to_json("signals.json")
    # strategy.signal_log.to_csv("signals.csv")


if __name__ == "__main__":
    engine = run_backtest()
    print_report(engine)
