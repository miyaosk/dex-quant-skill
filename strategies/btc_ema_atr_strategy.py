"""
BTC EMA 双均线交叉 + ATR 动态止盈止损

用户需求: "BTC 做个技术指标趋势策略，均线金叉做多死叉做空，1h"

做多:
  - EMA(9) 上穿 EMA(21)（金叉）
  - RSI > 50（多头动量确认）
  - 止损: 入场价 - 2×ATR(14)
  - 止盈: 入场价 + 3×ATR(14)

做空:
  - EMA(9) 下穿 EMA(21)（死叉）
  - RSI < 50（空头动量确认）
  - 止损: 入场价 + 2×ATR(14)
  - 止盈: 入场价 - 3×ATR(14)

使用:
  回测: python btc_ema_atr_strategy.py backtest 2025-01-01 2025-03-01
  实时: python btc_ema_atr_strategy.py live
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

STRATEGY_NAME = "BTC EMA金叉死叉+ATR动态止损"
STRATEGY_VERSION = "v1.0"
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"

EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
ATR_PERIOD = 14
ATR_SL_MULT = 2.0
ATR_TP_MULT = 3.0


# ═══════════════════════════════════════════
# 信号生成
# ═══════════════════════════════════════════

def generate_signals(mode="live", start_date=None, end_date=None):
    client = DataClient()
    ticker = "BTC-USDT-PERP"

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

    ema_fast = Indicators.ema(close, EMA_FAST)
    ema_slow = Indicators.ema(close, EMA_SLOW)
    rsi = Indicators.rsi(close, RSI_PERIOD)
    atr = Indicators.atr(high, low, close, ATR_PERIOD)

    golden_cross = Indicators.crossover(ema_fast, ema_slow)
    death_cross = Indicators.crossunder(ema_fast, ema_slow)

    signals = []
    position = None
    start_idx = max(EMA_SLOW, RSI_PERIOD, ATR_PERIOD) + 1

    for i in range(start_idx, len(df)):
        price = float(close[i])
        ts = str(df.iloc[i]["datetime"])
        cur_atr = float(atr[i]) if not np.isnan(atr[i]) else 0
        cur_rsi = float(rsi[i]) if not np.isnan(rsi[i]) else 50

        if position is None:
            if golden_cross[i] and cur_rsi > 50 and cur_atr > 0:
                sl = round(price - ATR_SL_MULT * cur_atr, 2)
                tp = round(price + ATR_TP_MULT * cur_atr, 2)
                signals.append({
                    "timestamp": ts,
                    "symbol": SYMBOL,
                    "action": "buy",
                    "direction": "long",
                    "confidence": min(0.5 + (cur_rsi - 50) * 0.01, 0.95),
                    "reason": f"EMA({EMA_FAST})上穿EMA({EMA_SLOW}) + RSI={cur_rsi:.0f} + ATR={cur_atr:.0f}",
                    "source_type": "technical",
                    "price_at_signal": price,
                    "suggested_stop_loss": sl,
                    "suggested_take_profit": tp,
                    "metadata": {
                        "ema_fast": round(float(ema_fast[i]), 2),
                        "ema_slow": round(float(ema_slow[i]), 2),
                        "rsi": round(cur_rsi, 1),
                        "atr": round(cur_atr, 2),
                    }
                })
                position = "long"

            elif death_cross[i] and cur_rsi < 50 and cur_atr > 0:
                sl = round(price + ATR_SL_MULT * cur_atr, 2)
                tp = round(price - ATR_TP_MULT * cur_atr, 2)
                signals.append({
                    "timestamp": ts,
                    "symbol": SYMBOL,
                    "action": "buy",
                    "direction": "short",
                    "confidence": min(0.5 + (50 - cur_rsi) * 0.01, 0.95),
                    "reason": f"EMA({EMA_FAST})下穿EMA({EMA_SLOW}) + RSI={cur_rsi:.0f} + ATR={cur_atr:.0f}",
                    "source_type": "technical",
                    "price_at_signal": price,
                    "suggested_stop_loss": sl,
                    "suggested_take_profit": tp,
                    "metadata": {
                        "ema_fast": round(float(ema_fast[i]), 2),
                        "ema_slow": round(float(ema_slow[i]), 2),
                        "rsi": round(cur_rsi, 1),
                        "atr": round(cur_atr, 2),
                    }
                })
                position = "short"

        elif position == "long":
            if death_cross[i]:
                signals.append({
                    "timestamp": ts,
                    "symbol": SYMBOL,
                    "action": "sell",
                    "direction": "long",
                    "confidence": 0.7,
                    "reason": f"EMA({EMA_FAST})下穿EMA({EMA_SLOW})平多",
                    "source_type": "technical",
                    "price_at_signal": price,
                    "metadata": {"rsi": round(cur_rsi, 1)},
                })
                position = None

        elif position == "short":
            if golden_cross[i]:
                signals.append({
                    "timestamp": ts,
                    "symbol": SYMBOL,
                    "action": "sell",
                    "direction": "short",
                    "confidence": 0.7,
                    "reason": f"EMA({EMA_FAST})上穿EMA({EMA_SLOW})平空",
                    "source_type": "technical",
                    "price_at_signal": price,
                    "metadata": {"rsi": round(cur_rsi, 1)},
                })
                position = None

    return {
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": mode,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "indicators": f"EMA({EMA_FAST}/{EMA_SLOW}) + RSI({RSI_PERIOD}) + ATR({ATR_PERIOD})",
        "signals": signals,
    }


if __name__ == "__main__":
    from strategy_runner import run
    run(generate_signals, STRATEGY_NAME, SYMBOL, TIMEFRAME, script_path=__file__)
