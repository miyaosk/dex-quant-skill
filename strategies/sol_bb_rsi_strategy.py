"""
SOL 布林带 + RSI 均值回归策略

用户需求: "SOL 布林带下轨买入 + RSI 超卖确认，上轨卖出，15m 短线"

买入条件:
  - 价格触碰布林带下轨（close <= lower band）
  - RSI < 35（超卖确认）
  - 成交量 > 均量 1.2 倍（有量配合）

卖出条件:
  - 价格触碰布林带上轨（close >= upper band）
  - 或 RSI > 70（超买）

风控:
  - 止损 1.5%（短线止损紧一点）
  - 止盈 3%

使用:
  回测: python sol_bb_rsi_strategy.py backtest 2024-10-01 2024-12-31
  实时: python sol_bb_rsi_strategy.py live
"""

import json
import sys
import os
from datetime import datetime, timezone

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(SKILL_ROOT, "backtester", "scripts"))

from data_client import DataClient
from indicators import Indicators
import numpy as np

# ═══════════════════════════════════════════
# 策略配置
# ═══════════════════════════════════════════

STRATEGY_NAME = "SOL 布林带+RSI 均值回归"
STRATEGY_VERSION = "v1.0"
SYMBOL = "SOLUSDT"
TIMEFRAME = "15m"

BB_PERIOD = 20
BB_STD = 2.0
RSI_PERIOD = 14
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 70
VOL_MA_PERIOD = 20
VOL_MULTIPLIER = 1.2

STOP_LOSS_PCT = 0.015
TAKE_PROFIT_PCT = 0.03


# ═══════════════════════════════════════════
# 信号生成
# ═══════════════════════════════════════════

def generate_signals(mode="live", start_date=None, end_date=None):
    client = DataClient()
    ticker = "SOL-USDT-PERP"

    if mode == "backtest" and start_date and end_date:
        df = client.get_perp_klines(ticker, TIMEFRAME, start_date, end_date)
    else:
        df = client.get_perp_klines(ticker, TIMEFRAME, limit=200)

    client.close()

    if df.empty:
        return {"strategy_name": STRATEGY_NAME, "signals": [], "error": "无数据"}

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values

    upper, middle, lower = Indicators.bollinger_bands(close, BB_PERIOD, BB_STD)
    rsi = Indicators.rsi(close, RSI_PERIOD)
    vol_ma = Indicators.volume_ma(volume, VOL_MA_PERIOD)

    signals = []
    position = None
    start_idx = max(BB_PERIOD, RSI_PERIOD, VOL_MA_PERIOD) + 1

    for i in range(start_idx, len(df)):
        row = df.iloc[i]
        price = float(row["close"])
        ts = str(row["datetime"])

        if position is None:
            if (not np.isnan(lower[i]) and price <= lower[i]
                and not np.isnan(rsi[i]) and rsi[i] < RSI_OVERSOLD
                and not np.isnan(vol_ma[i]) and vol_ma[i] > 0
                and volume[i] > vol_ma[i] * VOL_MULTIPLIER):

                signals.append({
                    "timestamp": ts,
                    "symbol": SYMBOL,
                    "action": "buy",
                    "direction": "long",
                    "confidence": min(0.6 + (RSI_OVERSOLD - rsi[i]) * 0.02, 0.95),
                    "reason": f"触碰布林下轨({lower[i]:.2f}) + RSI超卖({rsi[i]:.0f}) + 放量{volume[i]/vol_ma[i]:.1f}x",
                    "source_type": "technical",
                    "price_at_signal": price,
                    "suggested_stop_loss": round(price * (1 - STOP_LOSS_PCT), 2),
                    "suggested_take_profit": round(price * (1 + TAKE_PROFIT_PCT), 2),
                    "metadata": {
                        "bb_lower": round(float(lower[i]), 2),
                        "bb_upper": round(float(upper[i]), 2),
                        "bb_middle": round(float(middle[i]), 2),
                        "rsi": round(float(rsi[i]), 1),
                        "vol_ratio": round(float(volume[i] / vol_ma[i]), 2),
                    }
                })
                position = "long"

        elif position == "long":
            should_sell = False
            reason_parts = []

            if not np.isnan(upper[i]) and price >= upper[i]:
                should_sell = True
                reason_parts.append(f"触碰布林上轨({upper[i]:.2f})")

            if not np.isnan(rsi[i]) and rsi[i] > RSI_OVERBOUGHT:
                should_sell = True
                reason_parts.append(f"RSI超买({rsi[i]:.0f})")

            if should_sell:
                signals.append({
                    "timestamp": ts,
                    "symbol": SYMBOL,
                    "action": "sell",
                    "direction": "long",
                    "confidence": 0.75,
                    "reason": " + ".join(reason_parts),
                    "source_type": "technical",
                    "price_at_signal": price,
                    "metadata": {
                        "bb_upper": round(float(upper[i]), 2),
                        "rsi": round(float(rsi[i]), 1),
                    }
                })
                position = None

    return {
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": mode,
        "signals": signals,
    }


if __name__ == "__main__":
    from strategy_runner import run
    run(generate_signals, STRATEGY_NAME, SYMBOL, TIMEFRAME, script_path=__file__)
